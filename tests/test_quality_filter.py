"""
tests/test_quality_filter.py — RED test stubs for quality filter (REDDIT-02, QUALITY-01,
QUALITY-02).

These tests will import-fail until pipeline/quality_filter.py is implemented in Plan 02-04.
Standalone: python3 tests/test_quality_filter.py
"""
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# RED: ImportError expected until pipeline/quality_filter.py is built in Plan 02-04
from pipeline.quality_filter import (  # noqa: E402
    passes_story_quality,
    passes_tweet_quality,
)

QUALITY_STORY = {
    "min_upvotes": 1000,
    "min_words": 400,
    "max_words": 1200,
    "min_likes": 1000,
}

QUALITY_TWEET = {
    "min_upvotes": 500,
    "min_words": 200,
    "max_words": 800,
    "min_likes": 1000,
}


class TestStoryUpvoteFilter(unittest.TestCase):
    def test_story_upvote_filter_fails_below_min(self):
        """Story with score below min_upvotes returns (False, reason_string)."""
        result, reason = passes_story_quality(
            {"score": 999, "word_count": 500}, QUALITY_STORY
        )
        self.assertFalse(result)
        self.assertIsInstance(reason, str)
        self.assertTrue(len(reason) > 0)

    def test_story_upvote_filter_passes_at_min(self):
        """Story with score exactly at min_upvotes passes the upvote check."""
        result, reason = passes_story_quality(
            {"score": 1000, "word_count": 500}, QUALITY_STORY
        )
        self.assertTrue(result)
        self.assertEqual(reason, "")


class TestStoryWordCountBounds(unittest.TestCase):
    def test_word_count_below_min_fails(self):
        """Story with word_count below min_words returns (False, reason)."""
        result, reason = passes_story_quality(
            {"score": 5000, "word_count": 399}, QUALITY_STORY
        )
        self.assertFalse(result)
        self.assertTrue(len(reason) > 0)

    def test_word_count_above_max_fails(self):
        """Story with word_count above max_words returns (False, reason)."""
        result, reason = passes_story_quality(
            {"score": 5000, "word_count": 1201}, QUALITY_STORY
        )
        self.assertFalse(result)
        self.assertTrue(len(reason) > 0)

    def test_word_count_in_bounds_passes(self):
        """Story with word_count within bounds and sufficient score passes."""
        result, reason = passes_story_quality(
            {"score": 1500, "word_count": 600}, QUALITY_STORY
        )
        self.assertTrue(result)
        self.assertEqual(reason, "")


class TestTweetLikesFilter(unittest.TestCase):
    def test_tweet_likes_below_min_fails(self):
        """Tweet with likes below min_likes returns (False, reason)."""
        result, reason = passes_tweet_quality({"likes": 999}, QUALITY_TWEET)
        self.assertFalse(result)
        self.assertIsInstance(reason, str)
        self.assertTrue(len(reason) > 0)

    def test_tweet_likes_at_min_passes(self):
        """Tweet with likes exactly at min_likes returns (True, empty string)."""
        result, reason = passes_tweet_quality({"likes": 1000}, QUALITY_TWEET)
        self.assertTrue(result)
        self.assertEqual(reason, "")


if __name__ == "__main__":
    unittest.main()
