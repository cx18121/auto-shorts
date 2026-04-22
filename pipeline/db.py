"""
pipeline/db.py — SQLite schema initialisation and connection helper.
"""

import sqlite3
from pathlib import Path

import config
from pipeline.backlog import init_backlog_tables as init_backlog_tables  # noqa: F401 — re-export

DB_PATH: Path = config.DATA_DIR / "pipeline.db"


def get_connection() -> sqlite3.Connection:
    """Return a connection with row_factory set to sqlite3.Row."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn



def init_db() -> None:
    """Create all tables if they don't exist yet."""
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS channels (
            id              TEXT PRIMARY KEY,
            url             TEXT,
            name            TEXT,
            subscriber_count INTEGER,
            fetched_at      TEXT
        );

        CREATE TABLE IF NOT EXISTS videos (
            id                      TEXT PRIMARY KEY,
            channel_id              TEXT,
            title                   TEXT,
            description             TEXT,
            view_count              INTEGER,
            like_count              INTEGER,
            comment_count           INTEGER,
            duration_seconds        INTEGER,
            published_at            TEXT,
            tags                    TEXT,   -- JSON array
            thumbnail_url           TEXT,
            category_id             TEXT,
            default_audio_language  TEXT,
            caption_type            TEXT,
            transcript              TEXT,
            performance_score       REAL,
            is_top_performer        INTEGER DEFAULT 0,
            -- derived metrics
            title_length            INTEGER,
            description_length      INTEGER,
            like_to_view_ratio      REAL,
            comment_to_view_ratio   REAL,
            hour_of_day_published   INTEGER,
            day_of_week_published   INTEGER,
            -- analysis JSON blobs
            visual_analysis         TEXT,
            thumbnail_analysis      TEXT,
            FOREIGN KEY (channel_id) REFERENCES channels(id)
        );
        """)
        init_backlog_tables(conn)
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS video_insights (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            channel             TEXT NOT NULL,
            platform            TEXT NOT NULL,
            video_id            TEXT NOT NULL,
            fetched_at          TEXT NOT NULL,
            published_at        TEXT,
            view_count          INTEGER,
            like_count          INTEGER,
            comment_count       INTEGER,
            watch_time_seconds  INTEGER,
            reach               INTEGER,
            shares              INTEGER,
            saves               INTEGER,
            title               TEXT,
            transcript_path     TEXT,
            bg_filename         TEXT,
            UNIQUE(channel, platform, video_id, fetched_at)
        );
        """)
