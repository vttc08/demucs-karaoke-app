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
    _migrate_legacy_queue_items_if_needed()
    Base.metadata.create_all(bind=engine)
    ensure_auxiliary_schema()


def _migrate_legacy_queue_items_if_needed():
    """Migrate old single-table queue schema into media_items + queue_items split."""
    inspector = inspect(engine)
    if "queue_items" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("queue_items")}
    if "media_id" in columns and "position" in columns:
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS media_items (
                    id INTEGER PRIMARY KEY,
                    youtube_id TEXT UNIQUE,
                    title TEXT NOT NULL,
                    artist TEXT,
                    media_path TEXT NOT NULL UNIQUE,
                    lyrics_path TEXT,
                    vocals_path TEXT,
                    missing INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    last_scanned_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO media_items (
                    youtube_id, title, artist, media_path, lyrics_path, vocals_path,
                    missing, created_at, updated_at, last_scanned_at
                )
                SELECT
                    q.youtube_id,
                    COALESCE(q.title, q.youtube_id) AS title,
                    q.artist,
                    COALESCE(q.media_path, '/media/' || q.youtube_id || '.mp4') AS media_path,
                    NULL AS lyrics_path,
                    NULL AS vocals_path,
                    CASE WHEN q.media_path IS NULL THEN 1 ELSE 0 END AS missing,
                    COALESCE(q.created_at, CURRENT_TIMESTAMP) AS created_at,
                    COALESCE(q.updated_at, CURRENT_TIMESTAMP) AS updated_at,
                    NULL AS last_scanned_at
                FROM queue_items q
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE queue_items_new (
                    id INTEGER PRIMARY KEY,
                    media_id INTEGER NOT NULL REFERENCES media_items(id) ON DELETE RESTRICT,
                    position INTEGER NOT NULL,
                    requested_karaoke BOOLEAN NOT NULL DEFAULT 0,
                    requested_burn_lyrics BOOLEAN NOT NULL DEFAULT 0,
                    user_id TEXT,
                    session_id TEXT,
                    status TEXT DEFAULT 'pending',
                    error TEXT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO queue_items_new (
                    id, media_id, position, requested_karaoke, requested_burn_lyrics,
                    user_id, session_id, status, error, created_at, updated_at
                )
                SELECT
                    q.id,
                    m.id AS media_id,
                    q.id * 1000 AS position,
                    COALESCE(q.is_karaoke, 0) AS requested_karaoke,
                    CASE WHEN COALESCE(q.is_karaoke, 0) = 1 THEN COALESCE(q.burn_lyrics, 0) ELSE 0 END AS requested_burn_lyrics,
                    NULL AS user_id,
                    NULL AS session_id,
                    COALESCE(q.status, 'pending') AS status,
                    q.error,
                    COALESCE(q.created_at, CURRENT_TIMESTAMP) AS created_at,
                    COALESCE(q.updated_at, CURRENT_TIMESTAMP) AS updated_at
                FROM queue_items q
                JOIN media_items m ON m.youtube_id = q.youtube_id
                """
            )
        )
        conn.execute(text("DROP TABLE queue_items"))
        conn.execute(text("ALTER TABLE queue_items_new RENAME TO queue_items"))


def ensure_auxiliary_schema(bind_engine=None):
    """Ensure non-ORM schema objects (indexes/FTS/triggers) exist."""
    target_engine = bind_engine or engine
    _ensure_indexes(target_engine)
    _ensure_media_items_fts(target_engine)


def _ensure_indexes(bind_engine):
    """Ensure schema indexes exist for both fresh and migrated databases."""
    with bind_engine.begin() as conn:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_media_items_title ON media_items(title)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_media_items_artist ON media_items(artist)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_media_items_youtube_id ON media_items(youtube_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_queue_position ON queue_items(position)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_queue_items_media_id ON queue_items(media_id)"
            )
        )


def _ensure_media_items_fts(bind_engine):
    """Ensure media_items full-text index exists and stays in sync."""
    with bind_engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS media_items_fts
                USING fts5(
                    title,
                    artist,
                    content='media_items',
                    content_rowid='id'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TRIGGER IF NOT EXISTS media_items_ai
                AFTER INSERT ON media_items
                BEGIN
                    INSERT INTO media_items_fts(rowid, title, artist)
                    VALUES (new.id, COALESCE(new.title, ''), COALESCE(new.artist, ''));
                END
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TRIGGER IF NOT EXISTS media_items_ad
                AFTER DELETE ON media_items
                BEGIN
                    INSERT INTO media_items_fts(media_items_fts, rowid, title, artist)
                    VALUES ('delete', old.id, COALESCE(old.title, ''), COALESCE(old.artist, ''));
                END
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TRIGGER IF NOT EXISTS media_items_au
                AFTER UPDATE ON media_items
                BEGIN
                    INSERT INTO media_items_fts(media_items_fts, rowid, title, artist)
                    VALUES ('delete', old.id, COALESCE(old.title, ''), COALESCE(old.artist, ''));
                    INSERT INTO media_items_fts(rowid, title, artist)
                    VALUES (new.id, COALESCE(new.title, ''), COALESCE(new.artist, ''));
                END
                """
            )
        )
        conn.execute(text("INSERT INTO media_items_fts(media_items_fts) VALUES('rebuild')"))


def get_db() -> Session:
    """Get database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
