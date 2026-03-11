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

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

EXAMPLE_YAML = (PROJECT_ROOT / "channels.yaml.example").read_text()

class TestChannelConfig(unittest.TestCase):

    def setUp(self):
        # Write channels.yaml from the example file for the duration of each test
        self.channels_yaml = PROJECT_ROOT / "channels.yaml"
        self.channels_yaml.write_text(EXAMPLE_YAML)
        # Reload config so it re-runs load_channels() with the fresh file
        import importlib
        import config
        importlib.reload(config)
        self.config = config

    def tearDown(self):
        if self.channels_yaml.exists():
            self.channels_yaml.unlink()

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

    def test_missing_channels_yaml_raises_clear_error(self):
        self.channels_yaml.unlink()
        import importlib
        import config as cfg_module
        with self.assertRaises((FileNotFoundError, SystemExit)):
            importlib.reload(cfg_module)
        # Restore for tearDown
        self.channels_yaml.write_text(EXAMPLE_YAML)


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestChannelConfig)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
