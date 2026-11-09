"""Synthesizer V Studio 2 .s5p 导出的结构回归。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vocaloidtts.formats import formats, s5p
from vocaloidtts.prosody import VoiceOptions, compose


class S5pExportTests(unittest.TestCase):
    def _song(self):
        return compose("你好世界", VoiceOptions(seed=42))

    def _export(self):
        song = self._song()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = s5p.write_s5p(song, str(Path(tmp.name) / "x.s5p"))
        return song, path, json.loads(path.read_text(encoding="utf-8"))

    def test_top_level_shape(self) -> None:
        song, path, project = self._export()
        self.assertEqual(path.suffix, ".s5p")
        self.assertEqual(project["version"], s5p.PROJECT_VERSION)
        self.assertEqual(project["meter"],
                         [{"measure": 0, "beatPerMeasure": song.numerator,
                           "beatGranularity": song.denominator}])
        self.assertEqual(project["tempo"], [{"position": 0,
                                             "beatPerMinute": song.bpm}])
        self.assertEqual(project["instrumental"], {"filename": "", "offset": 0.0})
        self.assertEqual(len(project["tracks"]), 1)

    def test_notes_use_blicks(self) -> None:
        song, _, project = self._export()
        notes = project["tracks"][0]["notes"]
        self.assertEqual(len(notes), len(song.notes))
        first = notes[0]
        self.assertEqual(first["onset"], song.notes[0].start * s5p.BLICK_PER_TICK)
        self.assertEqual(first["duration"],
                         song.notes[0].dur * s5p.BLICK_PER_TICK)
        self.assertEqual(first["pitch"], song.notes[0].midi)
        # 可选字段一律 null，交给 dbDefaults
        for name in s5p.NOTE_OPTIONAL_FIELDS:
            self.assertIsNone(first[name], name)

    def test_track_defaults(self) -> None:
        _, _, project = self._export()
        track = project["tracks"][0]
        self.assertEqual(track["dbDefaults"], s5p.DB_DEFAULTS)
        self.assertEqual(track["parameters"]["interval"], s5p.PARAM_INTERVAL)
        self.assertEqual(track["parameters"]["pitchDelta"], [])
        self.assertIsNone(track["gsEvents"])
        self.assertTrue(track["mixer"]["engineOn"])

    def test_chinese_lyric_matches_the_svp_writer(self) -> None:
        """两种 SynthV 工程的歌词口径要一致：中文写汉字。"""
        song = self._song()
        project = s5p.build_project(song)
        notes = project["tracks"][0]["notes"]
        self.assertEqual([n["lyric"] for n in notes], list("你好世界"))

    def test_resolution_is_rescaled(self) -> None:
        song = self._song()
        song.resolution = 960
        project = s5p.build_project(song)
        second = project["tracks"][0]["notes"][1]
        self.assertNotEqual(song.notes[1].start, 0)   # 前提：这条不是零起点
        self.assertEqual(second["onset"],
                         round(song.notes[1].start * s5p.BLICK_PER_TICK * 480 / 960))

    def test_empty_song_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            s5p.write_s5p(compose("", VoiceOptions(seed=1)), "x.s5p")

    def test_registry_lists_s5p(self) -> None:
        self.assertIn("s5p", formats())
        self.assertEqual(formats()["s5p"].extension, ".s5p")


if __name__ == "__main__":
    unittest.main()
