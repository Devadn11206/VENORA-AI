"""Database initialization utilities."""

import sys
from sqlalchemy.engine import Engine

from app.core.logging import get_logger
from app.database.base import Base
from app.database.session import engine
import app.models  # Ensure all models are registered on Base.metadata

logger = get_logger("database.init")


def init_db(target_engine: Engine = engine) -> None:
    """Create all registered database tables and FTS5 virtual tables if they do not already exist."""
    logger.info("Initializing database schema...")
    Base.metadata.create_all(bind=target_engine)

    # Initialize SQLite FTS5 table for full-text search across document chunks
    try:
        with target_engine.connect() as conn:
            conn.execute(
                __import__("sqlalchemy").text(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(
                        chunk_id UNINDEXED,
                        document_id UNINDEXED,
                        content,
                        section_title,
                        tokenize = 'porter unicode61'
                    );
                    """
                )
            )
            conn.commit()
            logger.info("SQLite FTS5 virtual table 'document_chunks_fts' verified.")
    except Exception as exc:
        logger.warning(f"Could not initialize FTS5 virtual table (lexical search fallback will be used): {exc}")

    logger.info("Database schema initialized successfully.")


if __name__ == "__main__":
    try:
        init_db()
        print("Database initialized successfully.")
    except Exception as exc:
        print(f"Database initialization failed: {exc}", file=sys.stderr)
        sys.exit(1)
