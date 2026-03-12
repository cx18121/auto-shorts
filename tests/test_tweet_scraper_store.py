"""
tests/test_tweet_scraper_store.py — Tests for scrape_and_store_tweets() (Plan 02-05).

Verifies:
- scrape_and_store_tweets uses channel_cfg.twitter_accounts (not global VIRAL_ACCOUNTS)
- Tweets failing quality thresholds are never inserted into backlog_tweets
- Tweets passing quality are inserted via insert_tweet (duplicates logged and skipped)
- Returns summary dict: {scraped, passed, inserted, duplicates}
- Browser leak fixed: try/finally present in _scrape_async
"""
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# scrape_and_store_tweets is imported at test time (not module level) to avoid
# triggering channels.yaml requirement from analysis.db -> config.py chain.


def _make_channel_cfg(
    slug: str = "test-channel",
    twitter_accounts: list[str] | None = None,
    min_likes: int = 500,
) -> MagicMock:
    """Build a minimal ChannelConfig mock."""
    cfg = MagicMock()
    cfg.slug = slug
    cfg.twitter_accounts = twitter_accounts or ["naval", "paulg"]
    cfg.quality = {"min_likes": min_likes}
    return cfg


def _make_tweet(
    tweet_id: str = "111",
    username: str = "testuser",
    tweet_text: str = "This is a great tweet with no URL",
    likes: int = 1000,
    retweets: int = 50,
) -> dict:
    """Build a minimal tweet dict matching the scraper output schema."""
    return {
        "tweet_id": tweet_id,
        "username": username,
        "tweet_text": tweet_text,
        "text": tweet_text,
        "likes": likes,
        "retweets": retweets,
        "score": likes + retweets * 3,
        "url": f"https://x.com/{username}/status/{tweet_id}",
        "display_name": username,
        "profile_image_url": None,
        "verified": False,
        "created_at": None,
    }


def _make_in_memory_conn() -> sqlite3.Connection:
    """Create an in-memory SQLite DB with backlog tables initialised."""
    from pipeline.backlog import init_backlog_tables
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_backlog_tables(conn)
    return conn


class TestScrapeAndStoreTweetsUsesChannelAccounts(unittest.TestCase):
    """scrape_and_store_tweets must use channel_cfg.twitter_accounts."""

    def test_uses_channel_accounts_not_viral_accounts(self):
        """scrape_top_tweets is called with channel_cfg.twitter_accounts."""
        from formats.tweets.scraper import scrape_and_store_tweets
        channel_cfg = _make_channel_cfg(twitter_accounts=["elonmusk", "naval"])
        conn = _make_in_memory_conn()

        with patch("formats.tweets.scraper.scrape_top_tweets", return_value=[]) as mock_scrape:
            scrape_and_store_tweets(channel_cfg, _conn=conn)

        mock_scrape.assert_called_once()
        call_kwargs = mock_scrape.call_args
        accounts_passed = call_kwargs.kwargs.get("accounts")
        self.assertEqual(accounts_passed, ["elonmusk", "naval"])

    def test_does_not_use_global_viral_accounts(self):
        """scrape_top_tweets must NOT receive VIRAL_ACCOUNTS as the accounts arg."""
        from formats.tweets.scraper import VIRAL_ACCOUNTS, scrape_and_store_tweets
        channel_cfg = _make_channel_cfg(twitter_accounts=["myaccount"])
        conn = _make_in_memory_conn()

        with patch("formats.tweets.scraper.scrape_top_tweets", return_value=[]) as mock_scrape:
            scrape_and_store_tweets(channel_cfg, _conn=conn)

        accounts_passed = mock_scrape.call_args.kwargs.get("accounts")
        self.assertNotEqual(accounts_passed, VIRAL_ACCOUNTS)


class TestScrapeAndStoreReturnsSummary(unittest.TestCase):
    """scrape_and_store_tweets returns the correct summary dict."""

    def test_returns_summary_dict_keys(self):
        """Return value has keys: scraped, passed, inserted, duplicates."""
        from formats.tweets.scraper import scrape_and_store_tweets
        channel_cfg = _make_channel_cfg()
        conn = _make_in_memory_conn()

        with patch("formats.tweets.scraper.scrape_top_tweets", return_value=[]):
            result = scrape_and_store_tweets(channel_cfg, _conn=conn)

        self.assertIn("scraped", result)
        self.assertIn("passed", result)
        self.assertIn("inserted", result)
        self.assertIn("duplicates", result)

    def test_summary_counts_empty_scrape(self):
        """All counts are zero when scrape returns no tweets."""
        from formats.tweets.scraper import scrape_and_store_tweets
        channel_cfg = _make_channel_cfg()
        conn = _make_in_memory_conn()

        with patch("formats.tweets.scraper.scrape_top_tweets", return_value=[]):
            result = scrape_and_store_tweets(channel_cfg, _conn=conn)

        self.assertEqual(result["scraped"], 0)
        self.assertEqual(result["passed"], 0)
        self.assertEqual(result["inserted"], 0)
        self.assertEqual(result["duplicates"], 0)


class TestScrapeAndStoreQualityFiltering(unittest.TestCase):
    """Tweets below quality thresholds are rejected and never inserted."""

    def test_tweet_below_min_likes_not_inserted(self):
        """A tweet with likes below min_likes is counted in scraped but not passed/inserted."""
        from formats.tweets.scraper import scrape_and_store_tweets
        channel_cfg = _make_channel_cfg(min_likes=1000)
        low_likes_tweet = _make_tweet(tweet_id="low1", likes=100)
        conn = _make_in_memory_conn()

        with patch("formats.tweets.scraper.scrape_top_tweets", return_value=[low_likes_tweet]):
            result = scrape_and_store_tweets(channel_cfg, _conn=conn)

        self.assertEqual(result["scraped"], 1)
        self.assertEqual(result["passed"], 0)
        self.assertEqual(result["inserted"], 0)

    def test_tweet_with_url_not_inserted(self):
        """A tweet containing a URL fails quality and is never inserted."""
        from formats.tweets.scraper import scrape_and_store_tweets
        channel_cfg = _make_channel_cfg(min_likes=100)
        url_tweet = _make_tweet(
            tweet_id="url1",
            tweet_text="Check this out https://example.com",
            likes=5000,
        )
        conn = _make_in_memory_conn()

        with patch("formats.tweets.scraper.scrape_top_tweets", return_value=[url_tweet]):
            result = scrape_and_store_tweets(channel_cfg, _conn=conn)

        self.assertEqual(result["scraped"], 1)
        self.assertEqual(result["passed"], 0)
        self.assertEqual(result["inserted"], 0)

    def test_passing_tweet_is_inserted(self):
        """A tweet that passes quality is counted in passed and inserted."""
        from formats.tweets.scraper import scrape_and_store_tweets
        channel_cfg = _make_channel_cfg(min_likes=500)
        good_tweet = _make_tweet(tweet_id="good1", likes=1000)
        conn = _make_in_memory_conn()

        with patch("formats.tweets.scraper.scrape_top_tweets", return_value=[good_tweet]):
            result = scrape_and_store_tweets(channel_cfg, _conn=conn)

        self.assertEqual(result["scraped"], 1)
        self.assertEqual(result["passed"], 1)
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["duplicates"], 0)

    def test_mixed_tweets_correct_counts(self):
        """With mixed quality tweets, counts reflect actual filtering."""
        from formats.tweets.scraper import scrape_and_store_tweets
        channel_cfg = _make_channel_cfg(min_likes=500)
        tweets = [
            _make_tweet(tweet_id="ok1", likes=1000),
            _make_tweet(tweet_id="bad1", likes=100),  # below threshold
            _make_tweet(tweet_id="ok2", likes=2000),
        ]
        conn = _make_in_memory_conn()

        with patch("formats.tweets.scraper.scrape_top_tweets", return_value=tweets):
            result = scrape_and_store_tweets(channel_cfg, _conn=conn)

        self.assertEqual(result["scraped"], 3)
        self.assertEqual(result["passed"], 2)
        self.assertEqual(result["inserted"], 2)
        self.assertEqual(result["duplicates"], 0)


class TestScrapeAndStoreDuplicates(unittest.TestCase):
    """Duplicate tweets are logged and skipped, not re-inserted."""

    def test_duplicate_counted_not_inserted_twice(self):
        """Running twice with same tweet: first inserts, second counts as duplicate."""
        from formats.tweets.scraper import scrape_and_store_tweets
        channel_cfg = _make_channel_cfg(min_likes=100)
        tweet = _make_tweet(tweet_id="dup1", likes=1000)
        conn = _make_in_memory_conn()

        with patch("formats.tweets.scraper.scrape_top_tweets", return_value=[tweet]):
            result1 = scrape_and_store_tweets(channel_cfg, _conn=conn)

        with patch("formats.tweets.scraper.scrape_top_tweets", return_value=[tweet]):
            result2 = scrape_and_store_tweets(channel_cfg, _conn=conn)

        self.assertEqual(result1["inserted"], 1)
        self.assertEqual(result1["duplicates"], 0)
        self.assertEqual(result2["inserted"], 0)
        self.assertEqual(result2["duplicates"], 1)

    def test_tweet_in_db_counted_as_duplicate(self):
        """Tweet already in DB (pre-inserted) is counted as duplicate."""
        from formats.tweets.scraper import scrape_and_store_tweets
        from pipeline.backlog import insert_tweet
        channel_cfg = _make_channel_cfg(min_likes=100)
        tweet = _make_tweet(tweet_id="preexist1", likes=2000)
        conn = _make_in_memory_conn()

        # Pre-insert the tweet directly
        insert_tweet(conn, {
            "tweet_id": tweet["tweet_id"],
            "channel": channel_cfg.slug,
            "username": tweet["username"],
            "tweet_text": tweet["tweet_text"],
            "likes": tweet["likes"],
            "retweets": tweet["retweets"],
        })

        with patch("formats.tweets.scraper.scrape_top_tweets", return_value=[tweet]):
            result = scrape_and_store_tweets(channel_cfg, _conn=conn)

        self.assertEqual(result["inserted"], 0)
        self.assertEqual(result["duplicates"], 1)


class TestBrowserLeakFix(unittest.TestCase):
    """Verify the try/finally browser leak fix is present in source."""

    def test_try_finally_in_scrape_async(self):
        """_scrape_async source must contain 'finally' to close browser on exception."""
        import inspect
        from formats.tweets import scraper
        src = inspect.getsource(scraper._scrape_async)
        self.assertIn("finally", src, "_scrape_async must use try/finally for browser.close()")
        self.assertIn("browser.close()", src)


if __name__ == "__main__":
    unittest.main()
