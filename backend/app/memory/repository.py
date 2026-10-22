"""Repository layer for durable MemoryRecord persistence in SQLite via SQLAlchemy."""

from datetime import datetime, timezone, timedelta
import json
from typing import List, Optional, Tuple, Dict, Any
import uuid
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, desc, text

from app.models.memory import MemoryRecord, MemoryCategory, MemoryStatus
from app.memory.schemas import MemoryCreate, MemoryUpdate
from app.memory.deduplication import compute_content_hash, detect_memory_conflict
from app.core.logging import get_logger

logger = get_logger("memory.repository")


class MemoryRepository:
    """Manages transactional operations on the memories table and FTS index."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        schema: MemoryCreate,
        embedding: Optional[List[float]] = None,
        embedding_model: Optional[str] = None,
        default_ttl_days: int = 30
    ) -> MemoryRecord:
        """Create and persist a new MemoryRecord, with FTS5 indexing."""
        now = datetime.now(timezone.utc)
        mem_id = str(uuid.uuid4())
        content_hash = compute_content_hash(schema.content, schema.category)

        # Compute expiration if applicable
        expires_at = None
        if schema.ttl_days:
            expires_at = now + timedelta(days=schema.ttl_days)
        elif schema.category in (MemoryCategory.TASK_CONTEXT, MemoryCategory.EPISODIC_MEMORY):
            # Apply default TTL only to temporary categories
            expires_at = now + timedelta(days=default_ttl_days)

        embedding_json = json.dumps(embedding) if embedding else None

        record = MemoryRecord(
            id=mem_id,
            category=schema.category,
            content=schema.content,
            summary=schema.summary or (schema.content[:120] + "..." if len(schema.content) > 120 else schema.content),
            confidence=schema.confidence,
            importance=schema.importance,
            access_count=0,
            content_hash=content_hash,
            source_type=schema.source_type,
            source_reference=schema.source_reference,
            status=MemoryStatus.ACTIVE,
            embedding_json=embedding_json,
            embedding_model=embedding_model,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )

        self.db.add(record)
        self.db.flush()

        # Update FTS5 virtual table
        self._sync_fts_insert(mem_id, schema.category.value, schema.content)

        self.db.commit()
        self.db.refresh(record)
        return record

    def get_by_id(self, memory_id: str) -> Optional[MemoryRecord]:
        """Fetch memory record by its primary key UUID."""
        return self.db.query(MemoryRecord).filter(MemoryRecord.id == memory_id).first()

    def get_by_hash(self, content_hash: str, status: MemoryStatus = MemoryStatus.ACTIVE) -> Optional[MemoryRecord]:
        """Find active memory matching exact content hash."""
        return self.db.query(MemoryRecord).filter(
            MemoryRecord.content_hash == content_hash,
            MemoryRecord.status == status
        ).first()

    def list_memories(
        self,
        category: Optional[MemoryCategory] = None,
        status: Optional[MemoryStatus] = MemoryStatus.ACTIVE,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[int, List[MemoryRecord]]:
        """List memory records with pagination and optional filtering."""
        query = self.db.query(MemoryRecord)
        if status is not None:
            query = query.filter(MemoryRecord.status == status)
        if category is not None:
            query = query.filter(MemoryRecord.category == category)

        total = query.count()
        items = query.order_by(desc(MemoryRecord.created_at)).offset(offset).limit(limit).all()
        return total, items

    def update(
        self,
        memory_id: str,
        update_data: MemoryUpdate,
        new_embedding: Optional[List[float]] = None,
        embedding_model: Optional[str] = None
    ) -> Optional[MemoryRecord]:
        """Update an existing memory record."""
        record = self.get_by_id(memory_id)
        if not record:
            return None

        now = datetime.now(timezone.utc)
        record.updated_at = now

        if update_data.content is not None:
            record.content = update_data.content
            target_cat = update_data.category or record.category
            record.content_hash = compute_content_hash(update_data.content, target_cat)
            self._sync_fts_update(record.id, target_cat.value, update_data.content)

        if update_data.summary is not None:
            record.summary = update_data.summary
        if update_data.category is not None:
            record.category = update_data.category
        if update_data.confidence is not None:
            record.confidence = update_data.confidence
        if update_data.importance is not None:
            record.importance = update_data.importance
        if update_data.status is not None:
            record.status = update_data.status
        if update_data.ttl_days is not None:
            record.expires_at = now + timedelta(days=update_data.ttl_days)

        if new_embedding is not None:
            record.embedding_json = json.dumps(new_embedding)
            record.embedding_model = embedding_model

        self.db.commit()
        self.db.refresh(record)
        return record

    def archive(self, memory_id: str) -> Optional[MemoryRecord]:
        """Soft-archive a memory record."""
        record = self.get_by_id(memory_id)
        if not record:
            return None
        record.status = MemoryStatus.ARCHIVED
        record.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(record)
        return record

    def restore(self, memory_id: str) -> Optional[MemoryRecord]:
        """Restore an archived or superseded memory record to active status."""
        record = self.get_by_id(memory_id)
        if not record:
            return None
        record.status = MemoryStatus.ACTIVE
        record.superseded_by = None
        record.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(record)
        return record

    def mark_superseded(self, old_memory_id: str, new_memory_id: str) -> Optional[MemoryRecord]:
        """Mark an older memory record as superseded by a newer one."""
        record = self.get_by_id(old_memory_id)
        if not record:
            return None
        record.status = MemoryStatus.SUPERSEDED
        record.superseded_by = new_memory_id
        record.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(record)
        return record

    def delete(self, memory_id: str) -> bool:
        """Permanently delete a memory record and clean up index entries."""
        record = self.get_by_id(memory_id)
        if not record:
            return False

        self._sync_fts_delete(memory_id)
        self.db.delete(record)
        self.db.commit()
        return True

    def record_access(self, memory_id: str) -> None:
        """Update last_accessed_at and increment access_count."""
        record = self.get_by_id(memory_id)
        if record:
            record.access_count += 1
            record.last_accessed_at = datetime.now(timezone.utc)
            self.db.commit()

    def get_active_memories(
        self,
        categories: Optional[List[MemoryCategory]] = None,
        include_archived: bool = False
    ) -> List[MemoryRecord]:
        """Retrieve active memories that have not expired."""
        now = datetime.now(timezone.utc)
        query = self.db.query(MemoryRecord)

        if include_archived:
            query = query.filter(MemoryRecord.status.in_([MemoryStatus.ACTIVE, MemoryStatus.ARCHIVED]))
        else:
            query = query.filter(MemoryRecord.status == MemoryStatus.ACTIVE)

        # Filter out expired records
        query = query.filter(
            or_(
                MemoryRecord.expires_at.is_(None),
                MemoryRecord.expires_at > now
            )
        )

        if categories:
            query = query.filter(MemoryRecord.category.in_(categories))

        return query.all()

    def count_by_status(self) -> Dict[str, int]:
        """Count memories grouped by lifecycle status."""
        counts = {
            "active": 0,
            "archived": 0,
            "superseded": 0,
            "expired": 0,
        }
        now = datetime.now(timezone.utc)
        all_recs = self.db.query(MemoryRecord).all()
        for r in all_recs:
            if r.expires_at and r.expires_at <= now:
                counts["expired"] += 1
            elif r.status == MemoryStatus.ACTIVE:
                counts["active"] += 1
            elif r.status == MemoryStatus.ARCHIVED:
                counts["archived"] += 1
            elif r.status == MemoryStatus.SUPERSEDED:
                counts["superseded"] += 1
        return counts

    # -----------------------------------------------------------------
    # SQLite FTS5 Synchronization Helpers
    # -----------------------------------------------------------------
    def _sync_fts_insert(self, memory_id: str, category: str, content: str) -> None:
        try:
            self.db.execute(
                text("INSERT INTO memories_fts(memory_id, category, content) VALUES (:mid, :cat, :cnt)"),
                {"mid": memory_id, "cat": category, "cnt": content}
            )
        except Exception as exc:
            logger.debug(f"FTS5 insert skipped: {exc}")

    def _sync_fts_update(self, memory_id: str, category: str, content: str) -> None:
        try:
            self.db.execute(
                text("DELETE FROM memories_fts WHERE memory_id = :mid"),
                {"mid": memory_id}
            )
            self.db.execute(
                text("INSERT INTO memories_fts(memory_id, category, content) VALUES (:mid, :cat, :cnt)"),
                {"mid": memory_id, "cat": category, "cnt": content}
            )
        except Exception as exc:
            logger.debug(f"FTS5 update skipped: {exc}")

    def _sync_fts_delete(self, memory_id: str) -> None:
        try:
            self.db.execute(
                text("DELETE FROM memories_fts WHERE memory_id = :mid"),
                {"mid": memory_id}
            )
        except Exception as exc:
            logger.debug(f"FTS5 delete skipped: {exc}")
