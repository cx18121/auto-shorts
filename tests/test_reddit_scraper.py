"""
tests/test_reddit_scraper.py — RED test stubs for Reddit scraper (REDDIT-01, REDDIT-04).

These tests will import-fail until pipeline/reddit_scraper.py is implemented in Plan 02-03.
Standalone: python3 tests/test_reddit_scraper.py
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# RED: ImportError expected until pipeline/reddit_scraper.py is built in Plan 02-03
from pipeline.reddit_scraper import (  # noqa: E402
    scrape_subreddit_top,
    scrape_channel_subreddits,
)


def _make_fake_post(
    post_id: str = "abc123",
    title: str = "Test story",
    selftext: str = "This is the body of the story " * 20,
    score: int = 5000,
    subreddit_name: str = "AITAH",
) -> MagicMock:
    """Build a mock praw Submission object."""
    post = MagicMock()
    post.id = post_id
    post.title = title
    post.selftext = selftext
    post.score = score
    post.subreddit.display_name = subreddit_name
    return post


class TestScrapeReturnsPosts(unittest.TestCase):
    def test_scrape_returns_posts(self):
        """scrape_subreddit_top returns list of dicts with required keys for valid posts."""
        mock_reddit = MagicMock()
        fake_posts = [
            _make_fake_post(post_id=f"id{i}", selftext="Valid selftext content " * 20)
            for i in range(3)
        ]
        mock_reddit.subreddit.return_value.top.return_value = iter(fake_posts)

        results = scrape_subreddit_top(mock_reddit, "AITAH", limit=10)

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
        """Posts with empty selftext are filtered out."""
        mock_reddit = MagicMock()
        bad_posts = [
            _make_fake_post(post_id="b1", selftext=""),
            _make_fake_post(post_id="b2", selftext="[removed]"),
            _make_fake_post(post_id="b3", selftext="[deleted]"),
        ]
        mock_reddit.subreddit.return_value.top.return_value = iter(bad_posts)

        results = scrape_subreddit_top(mock_reddit, "AITAH", limit=10)
        self.assertEqual(results, [])


class TestPerSubredditFailureIsolation(unittest.TestCase):
    def test_per_subreddit_failure_isolation(self):
        """A failing subreddit does not block other subreddits from returning posts."""
        channel_cfg = MagicMock()
        channel_cfg.subreddits = ["AITAH", "relationship_advice"]

        def side_effect(reddit, subreddit_name, time_filter="day", limit=25):
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

        mock_reddit = MagicMock()

        with patch("pipeline.reddit_scraper.scrape_subreddit_top", side_effect=side_effect):
            results = scrape_channel_subreddits(channel_cfg, mock_reddit)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["subreddit"], "relationship_advice")


if __name__ == "__main__":
    unittest.main()
