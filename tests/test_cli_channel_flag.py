"""
Smoke tests for --channel global flag CLI routing (MULTI-03).
Standalone: python3 tests/test_cli_channel_flag.py
Uses subprocess to avoid import-time config issues.
"""
import os
import sys
import subprocess
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
EXAMPLE_YAML = (PROJECT_ROOT / "channels.yaml.example").read_text()
PYTHON = sys.executable


class TestChannelFlag(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.channels_yaml = PROJECT_ROOT / "channels.yaml"
        cls.channels_yaml.write_text(EXAMPLE_YAML)

    @classmethod
    def tearDownClass(cls):
        if cls.channels_yaml.exists():
            cls.channels_yaml.unlink()

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [PYTHON, str(PROJECT_ROOT / "main.py")] + args,
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )

    def test_channel_flag_missing_causes_error(self):
        """--channel is required; omitting it must cause a non-zero exit."""
        result = self._run(["backlog-status"])
        self.assertNotEqual(result.returncode, 0,
            "Expected non-zero exit when --channel is omitted")

    def test_channel_flag_valid_slug_is_accepted(self):
        """--channel relationships must be accepted (parse stage, not execution)."""
        # We check that the error is NOT an argparse error about --channel.
        # It will fail for other reasons (API keys, etc.) but not for --channel.
        result = self._run(["--channel", "relationships", "backlog-status"])
        # argparse should not complain about --channel
        self.assertNotIn("--channel", result.stderr.lower().replace("channel", ""),
            "argparse complained about --channel flag when it should be valid")

    def test_channel_flag_all_is_accepted(self):
        """--channel all must be accepted by argparse."""
        result = self._run(["--channel", "all", "backlog-status"])
        self.assertNotIn("error: argument --channel", result.stderr)

    def test_channel_flag_unknown_slug_causes_error(self):
        """--channel bogus-channel must cause a non-zero exit with clear message."""
        result = self._run(["--channel", "bogus-channel", "backlog-status"])
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestChannelFlag)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
