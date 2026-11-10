"""ACE Virtual Singer（手机版）.ace 导出的结构回归。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vocaloidtts.formats import ace, formats
from vocaloidtts.prosody import VoiceOptions, compose


def _song():
    return compose("你好世界", VoiceOptions(seed=42))


class AceExportTests(unittest.TestCase):
    def _project(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = ace.FORMAT.writer(_song(), str(Path(tmp.name) / "x.ace"))
        return json.loads(path.read_text(encoding="utf-8"))

    def test_top_level(self) -> None:
        project = self._project()
        self.assertEqual(project["version"], ace.PROJECT_VERSION)
        for key in ("debug_info", "song_info", "bgm_info", "tracks"):
            self.assertIn(key, project)
        self.assertEqual(project["bgm_info"]["tracks"], [])
        self.assertEqual(project["debug_info"]["recordType"], "create")

    def test_song_info_uses_seconds(self) -> None:
        project = self._project()
        info = project["song_info"]
        self.assertEqual(info["bpm"], 120.0)
        self.assertEqual(info["beat_of_bar"], 4)
        self.assertEqual(info["operateScale"], ace.DEFAULT_SCALE)
        self.assertEqual(info["song_id"], 0)      # 固定值，保证可复现
        song = _song()
        expected = (max(n.start + n.dur for n in song.notes)) / 480 / 120 * 60
        self.assertAlmostEqual(info["duration"], expected, places=5)

    def test_track(self) -> None:
        project = self._project()
        track = project["tracks"][0]
        self.assertTrue(track["AI_SVS_mode"])
        self.assertEqual(track["unReadLyric"], "")
        self.assertEqual(track["lyric"], "你好世界")
        self.assertEqual(track["role_info"]["name"], ace.DEFAULT_ROLE_NAME)

    def test_notes(self) -> None:
        project = self._project()
        notes = project["tracks"][0]["notes"]
        song = _song()
        self.assertEqual(len(notes), len(song.notes))
        first = notes[0]
        self.assertAlmostEqual(first["start_time"], 0.0, places=6)
        # pitch 是 MIDI + 12，不是 MIDI
        self.assertEqual(first["pitch"], song.notes[0].midi + ace.PITCH_OFFSET)
        self.assertEqual(first["word"], "你")
        self.assertEqual(first["pinyin"], "ni")
        self.assertEqual(first["scale"], ace.DEFAULT_SCALE)

    def test_note_times_match_bpm(self) -> None:
        notes = self._project()["tracks"][0]["notes"]
        song = _song()
        for index, note in enumerate(notes):
            source = song.notes[index]
            self.assertAlmostEqual(note["end_time"] - note["start_time"],
                                   source.dur / 480 / 120 * 60, places=5)

    def test_pitch_bends_are_relative_semitones(self) -> None:
        notes = self._project()["tracks"][0]["notes"]
        bends = notes[0]["pitchBends"]
        self.assertGreater(len(bends), 0)
        for bend in bends:
            self.assertIn("time", bend)
            self.assertIn("pitch", bend)
            # 相对音符本身的偏移，上限是 PBS 个半音
            self.assertLessEqual(abs(bend["pitch"]), 12)

    def test_key_style_is_mixed(self) -> None:
        """带别名的字段是驼峰，没别名的保持下划线——这是原模型的写法。"""
        project = self._project()
        note = project["tracks"][0]["notes"][0]
        self.assertIn("pitchBends", note)
        self.assertIn("start_time", note)
        self.assertIn("song_info", project)
        self.assertNotIn("songInfo", project)

    def test_export_is_reproducible(self) -> None:
        first = ace.build_project(_song())
        second = ace.build_project(_song())
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))

    def test_empty_song_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ace.write_ace(compose("", VoiceOptions(seed=1)), "x.ace")

    def test_registry(self) -> None:
        self.assertEqual(formats()["ace"].extension, ".ace")


if __name__ == "__main__":
    unittest.main()
