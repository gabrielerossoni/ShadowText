import subprocess
import sys
import unittest
from pathlib import Path


class CliInvocationTests(unittest.TestCase):
    def test_watcher_script_can_be_run_from_package_directory(self):
        repo_root = Path(__file__).resolve().parents[1]
        package_dir = repo_root / "censura_privacy"

        result = subprocess.run(
            [sys.executable, "watcher.py", "--help"],
            cwd=package_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Censura", result.stdout)


if __name__ == "__main__":
    unittest.main()
