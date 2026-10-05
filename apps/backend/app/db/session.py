import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def _database_url() -> str:
    """Resolve the database URL without forcing unrelated application settings.

    Narrow background workers (for example the hosting health controller) need
    only database access. When DATABASE_URL is explicitly provided, avoid
    importing the full application Settings object, whose production validator
    intentionally requires mail, billing, DNS and other control-plane secrets.

    API processes still import app.core.config through app.main and therefore
    retain the complete production configuration validation.
    """
    configured = os.getenv("DATABASE_URL")
    if configured:
        return configured
    from app.core.config import settings

    return settings.database_url


engine = create_engine(_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
