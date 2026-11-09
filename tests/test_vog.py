"""Vogen .vog 导出的结构回归。

.vog 是 zip 包，里面只有 chart.json，所以测试要解压后再核对字段。
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from vocaloidtts.formats import formats, vog
from vocaloidtts.prosody import VoiceOptions, compose


def _song():
    return compose("你好世界", VoiceOptions(seed=42))


class VogExportTests(unittest.TestCase):
    def _read(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = vog.FORMAT.writer(_song(), str(Path(tmp.name) / "x.vog"))
        with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as archive:
            names = archive.namelist()
            payload = archive.read("chart.json")
        return names, json.loads(payload)

    def test_container(self) -> None:
        names, _ = self._read()
        self.assertEqual(names, ["chart.json"])

    def test_top_level(self) -> None:
        _, project = self._read()
        self.assertEqual(project["timeSig0"], "4/4")
        self.assertEqual(project["bpm0"], 120.0)
        self.assertEqual(project["accomOffset"], 0)
        self.assertEqual(len(project["utts"]), 1)

    def test_track_and_notes(self) -> None:
        _, project = self._read()
        track = project["utts"][0]
        self.assertEqual(track["name"], "VocaloidTTS")
        self.assertIsNone(track["singerId"])
        notes = track["notes"]
        song = _song()
        self.assertEqual(len(notes), len(song.notes))
        first = notes[0]
        self.assertEqual(first["pitch"], song.notes[0].midi)
        self.assertEqual(first["on"], song.notes[0].start)
        self.assertEqual(first["dur"], song.notes[0].dur)
        self.assertEqual(first["lyric"], "你")
        self.assertEqual(first["rom"], "ni")

    def test_empty_song_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            vog.write_vog(compose("", VoiceOptions(seed=1)), "x.vog")

    def test_registry(self) -> None:
        self.assertEqual(formats()["vog"].extension, ".vog")


if __name__ == "__main__":
    unittest.main()
