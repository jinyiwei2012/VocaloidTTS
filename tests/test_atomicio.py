"""Atomic writes keep the previous project intact when a render fails."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vocaloidtts.atomicio import atomic_write_bytes, atomic_write_text


class AtomicWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_writes_new_file_and_creates_parent(self) -> None:
        target = self.dir / "sub" / "a.txt"
        atomic_write_text(target, "hello\n")
        self.assertEqual(target.read_text(encoding="utf-8"), "hello\n")

    def test_replaces_existing_content(self) -> None:
        target = self.dir / "a.txt"
        target.write_bytes(b"old")
        atomic_write_bytes(target, b"new")
        self.assertEqual(target.read_bytes(), b"new")

    def test_failure_keeps_old_file_and_removes_tmp(self) -> None:
        target = self.dir / "a.txt"
        target.write_bytes(b"old")
        with patch("vocaloidtts.atomicio.os.replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                atomic_write_bytes(target, b"new")
        self.assertEqual(target.read_bytes(), b"old")
        self.assertEqual(list(self.dir.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
