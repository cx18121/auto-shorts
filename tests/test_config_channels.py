"""
Tests for multi-channel config loading (NICHE-01, NICHE-02, NICHE-03, MULTI-01).
Standalone: python3 tests/test_config_channels.py
"""
import os
import sys
import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

EXAMPLE_YAML = (PROJECT_ROOT / "channels.yaml.example").read_text()

# Build the mock config that other test files (test_run_cycle, test_story_generator) rely on.
# tearDown restores this after each test so config-mocked tests running AFTER this file still work.
_SHARED_MOCK_CONFIG = MagicMock()
_SHARED_MOCK_CONFIG.ANTHROPIC_API_KEY = "test-api-key"
_SHARED_MOCK_CONFIG.OUTPUT_DIR = Path("/tmp/test_output")
_SHARED_MOCK_CONFIG.ASSETS_DIR = Path("/tmp/test_assets")
_SHARED_MOCK_CONFIG.CHANNELS_DIR = Path("/tmp/test_channels")
_SHARED_MOCK_CONFIG.CHANNELS = {}


class TestChannelConfig(unittest.TestCase):

    def setUp(self):
        # Write channels.yaml from the example file for the duration of each test
        self.channels_yaml = PROJECT_ROOT / "channels.yaml"
        self.channels_yaml.write_text(EXAMPLE_YAML)
        # Ensure we load the REAL config module, not a test mock injected by other test files
        import importlib
        if "config" in sys.modules:
            del sys.modules["config"]
        import config
        importlib.reload(config)
        self.config = config

    def tearDown(self):
        if self.channels_yaml.exists():
            self.channels_yaml.unlink()
        # Remove the real config from sys.modules and restore the shared mock so that
        # test files running after this one (test_run_cycle, test_story_generator) still
        # find a mock config and do not trigger channels.yaml SystemExit.
        if "config" in sys.modules:
            del sys.modules["config"]
        sys.modules["config"] = _SHARED_MOCK_CONFIG

    def test_load_channels_returns_three_slugs(self):
        self.assertEqual(
            set(self.config.CHANNELS.keys()),
            {"hypothetical-scenarios", "relationships", "finance-hustle"},
        )

    def test_channel_config_has_required_fields(self):
        cfg = self.config.CHANNELS["relationships"]
        self.assertTrue(hasattr(cfg, "slug"))
        self.assertTrue(hasattr(cfg, "name"))
        self.assertTrue(hasattr(cfg, "format"))
        self.assertTrue(hasattr(cfg, "voice_id"))
        self.assertTrue(hasattr(cfg, "subreddits"))
        self.assertTrue(hasattr(cfg, "twitter_accounts"))

    def test_get_channel_valid(self):
        cfg = self.config.get_channel("relationships")
        self.assertEqual(cfg.name, "Relationships")
        self.assertEqual(cfg.format, "storytelling")
        self.assertGreater(len(cfg.subreddits), 0)

    def test_get_channel_finance_hustle_is_tweets(self):
        cfg = self.config.get_channel("finance-hustle")
        self.assertEqual(cfg.format, "tweets")

    def test_get_channel_invalid_raises_system_exit(self):
        with self.assertRaises(SystemExit):
            self.config.get_channel("nonexistent-channel")

    def test_per_channel_dirs_created(self):
        channels_data_dir = PROJECT_ROOT / "data" / "channels"
        for slug in ["hypothetical-scenarios", "relationships", "finance-hustle"]:
            self.assertTrue(
                (channels_data_dir / slug).is_dir(),
                f"Expected data/channels/{slug}/ to exist after load_channels()",
            )

    def test_style_profile_optional(self):
        """ChannelConfig loads successfully when style_profile is absent from YAML (empty string default)."""
        cfg = self.config.CHANNELS["hypothetical-scenarios"]
        self.assertTrue(hasattr(cfg, "style_profile"))
        # style_profile defaults to empty string when not set
        self.assertIsInstance(cfg.style_profile, str)

    def test_style_profile_set(self):
        """ChannelConfig accepts style_profile field and stores it."""
        import yaml
        import importlib
        custom_yaml = EXAMPLE_YAML.replace(
            'style_profile: ""  # Path to style profile JSON (optional — omit or leave empty to use niche defaults)\n\nrelationships:',
            'style_profile: "style_profiles/test.json"  # Path to style profile JSON\n\nrelationships:',
        )
        self.channels_yaml.write_text(custom_yaml)
        import config as cfg_module
        importlib.reload(cfg_module)
        cfg = cfg_module.CHANNELS["hypothetical-scenarios"]
        self.assertEqual(cfg.style_profile, "style_profiles/test.json")
        # Restore original for other tests
        importlib.reload(self.config)

    def test_missing_channels_yaml_raises_clear_error(self):
        self.channels_yaml.unlink()
        import importlib
        import config as cfg_module
        with self.assertRaises((FileNotFoundError, SystemExit)):
            importlib.reload(cfg_module)
        # Restore for tearDown
        self.channels_yaml.write_text(EXAMPLE_YAML)

    def test_enabled_defaults_to_true_when_missing(self):
        """ChannelConfig.enabled defaults to True when not present in YAML."""
        import importlib
        import yaml
        # Build a minimal YAML without 'enabled' key
        minimal_yaml = (
            "hypothetical-scenarios:\n"
            "  name: Test\n"
            "  format: storytelling\n"
            "  voice_id: v1\n"
            "  subreddits:\n"
            "    - AskReddit\n"
            "  twitter_accounts: []\n"
        )
        self.channels_yaml.write_text(minimal_yaml)
        import config as cfg_module
        importlib.reload(cfg_module)
        cfg = cfg_module.CHANNELS["hypothetical-scenarios"]
        self.assertTrue(cfg.enabled)
        # Restore original
        self.channels_yaml.write_text(EXAMPLE_YAML)
        importlib.reload(cfg_module)

    def test_hashtags_defaults_to_empty_list_when_missing(self):
        """ChannelConfig.hashtags defaults to [] when not present in YAML."""
        import importlib
        # Build a minimal YAML without 'hashtags' key
        minimal_yaml = (
            "hypothetical-scenarios:\n"
            "  name: Test\n"
            "  format: storytelling\n"
            "  voice_id: v1\n"
            "  subreddits:\n"
            "    - AskReddit\n"
            "  twitter_accounts: []\n"
        )
        self.channels_yaml.write_text(minimal_yaml)
        import config as cfg_module
        importlib.reload(cfg_module)
        cfg = cfg_module.CHANNELS["hypothetical-scenarios"]
        self.assertEqual(cfg.hashtags, [])
        # Restore original
        self.channels_yaml.write_text(EXAMPLE_YAML)
        importlib.reload(cfg_module)

    def test_new_fields_loaded_from_yaml(self):
        """enabled, hashtags, and instagram_user_id are loaded correctly from YAML."""
        import importlib
        cfg = self.config.CHANNELS["hypothetical-scenarios"]
        # From channels.yaml.example
        self.assertTrue(cfg.enabled)
        self.assertIsInstance(cfg.hashtags, list)
        self.assertGreater(len(cfg.hashtags), 0)
        self.assertIn("shorts", cfg.hashtags)
        self.assertIsInstance(cfg.instagram_user_id, str)
        # Default is empty string
        self.assertEqual(cfg.instagram_user_id, "")


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestChannelConfig)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
