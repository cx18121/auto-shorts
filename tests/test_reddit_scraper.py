"""
tests/test_reddit_scraper.py — Tests for pipeline/reddit_scraper.py.

The scraper uses requests.get against reddit.com/.json (no PRAW).

Standalone: python3 tests/test_reddit_scraper.py
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.reddit_scraper import (  # noqa: E402
    scrape_subreddit_top,
    scrape_channel_subreddits,
)


class TestScrapeReturnsPosts(unittest.TestCase):
    def test_scrape_returns_posts(self):
        """scrape_subreddit_top returns list of dicts with required keys for valid posts."""
        fake_children = [
            {
                "data": {
                    "id": f"id{i}",
                    "is_self": True,
                    "selftext": "Valid selftext content " * 20,
                    "title": "Test story",
                    "score": 5000,
                    "permalink": f"/r/AITAH/comments/id{i}/test/",
                }
            }
            for i in range(3)
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {"children": fake_children, "after": None}
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("pipeline.reddit_scraper.requests.get", return_value=mock_resp) as mock_get:
            results = scrape_subreddit_top("AITAH", limit=10)

        self.assertEqual(len(results), 3)
        for r in results:
            self.assertIn("id", r)
            self.assertIn("title", r)
            self.assertIn("body", r)
            self.assertIn("score", r)
            self.assertIn("word_count", r)
            self.assertIn("subreddit", r)


class TestSelftextFilter(unittest.TestCase):
    def test_selftext_filter_empty(self):
        """Posts with empty/removed/deleted selftext are filtered out."""
        fake_children = [
            {"data": {"id": "b1", "is_self": True, "selftext": "", "title": "T", "score": 100, "permalink": "/r/AITAH/b1/"}},
            {"data": {"id": "b2", "is_self": True, "selftext": "[removed]", "title": "T", "score": 100, "permalink": "/r/AITAH/b2/"}},
            {"data": {"id": "b3", "is_self": True, "selftext": "[deleted]", "title": "T", "score": 100, "permalink": "/r/AITAH/b3/"}},
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {"children": fake_children, "after": None}
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("pipeline.reddit_scraper.requests.get", return_value=mock_resp):
            results = scrape_subreddit_top("AITAH", limit=10)

        self.assertEqual(results, [])


class TestPerSubredditFailureIsolation(unittest.TestCase):
    def test_per_subreddit_failure_isolation(self):
        """A failing subreddit does not block other subreddits from returning posts."""
        channel_cfg = MagicMock()
        channel_cfg.subreddits = ["AITAH", "relationship_advice"]

        def side_effect(subreddit_name, time_filter="day", limit=25):
            if subreddit_name == "AITAH":
                raise Exception("Network error")
            return [
                {
                    "id": "ok1",
                    "title": "Good post",
                    "body": "Content here",
                    "score": 3000,
                    "word_count": 200,
                    "subreddit": "relationship_advice",
                }
            ]

        with patch("pipeline.reddit_scraper.scrape_subreddit_top", side_effect=side_effect):
            results = scrape_channel_subreddits(channel_cfg)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["subreddit"], "relationship_advice")


if __name__ == "__main__":
    unittest.main()
