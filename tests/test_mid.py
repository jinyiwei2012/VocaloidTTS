"""标准 MIDI 导出的结构回归。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vocaloidtts.formats import formats, mid
from vocaloidtts.prosody import VoiceOptions, compose


class MidExportTests(unittest.TestCase):
    def _export(self):
        song = compose("你好世界", VoiceOptions(seed=42))
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = mid.write_mid(song, str(Path(tmp.name) / "x.mid"))
        return song, path.read_bytes()

    def test_header_chunk(self) -> None:
        _, data = self._export()
        self.assertEqual(data[:4], b"MThd")
        self.assertEqual(int.from_bytes(data[4:8], "big"), 6)
        self.assertEqual(int.from_bytes(data[8:10], "big"), 0)    # format 0
        self.assertEqual(int.from_bytes(data[10:12], "big"), 1)   # 单轨
        self.assertEqual(int.from_bytes(data[12:14], "big"), mid.DIVISION)

    def test_track_has_lyrics_and_notes(self) -> None:
        _, data = self._export()
        self.assertIn(b"MTrk", data)
        self.assertIn(b"\xff\x05", data)    # lyric meta
        self.assertIn(b"\x90", data)        # note on
        self.assertIn(b"\x80", data)        # note off
        self.assertTrue(data.endswith(b"\xff\x2f\x00"))

    def test_empty_song_is_rejected(self) -> None:
        song = compose("", VoiceOptions(seed=1))
        with self.assertRaises(ValueError):
            mid.write_mid(song, "x.mid")

    def test_registry_lists_mid(self) -> None:
        self.assertEqual(formats()["mid"].extension, ".mid")


if __name__ == "__main__":
    unittest.main()
