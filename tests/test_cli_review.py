"""
tests/test_cli_review.py — RED test stub for CLI review command (BACKLOG-04).

Standalone: python3 tests/test_cli_review.py
"""
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
PYTHON = sys.executable


class TestCliReview(unittest.TestCase):

    @unittest.skip(
        "Integration stub — requires backlog data setup. "
        "Full integration test needs: a channel config, a seeded pipeline.db with at least one "
        "pending story, and subprocess.run with stdin='y\\n' to simulate user approval. "
        "Implement after Plan 02-02 (backlog module) and Plan 02-05 (CLI review command) are "
        "complete. At that point: create temp DB, insert pending story, run "
        "'python main.py --channel relationships review' with piped stdin, "
        "then assert the story status changed to 'approved' in the DB."
    )
    def test_review_approve(self):
        """CLI review command transitions a pending story to approved on 'y' input."""
        import subprocess

        result = subprocess.run(
            [PYTHON, str(PROJECT_ROOT / "main.py"), "--channel", "relationships", "review"],
            input="y\n",
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        # Assert backlog item transitions to approved after y input
        # (full implementation after Plans 02-02 and 02-05 are complete)
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
