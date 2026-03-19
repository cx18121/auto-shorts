"""
pipeline/backlog.py — DB operations layer for the content backlog.

Single source of truth for all state transitions on backlog_stories,
backlog_tweets, and niche_state tables.

Callers should pass an sqlite3.Connection (row_factory=sqlite3.Row).
Use pipeline.db.get_connection() for production or sqlite3.connect(':memory:')
for tests.
"""
import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

PROBATION_THRESHOLD: int = 25


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_backlog_tables(conn: sqlite3.Connection) -> None:
    """Create backlog_stories, backlog_tweets, and niche_state tables.

    Uses CREATE TABLE IF NOT EXISTS — safe to call on an existing DB.
    This is the canonical DDL; pipeline/db.py delegates here.
    """
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS background_usage (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        channel     TEXT NOT NULL,
        bg_filename TEXT NOT NULL,
        used_at     TEXT NOT NULL
    );

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


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _pk(table: str) -> str:
    """Return the primary-key column name for a backlog table.

    Raises ValueError for unknown tables.
    """
    if table == "backlog_stories":
        return "id"
    if table == "backlog_tweets":
        return "tweet_id"
    raise ValueError(f"Unknown backlog table: {table!r}")


def _utcnow() -> str:
    """Return current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _ensure_niche_state(conn: sqlite3.Connection, channel: str) -> None:
    """Create a niche_state row for *channel* if one does not exist yet."""
    conn.execute(
        "INSERT OR IGNORE INTO niche_state (channel, manually_reviewed_count)"
        " VALUES (?, 0)",
        (channel,),
    )


# ---------------------------------------------------------------------------
# Insert
# ---------------------------------------------------------------------------

def insert_story(conn: sqlite3.Connection, item: dict) -> bool:
    """Insert a story into backlog_stories with status='pending'.

    Idempotent: re-inserting the same *id* is a no-op.

    Args:
        conn: Active SQLite connection.
        item: Dict with keys id, channel, subreddit, title, body, score,
              word_count. Optional key scraped_at (defaults to utcnow).

    Returns:
        True if a new row was inserted, False if it was a duplicate.
    """
    scraped_at = item.get("scraped_at") or _utcnow()
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO backlog_stories
            (id, channel, subreddit, title, body, score, word_count,
             status, scraped_at, approved_at, used_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, NULL, NULL)
        """,
        (
            item["id"],
            item["channel"],
            item["subreddit"],
            item["title"],
            item["body"],
            item["score"],
            item["word_count"],
            scraped_at,
        ),
    )
    conn.commit()
    inserted = cur.rowcount > 0
    if inserted:
        logger.debug("insert_story: inserted %s (%s)", item["id"], item["channel"])
    else:
        logger.debug("insert_story: duplicate %s, skipped", item["id"])
    return inserted


def insert_tweet(conn: sqlite3.Connection, item: dict) -> bool:
    """Insert a tweet into backlog_tweets with status='pending'.

    Idempotent: re-inserting the same *tweet_id* is a no-op.

    Args:
        conn: Active SQLite connection.
        item: Dict with keys tweet_id, channel, username, tweet_text,
              likes, retweets. Optional key scraped_at.

    Returns:
        True if a new row was inserted, False if it was a duplicate.
    """
    scraped_at = item.get("scraped_at") or _utcnow()
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO backlog_tweets
            (tweet_id, channel, username, tweet_text, likes, retweets,
             status, scraped_at, approved_at, used_at)
        VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, NULL, NULL)
        """,
        (
            item["tweet_id"],
            item["channel"],
            item["username"],
            item["tweet_text"],
            item["likes"],
            item["retweets"],
            scraped_at,
        ),
    )
    conn.commit()
    inserted = cur.rowcount > 0
    if inserted:
        logger.debug("insert_tweet: inserted %s (%s)", item["tweet_id"], item["channel"])
    else:
        logger.debug("insert_tweet: duplicate %s, skipped", item["tweet_id"])
    return inserted


# ---------------------------------------------------------------------------
# Status transitions — generic
# ---------------------------------------------------------------------------

def approve_item(conn: sqlite3.Connection, table: str, item_id: str, channel: str) -> None:
    """Set status='approved' and approved_at on a backlog row.

    Also increments the manually_reviewed_count for *channel* — this
    represents a human decision to approve the item.

    Args:
        conn:    Active SQLite connection.
        table:   'backlog_stories' or 'backlog_tweets'.
        item_id: Primary key value.
        channel: Channel slug (used to update niche_state).
    """
    pk = _pk(table)
    now = _utcnow()
    conn.execute(
        f"UPDATE {table} SET status='approved', approved_at=? WHERE {pk}=?",
        (now, item_id),
    )
    increment_reviewed_count(conn, channel)
    logger.info("approve_item: %s/%s approved (channel=%s)", table, item_id, channel)


def reject_item(conn: sqlite3.Connection, table: str, item_id: str, channel: str) -> None:
    """Set status='rejected' on a backlog row.

    Also increments the manually_reviewed_count — rejection still counts
    as a human review for probation tracking purposes.

    Args:
        conn:    Active SQLite connection.
        table:   'backlog_stories' or 'backlog_tweets'.
        item_id: Primary key value.
        channel: Channel slug.
    """
    pk = _pk(table)
    conn.execute(
        f"UPDATE {table} SET status='rejected' WHERE {pk}=?",
        (item_id,),
    )
    increment_reviewed_count(conn, channel)
    logger.info("reject_item: %s/%s rejected (channel=%s)", table, item_id, channel)


def mark_used(conn: sqlite3.Connection, table: str, item_id: str) -> None:
    """Set status='used' and used_at on a backlog row.

    Args:
        conn:    Active SQLite connection.
        table:   'backlog_stories' or 'backlog_tweets'.
        item_id: Primary key value.
    """
    pk = _pk(table)
    now = _utcnow()
    conn.execute(
        f"UPDATE {table} SET status='used', used_at=? WHERE {pk}=?",
        (now, item_id),
    )
    logger.info("mark_used: %s/%s marked used", table, item_id)


# ---------------------------------------------------------------------------
# Status transitions — story-specific convenience wrappers
# (used by tests and CLI for stories without needing to pass table name)
# ---------------------------------------------------------------------------

def approve_story(conn: sqlite3.Connection, story_id: str, channel: str = "") -> None:
    """Approve a single story by id.

    Convenience wrapper around approve_item for backlog_stories.
    *channel* defaults to empty string; the niche_state row will still
    be created with INSERT OR IGNORE so it is safe to omit.
    """
    pk = "id"
    now = _utcnow()
    conn.execute(
        f"UPDATE backlog_stories SET status='approved', approved_at=? WHERE {pk}=?",
        (now, story_id),
    )
    if channel:
        increment_reviewed_count(conn, channel)
    logger.info("approve_story: %s approved", story_id)


def reject_story(conn: sqlite3.Connection, story_id: str, channel: str = "") -> None:
    """Reject a single story by id.

    Convenience wrapper around reject_item for backlog_stories.
    """
    conn.execute(
        "UPDATE backlog_stories SET status='rejected' WHERE id=?",
        (story_id,),
    )
    if channel:
        increment_reviewed_count(conn, channel)
    logger.info("reject_story: %s rejected", story_id)


def mark_story_used(conn: sqlite3.Connection, story_id: str) -> None:
    """Mark a single story as used.

    Convenience wrapper around mark_used for backlog_stories.
    """
    now = _utcnow()
    conn.execute(
        "UPDATE backlog_stories SET status='used', used_at=? WHERE id=?",
        (now, story_id),
    )
    logger.info("mark_story_used: %s marked used", story_id)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def get_approved_stories(conn: sqlite3.Connection, channel: str) -> list:
    """Return all approved stories for *channel*, ordered by approved_at ASC.

    Args:
        conn:    Active SQLite connection with row_factory=sqlite3.Row.
        channel: Channel slug.

    Returns:
        List of sqlite3.Row objects.
    """
    return conn.execute(
        "SELECT * FROM backlog_stories"
        " WHERE channel=? AND status='approved'"
        " ORDER BY approved_at ASC",
        (channel,),
    ).fetchall()


def get_approved_tweets(conn: sqlite3.Connection, channel: str) -> list:
    """Return all approved tweets for *channel*, ordered by approved_at ASC."""
    return conn.execute(
        "SELECT * FROM backlog_tweets"
        " WHERE channel=? AND status='approved'"
        " ORDER BY approved_at ASC",
        (channel,),
    ).fetchall()


def get_pending_stories(conn: sqlite3.Connection, channel: str) -> list:
    """Return pending stories for *channel*, newest scraped batch first, then by score DESC within each batch."""
    return conn.execute(
        "SELECT * FROM backlog_stories"
        " WHERE channel=? AND status='pending'"
        " ORDER BY DATE(scraped_at) DESC, score DESC",
        (channel,),
    ).fetchall()


def get_pending_tweets(conn: sqlite3.Connection, channel: str) -> list:
    """Return pending tweets for *channel*, ordered by computed score (likes + retweets*3) DESC."""
    return conn.execute(
        "SELECT * FROM backlog_tweets"
        " WHERE channel=? AND status='pending'"
        " ORDER BY (likes + retweets * 3) DESC",
        (channel,),
    ).fetchall()


def get_status_counts(conn: sqlite3.Connection, channel: str) -> dict:
    """Return status counts for *channel* (or all channels if channel=='all').

    Returns:
        Dict mapping channel slug → {pending, approved, rejected, used}.
        Example: {'relationships': {'pending': 10, 'approved': 5, ...}}
    """
    statuses = ("pending", "approved", "rejected", "used")
    result: dict = {}

    for table in ("backlog_stories", "backlog_tweets"):
        if channel == "all":
            rows = conn.execute(
                f"SELECT channel, status, COUNT(*) AS cnt FROM {table}"
                f" GROUP BY channel, status"
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT channel, status, COUNT(*) AS cnt FROM {table}"
                f" WHERE channel=? GROUP BY channel, status",
                (channel,),
            ).fetchall()

        for row in rows:
            ch = row["channel"]
            if ch not in result:
                result[ch] = {s: 0 for s in statuses}
            if row["status"] in result[ch]:
                result[ch][row["status"]] += row["cnt"]

    # Ensure the requested channel key always exists (even with zero counts)
    if channel != "all" and channel not in result:
        result[channel] = {s: 0 for s in statuses}

    return result


# ---------------------------------------------------------------------------
# Probation / niche_state
# ---------------------------------------------------------------------------

def increment_reviewed_count(conn: sqlite3.Connection, channel: str) -> None:
    """Increment manually_reviewed_count for *channel* in niche_state.

    Creates the row first if it does not exist.
    """
    _ensure_niche_state(conn, channel)
    conn.execute(
        "UPDATE niche_state SET manually_reviewed_count = manually_reviewed_count + 1"
        " WHERE channel=?",
        (channel,),
    )
    logger.debug("increment_reviewed_count: channel=%s", channel)


def get_probation_remaining(conn: sqlite3.Connection, channel: str) -> int:
    """Return how many more manual reviews are needed before auto-approve activates.

    Returns:
        Integer >= 0. Zero means the channel has graduated from probation.
    """
    _ensure_niche_state(conn, channel)
    row = conn.execute(
        "SELECT manually_reviewed_count FROM niche_state WHERE channel=?",
        (channel,),
    ).fetchone()
    reviewed = row["manually_reviewed_count"] if row else 0
    remaining = max(0, PROBATION_THRESHOLD - reviewed)
    logger.debug("get_probation_remaining: channel=%s remaining=%d", channel, remaining)
    return remaining


def maybe_auto_approve(
    conn: sqlite3.Connection, table: str, item_id: str, channel: str
) -> bool:
    """Auto-approve *item_id* if the channel has graduated from probation.

    Does NOT increment manually_reviewed_count — auto-approved items are
    not counted as manual reviews.

    Args:
        conn:    Active SQLite connection.
        table:   'backlog_stories' or 'backlog_tweets'.
        item_id: Primary key value.
        channel: Channel slug.

    Returns:
        True if the item was auto-approved, False if still in probation.
    """
    _ensure_niche_state(conn, channel)
    row = conn.execute(
        "SELECT manually_reviewed_count FROM niche_state WHERE channel=?",
        (channel,),
    ).fetchone()
    reviewed = row["manually_reviewed_count"] if row else 0

    if reviewed >= PROBATION_THRESHOLD:
        pk = _pk(table)
        now = _utcnow()
        conn.execute(
            f"UPDATE {table} SET status='approved', approved_at=? WHERE {pk}=?",
            (now, item_id),
        )
        logger.info(
            "maybe_auto_approve: AUTO-APPROVED %s/%s (channel=%s, reviewed=%d)",
            table,
            item_id,
            channel,
            reviewed,
        )
        return True

    logger.debug(
        "maybe_auto_approve: still in probation channel=%s reviewed=%d/%d",
        channel,
        reviewed,
        PROBATION_THRESHOLD,
    )
    return False


# ---------------------------------------------------------------------------
# Background usage tracking
# ---------------------------------------------------------------------------

def log_background_use(conn: sqlite3.Connection, channel: str, bg_filename: str) -> None:
    """Record that *bg_filename* was used for a video on *channel*.

    No-op if the background_usage table does not exist yet.

    Args:
        conn:        Active SQLite connection.
        channel:     Channel slug.
        bg_filename: Basename of the background clip (e.g. "subwaysurfers.mp4").
    """
    try:
        conn.execute(
            "INSERT INTO background_usage (channel, bg_filename, used_at) VALUES (?, ?, ?)",
            (channel, bg_filename, _utcnow()),
        )
        logger.debug("log_background_use: channel=%s bg=%s", channel, bg_filename)
    except sqlite3.OperationalError:
        logger.debug("log_background_use: background_usage table missing, skipping")


def get_recent_backgrounds(
    conn: sqlite3.Connection, channel: str, limit: int = 5
) -> list[str]:
    """Return the last *limit* background filenames used for *channel*, newest first.

    Returns an empty list if the background_usage table does not exist yet
    (e.g. older databases before this table was introduced).

    Args:
        conn:    Active SQLite connection with row_factory=sqlite3.Row.
        channel: Channel slug.
        limit:   Number of recent entries to return (default 5).

    Returns:
        List of bg_filename strings, ordered by used_at DESC.
    """
    try:
        rows = conn.execute(
            "SELECT bg_filename FROM background_usage"
            " WHERE channel=? ORDER BY used_at DESC LIMIT ?",
            (channel, limit),
        ).fetchall()
        return [row["bg_filename"] for row in rows]
    except sqlite3.OperationalError:
        # Table not yet created — return empty list (no exclusions)
        logger.debug("get_recent_backgrounds: background_usage table missing, returning []")
        return []
