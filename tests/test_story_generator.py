"""
Tests for formats/storytelling/generator.py — adapt_reddit_post, _build_reddit_prompt,
_NICHE_TONES, and enhanced _validate (GEN-01, GEN-02, GEN-03).

Standalone: python3 tests/test_story_generator.py
"""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Mock config before any import that triggers config.py (which calls load_channels at import time)
from unittest.mock import MagicMock as _MagicMock  # noqa: E402
_mock_config = _MagicMock()
_mock_config.ANTHROPIC_API_KEY = "test-api-key"
_mock_config.CHANNELS = {}
sys.modules.setdefault("config", _mock_config)
# NOTE: Do NOT mock pipeline.claude_utils — it is a pure utility with no config dependency,
# and generator.py binds parse_json from it at import time.

# ---------------------------------------------------------------------------
# Canned mock response for Anthropic API
# ---------------------------------------------------------------------------
_MOCK_STORY_TEXT = (
    "Have you ever wondered what it would be like if the world ran out of coffee? "
    "Picture this: one morning you wake up and every coffee shop is closed, every "
    "supermarket shelf is empty. People stumble into work half-asleep, productivity "
    "plummets, and tempers flare. Scientists scramble for an alternative, but nothing "
    "compares. Society starts to unravel at the edges, all because of a single bean."
)
_MOCK_RESPONSE_JSON = json.dumps({
    "title": "What If The World Ran Out Of Coffee",
    "hook_line": "Have you ever wondered what it would be like if the world ran out of coffee?",
    "story_text": _MOCK_STORY_TEXT,
    "overlay_phrases": [
        "world ran out of coffee",
        "every coffee shop is closed",
        "productivity plummets",
        "Scientists scramble for an alternative",
        "Society starts to unravel",
    ],
    "estimated_duration_seconds": 52,
})

_SAMPLE_POST = {
    "title": "What would happen if the world ran out of coffee?",
    "body": (
        "I've been thinking about this scenario a lot lately. "
        "Coffee is such a fundamental part of modern society — what would happen "
        "if all the coffee plants died from some disease? Would society collapse? "
        "Would we find an alternative? Would productivity just tank completely? "
        "Throwaway because my main gets too much attention on AskReddit. "
        "Edit: wow this blew up, thanks for the awards everyone! "
        "I think the economic impact alone would be devastating. The coffee industry "
        "employs millions worldwide. AITA for thinking this would actually be fine though? "
        "NTA btw. Let me know your thoughts in the comments and upvote if you agree."
    ),
}


def _make_mock_client(response_json: str = _MOCK_RESPONSE_JSON):
    """Build a mock Anthropic client that returns response_json from resp.content[0].text."""
    mock_content = MagicMock()
    mock_content.text = response_json
    mock_resp = MagicMock()
    mock_resp.content = [mock_content]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_resp
    return mock_client


# ---------------------------------------------------------------------------
# TestNicheTones
# ---------------------------------------------------------------------------

class TestNicheTones(unittest.TestCase):
    """Tests for the _NICHE_TONES module-level dict."""

    def setUp(self):
        from formats.storytelling import generator
        self.generator = generator

    def test_niche_tones_has_hypothetical_scenarios(self):
        """_NICHE_TONES contains an entry for hypothetical-scenarios."""
        self.assertIn("hypothetical-scenarios", self.generator._NICHE_TONES)

    def test_niche_tones_has_relationships(self):
        """_NICHE_TONES contains an entry for relationships."""
        self.assertIn("relationships", self.generator._NICHE_TONES)

    def test_hypothetical_tone_contains_contemplative(self):
        """hypothetical-scenarios tone directive includes 'contemplative'."""
        tone = self.generator._NICHE_TONES["hypothetical-scenarios"]
        self.assertIn("contemplative", tone.lower())

    def test_relationships_tone_contains_empathy(self):
        """relationships tone directive includes 'empathy' or 'empathetic'."""
        tone = self.generator._NICHE_TONES["relationships"]
        self.assertTrue(
            "empathy" in tone.lower() or "empathetic" in tone.lower(),
            f"Expected 'empathy' or 'empathetic' in relationships tone, got: {tone!r}",
        )


# ---------------------------------------------------------------------------
# TestBuildRedditPrompt
# ---------------------------------------------------------------------------

class TestBuildRedditPrompt(unittest.TestCase):
    """Tests for _build_reddit_prompt() branching logic."""

    def setUp(self):
        from formats.storytelling import generator
        self.generator = generator

    def test_niche_tone_hypothetical(self):
        """_build_reddit_prompt without profile includes 'contemplative' for hypothetical-scenarios."""
        prompt = self.generator._build_reddit_prompt(
            _SAMPLE_POST, "hypothetical-scenarios", None
        )
        self.assertIn("contemplative", prompt.lower())

    def test_niche_tone_relationships(self):
        """_build_reddit_prompt without profile includes 'empathy' for relationships."""
        prompt = self.generator._build_reddit_prompt(
            _SAMPLE_POST, "relationships", None
        )
        self.assertTrue(
            "empathy" in prompt.lower() or "empathetic" in prompt.lower(),
            f"Expected empathy/empathetic in prompt for relationships",
        )

    def test_profile_overrides_niche(self):
        """_build_reddit_prompt with profile uses profile's tone, not niche defaults."""
        profile = {
            "generation_prompt_guidance": "Be extremely dramatic and suspenseful.",
            "content_style": {
                "tone": "dramatic thriller",
                "hook_patterns": ["shocking revelation", "cliffhanger"],
                "ideal_duration_seconds": {"min": 55, "max": 70},
                "ideal_word_count": {"min": 120, "max": 180},
            },
            "vocabulary_notes": "Use vivid action verbs.",
        }
        prompt = self.generator._build_reddit_prompt(
            _SAMPLE_POST, "hypothetical-scenarios", profile
        )
        # Profile guidance should appear, not the default niche tone
        self.assertIn("dramatic", prompt.lower())
        self.assertIn("Be extremely dramatic and suspenseful.", prompt)
        # The niche default 'contemplative' should NOT appear when profile is provided
        self.assertNotIn("contemplative", prompt.lower())

    def test_no_profile_uses_default_duration(self):
        """_build_reddit_prompt without profile targets 45–60 seconds."""
        prompt = self.generator._build_reddit_prompt(
            _SAMPLE_POST, "hypothetical-scenarios", None
        )
        self.assertIn("45", prompt)
        self.assertIn("60", prompt)

    def test_post_title_and_body_in_prompt(self):
        """_build_reddit_prompt includes post title and body in the output."""
        prompt = self.generator._build_reddit_prompt(
            _SAMPLE_POST, "relationships", None
        )
        self.assertIn(_SAMPLE_POST["title"], prompt)
        # Body is truncated to 4000 chars, but first 50 chars should be present
        self.assertIn(_SAMPLE_POST["body"][:50], prompt)


# ---------------------------------------------------------------------------
# TestValidate
# ---------------------------------------------------------------------------

class TestValidate(unittest.TestCase):
    """Tests for the enhanced _validate() function."""

    def setUp(self):
        from formats.storytelling import generator
        self.generator = generator

    def _make_valid_story(self):
        return {
            "title": "Test Title",
            "hook_line": "This is the hook.",
            "story_text": "This is the full story text. It has multiple sentences.",
            "overlay_phrases": ["the full story text", "multiple sentences"],
            "estimated_duration_seconds": 45,
        }

    def test_valid_story_passes(self):
        """_validate() does not raise for a fully valid story dict."""
        story = self._make_valid_story()
        # Should not raise
        self.generator._validate(story)

    def test_overlay_phrases_are_substrings_valid(self):
        """_validate() passes when all overlay_phrases are exact substrings of story_text."""
        story = self._make_valid_story()
        # All phrases are substrings — should pass silently
        self.generator._validate(story)

    def test_overlay_phrases_are_substrings_invalid(self):
        """_validate() raises ValueError when an overlay_phrase is not in story_text."""
        story = self._make_valid_story()
        story["overlay_phrases"] = [
            "the full story text",
            "this phrase does not appear in story",  # not a substring
        ]
        with self.assertRaises(ValueError):
            self.generator._validate(story)

    def test_missing_required_key_raises(self):
        """_validate() raises ValueError when a required key is missing."""
        story = self._make_valid_story()
        del story["hook_line"]
        with self.assertRaises(ValueError):
            self.generator._validate(story)

    def test_empty_story_text_raises(self):
        """_validate() raises ValueError when story_text is empty."""
        story = self._make_valid_story()
        story["story_text"] = ""
        with self.assertRaises(ValueError):
            self.generator._validate(story)


# ---------------------------------------------------------------------------
# TestAdaptRedditPost
# ---------------------------------------------------------------------------

class TestAdaptRedditPost(unittest.TestCase):
    """Tests for adapt_reddit_post() — mocks the Anthropic client."""

    def setUp(self):
        from formats.storytelling import generator
        self.generator = generator

    def _call_adapt(self, post=None, channel_slug="hypothetical-scenarios",
                    profile=None, response_json=_MOCK_RESPONSE_JSON):
        """Call adapt_reddit_post with a mocked Anthropic client."""
        if post is None:
            post = _SAMPLE_POST
        with patch("anthropic.Anthropic", return_value=_make_mock_client(response_json)):
            return self.generator.adapt_reddit_post(post, channel_slug, profile)

    def test_output_schema(self):
        """adapt_reddit_post() returns dict with all 5 required keys."""
        result = self._call_adapt()
        required = {"title", "hook_line", "story_text", "overlay_phrases", "estimated_duration_seconds"}
        self.assertEqual(required, result.keys() & required)
        for key in required:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_reddit_jargon_stripped(self):
        """Output story_text does not contain AITA, NTA, or 'throwaway'."""
        result = self._call_adapt()
        story_text = result["story_text"].lower()
        for jargon in ["aita", "nta", "throwaway"]:
            self.assertNotIn(
                jargon, story_text,
                f"Found Reddit jargon '{jargon}' in story_text: {result['story_text']!r}",
            )

    def test_duration_in_range(self):
        """estimated_duration_seconds is between 30 and 90."""
        result = self._call_adapt()
        duration = result["estimated_duration_seconds"]
        self.assertGreaterEqual(duration, 30, f"Duration {duration} < 30")
        self.assertLessEqual(duration, 90, f"Duration {duration} > 90")

    def test_no_markdown(self):
        """story_text contains no markdown characters (**, ##, __, `)."""
        result = self._call_adapt()
        story_text = result["story_text"]
        for md_marker in ["**", "##", "__", "`", "* "]:
            self.assertNotIn(
                md_marker, story_text,
                f"Found markdown marker '{md_marker}' in story_text",
            )

    def test_overlay_phrases_are_substrings_of_story_text(self):
        """Each overlay_phrase is an exact substring of story_text."""
        result = self._call_adapt()
        story_text = result["story_text"]
        for phrase in result["overlay_phrases"]:
            self.assertIn(
                phrase, story_text,
                f"overlay_phrase {phrase!r} is not a substring of story_text",
            )

    def test_short_body_raises_value_error(self):
        """adapt_reddit_post raises ValueError when post body is < 50 words."""
        short_post = {
            "title": "Some title",
            "body": "Too short.",
        }
        with patch("anthropic.Anthropic", return_value=_make_mock_client()):
            with self.assertRaises(ValueError):
                self.generator.adapt_reddit_post(short_post, "relationships")

    def test_uses_reddit_system_prompt(self):
        """adapt_reddit_post uses _REDDIT_SYSTEM_PROMPT, not _SYSTEM_PROMPT."""
        mock_client = _make_mock_client()
        with patch("anthropic.Anthropic", return_value=mock_client):
            self.generator.adapt_reddit_post(_SAMPLE_POST, "hypothetical-scenarios")
        call_kwargs = mock_client.messages.create.call_args
        system_arg = call_kwargs.kwargs.get("system") or call_kwargs.args[2] if len(call_kwargs.args) > 2 else None
        if system_arg is None:
            # Try keyword args
            system_arg = call_kwargs.kwargs.get("system")
        # The system prompt should mention "adapt" or "Reddit" (reddit-specific variant)
        self.assertIsNotNone(system_arg)
        self.assertTrue(
            "adapt" in system_arg.lower() or "reddit" in system_arg.lower(),
            f"Expected reddit-adaptation system prompt, got: {system_arg!r}",
        )


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestNicheTones))
    suite.addTests(loader.loadTestsFromTestCase(TestBuildRedditPrompt))
    suite.addTests(loader.loadTestsFromTestCase(TestValidate))
    suite.addTests(loader.loadTestsFromTestCase(TestAdaptRedditPost))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
