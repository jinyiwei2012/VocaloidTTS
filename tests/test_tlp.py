"""TuneLab .tlp 导出的结构回归。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vocaloidtts.formats import formats, tlp
from vocaloidtts.prosody import VoiceOptions, compose


class TlpExportTests(unittest.TestCase):
    def _project(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = tlp.FORMAT.writer(compose("你好世界", VoiceOptions(seed=42)),
                                 str(Path(tmp.name) / "x.tlp"))
        return json.loads(path.read_text(encoding="utf-8"))

    def test_top_level(self) -> None:
        project = self._project()
        self.assertEqual(list(project), ["version", "tempos", "timeSignatures", "tracks"])
        self.assertEqual(project["tempos"], [{"pos": 0, "bpm": 120.0}])
        self.assertEqual(project["timeSignatures"],
                         [{"numerator": 4, "denominator": 4, "barIndex": 0}])
        self.assertEqual(len(project["tracks"]), 1)

    def test_notes(self) -> None:
        project = self._project()
        song = compose("你好世界", VoiceOptions(seed=42))
        notes = project["tracks"][0]["parts"][0]["notes"]
        self.assertEqual(len(notes), len(song.notes))
        first = notes[0]
        self.assertEqual(first["pos"], song.notes[0].start)
        self.assertEqual(first["dur"], song.notes[0].dur)
        self.assertEqual(first["pitch"], song.notes[0].midi)
        self.assertEqual(first["lyric"], "你")
        # 歌词和读音分开存
        self.assertEqual(first["pronunciation"], "ni")

    def test_pitch_is_absolute_and_flat(self) -> None:
        project = self._project()
        segments = project["tracks"][0]["parts"][0]["pitch"]
        self.assertEqual(len(segments), 1)
        flat = segments[0]
        self.assertEqual(len(flat) % 2, 0)
        # 绝对音高 = 音符 MIDI + PIT 偏移；PIT 的上限是 PBS 个半音
        song = compose("你好世界", VoiceOptions(seed=42))
        self.assertLessEqual(abs(flat[1] - song.notes[0].midi), song.options.pbs)
        # 横坐标单调不减
        xs = flat[0::2]
        self.assertEqual(xs, sorted(xs))

    def test_part_duration_is_bar_aligned(self) -> None:
        project = self._project()
        part = project["tracks"][0]["parts"][0]
        self.assertEqual(part["type"], "midi")
        self.assertEqual(part["dur"] % 1920, 0)

    def test_empty_song_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            tlp.write_tlp(compose("", VoiceOptions(seed=1)), "x.tlp")

    def test_registry(self) -> None:
        self.assertEqual(formats()["tlp"].extension, ".tlp")


if __name__ == "__main__":
    unittest.main()
