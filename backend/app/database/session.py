"""Database engine configuration and session factory."""

from pathlib import Path
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import get_settings


def create_app_engine(database_url: str) -> Engine:
    """Create and configure a SQLAlchemy Engine."""
    connect_args = {}
    
    # SQLite specific configurations
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        
        # Ensure directory exists for file-based SQLite databases
        if "///" in database_url and not database_url.startswith("sqlite:///:memory:"):
            db_path_str = database_url.split("///")[-1]
            db_path = Path(db_path_str)
            if db_path.parent and not db_path.parent.exists():
                db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        database_url,
        connect_args=connect_args,
        echo=False,
        future=True,
    )

    # Enable SQLite Foreign Key constraints
    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()

    return engine


settings = get_settings()
engine = create_app_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a transactional database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
