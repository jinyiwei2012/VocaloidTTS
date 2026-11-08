"""The manual release helper builds a source ZIP with the expected contents."""
from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.build_release import build, sha256


class ReleaseZipTests(unittest.TestCase):
    def test_source_zip_contains_sources_and_skips_ignored_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = build(Path(tmp) / "downloads")
            self.assertTrue(target.is_file())
            self.assertGreater(target.stat().st_size, 0)
            with zipfile.ZipFile(target) as archive:
                names = set(archive.namelist())
            self.assertIn("README.md", names)
            self.assertIn("vocaloidtts/app.py", names)
            self.assertFalse(any(name.startswith(".git/") for name in names))
            self.assertFalse(any(name.startswith("release_web/") for name in names))
            self.assertEqual(len(sha256(target)), 64)


if __name__ == "__main__":
    unittest.main()
