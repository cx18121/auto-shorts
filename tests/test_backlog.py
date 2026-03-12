"""
tests/test_backlog.py — RED test stubs for backlog module (BACKLOG-01, BACKLOG-02, BACKLOG-03,
REDDIT-03, QUALITY-03).

These tests will import-fail until pipeline/backlog.py is implemented in Plan 02-02.
Standalone: python3 tests/test_backlog.py
"""
import sqlite3
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# RED: ImportError expected until pipeline/backlog.py is built in Plan 02-02
from pipeline.backlog import (  # noqa: E402
    init_backlog_tables,
    insert_story,
    approve_story,
    reject_story,
    mark_story_used,
    get_approved_stories,
)


def _make_conn() -> sqlite3.Connection:
    """Create an in-memory SQLite connection with backlog tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_backlog_tables(conn)
    return conn


def _story_dict(**overrides) -> dict:
    base = {
        "id": "test-story-001",
        "channel": "relationships",
        "subreddit": "AITAH",
        "title": "AITA for not attending my sister's wedding?",
        "body": "Long story " * 100,
        "score": 5000,
        "word_count": 600,
        "scraped_at": "2026-03-11T00:00:00Z",
    }
    base.update(overrides)
    return base


class TestTablesCreated(unittest.TestCase):
    def test_tables_created(self):
        """init_backlog_tables creates backlog_stories, backlog_tweets, niche_state."""
        conn = sqlite3.connect(":memory:")
        init_backlog_tables(conn)
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertIn("backlog_stories", tables)
        self.assertIn("backlog_tweets", tables)
        self.assertIn("niche_state", tables)


class TestInsertStory(unittest.TestCase):
    def test_insert_story(self):
        """insert_story persists all fields to backlog_stories."""
        conn = _make_conn()
        story = _story_dict()
        insert_story(conn, story)
        row = conn.execute(
            "SELECT * FROM backlog_stories WHERE id = ?", (story["id"],)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["channel"], "relationships")
        self.assertEqual(row["subreddit"], "AITAH")
        self.assertEqual(row["score"], 5000)
        self.assertEqual(row["word_count"], 600)
        self.assertEqual(row["status"], "pending")
        self.assertIsNone(row["approved_at"])
        self.assertIsNone(row["used_at"])


class TestStatusTransitions(unittest.TestCase):
    def test_status_transitions_approve(self):
        """pending -> approve sets status='approved' and approved_at timestamp."""
        conn = _make_conn()
        story = _story_dict(id="story-approve")
        insert_story(conn, story)
        approve_story(conn, story["id"])
        row = conn.execute(
            "SELECT * FROM backlog_stories WHERE id = ?", (story["id"],)
        ).fetchone()
        self.assertEqual(row["status"], "approved")
        self.assertIsNotNone(row["approved_at"])

    def test_status_transitions_reject(self):
        """pending -> reject sets status='rejected'."""
        conn = _make_conn()
        story = _story_dict(id="story-reject")
        insert_story(conn, story)
        reject_story(conn, story["id"])
        row = conn.execute(
            "SELECT * FROM backlog_stories WHERE id = ?", (story["id"],)
        ).fetchone()
        self.assertEqual(row["status"], "rejected")

    def test_status_transitions_used(self):
        """approved -> used sets used_at timestamp."""
        conn = _make_conn()
        story = _story_dict(id="story-used")
        insert_story(conn, story)
        approve_story(conn, story["id"])
        mark_story_used(conn, story["id"])
        row = conn.execute(
            "SELECT * FROM backlog_stories WHERE id = ?", (story["id"],)
        ).fetchone()
        self.assertIsNotNone(row["used_at"])


class TestGetApprovedOnly(unittest.TestCase):
    def test_get_approved_only(self):
        """get_approved_stories returns only approved stories for the given channel."""
        conn = _make_conn()
        pending = _story_dict(id="p1", channel="relationships")
        approved = _story_dict(id="a1", channel="relationships")
        insert_story(conn, pending)
        insert_story(conn, approved)
        approve_story(conn, "a1")
        results = get_approved_stories(conn, "relationships")
        ids = [r["id"] for r in results]
        self.assertIn("a1", ids)
        self.assertNotIn("p1", ids)

    def test_rejected_not_in_approved(self):
        """get_approved_stories excludes rejected stories."""
        conn = _make_conn()
        story = _story_dict(id="r1", channel="relationships")
        insert_story(conn, story)
        reject_story(conn, "r1")
        results = get_approved_stories(conn, "relationships")
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
