"""The package version is the single source of truth for docs and the page."""
from __future__ import annotations

import unittest
from pathlib import Path

from vocaloidtts import __version__


class VersionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parent.parent

    def test_readme_mentions_current_version(self) -> None:
        readme = (self.root / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"v{__version__}", readme)

    def test_release_page_title_matches(self) -> None:
        page = (self.root / "release_web" / "index.html").read_text(encoding="utf-8")
        self.assertIn(f"VocaloidTTS {__version__}", page)


if __name__ == "__main__":
    unittest.main()
