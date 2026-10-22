"""Database initialization utilities."""

import sys
from sqlalchemy.engine import Engine

from app.core.logging import get_logger
from app.database.base import Base
from app.database.session import engine
import app.models  # Ensure all models are registered on Base.metadata

logger = get_logger("database.init")


def init_db(target_engine: Engine = engine) -> None:
    """Create all registered database tables if they do not already exist."""
    logger.info("Initializing database schema...")
    Base.metadata.create_all(bind=target_engine)
    logger.info("Database schema initialized successfully.")


if __name__ == "__main__":
    try:
        init_db()
        print("Database initialized successfully.")
    except Exception as exc:
        print(f"Database initialization failed: {exc}", file=sys.stderr)
        sys.exit(1)
