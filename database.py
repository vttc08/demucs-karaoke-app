"""Database connection and session management."""
from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker, Session
from models import Base
from config import settings

engine = create_engine(
    settings.database_url, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)
    _ensure_queue_item_columns()


def _ensure_queue_item_columns():
    """Apply lightweight schema additions for existing SQLite databases."""
    inspector = inspect(engine)
    if "queue_items" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("queue_items")}
    if "burn_lyrics" in columns:
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE queue_items "
                "ADD COLUMN burn_lyrics BOOLEAN DEFAULT 0 NOT NULL"
            )
        )


def get_db() -> Session:
    """Get database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
