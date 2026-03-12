"""
analysis/db.py — SQLite schema initialisation and connection helper.
"""

import sqlite3
from pathlib import Path

import config

DB_PATH: Path = config.DATA_DIR / "pipeline.db"


def get_connection() -> sqlite3.Connection:
    """Return a connection with row_factory set to sqlite3.Row."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_backlog_tables(conn: sqlite3.Connection) -> None:
    """Create backlog and niche state tables if they don't exist yet."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS backlog_stories (
        id          TEXT PRIMARY KEY,
        channel     TEXT NOT NULL,
        subreddit   TEXT NOT NULL,
        title       TEXT NOT NULL,
        body        TEXT NOT NULL,
        score       INTEGER NOT NULL,
        word_count  INTEGER NOT NULL,
        status      TEXT NOT NULL DEFAULT 'pending',
        scraped_at  TEXT NOT NULL,
        approved_at TEXT,
        used_at     TEXT
    );

    CREATE TABLE IF NOT EXISTS backlog_tweets (
        tweet_id    TEXT PRIMARY KEY,
        channel     TEXT NOT NULL,
        username    TEXT NOT NULL,
        tweet_text  TEXT NOT NULL,
        likes       INTEGER NOT NULL,
        retweets    INTEGER NOT NULL,
        status      TEXT NOT NULL DEFAULT 'pending',
        scraped_at  TEXT NOT NULL,
        approved_at TEXT,
        used_at     TEXT
    );

    CREATE TABLE IF NOT EXISTS niche_state (
        channel                 TEXT PRIMARY KEY,
        manually_reviewed_count INTEGER NOT NULL DEFAULT 0
    );
    """)


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

        CREATE TABLE IF NOT EXISTS style_profiles (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id  TEXT,
            name        TEXT,
            format      TEXT,
            profile_json TEXT,
            created_at  TEXT,
            FOREIGN KEY (channel_id) REFERENCES channels(id)
        );
        """)
        init_backlog_tables(conn)
