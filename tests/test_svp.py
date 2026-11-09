"""Synthesizer V .svp 导出的结构回归。

这些断言只验证「写出来的 JSON 符合 SVP 的字段约定」，不代表 Synthesizer V
真的能打开——真实载入需要装了编辑器的机器。
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vocaloidtts.formats import formats, svp
from vocaloidtts.prosody import VoiceOptions, compose


class SvpExportTests(unittest.TestCase):
    def _export(self, text: str = "你好世界"):
        song = compose(text, VoiceOptions(seed=42))
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = svp.write_svp(song, str(Path(tmp.name) / "x.svp"))
        return song, json.loads(path.read_text(encoding="utf-8"))

    def test_note_times_are_blicks(self) -> None:
        song, data = self._export()
        notes = data["tracks"][0]["mainGroup"]["notes"]
        self.assertEqual(len(notes), len(song.notes))
        self.assertEqual(notes[0]["onset"],
                         int(song.notes[0].start * svp.BLICK_PER_TICK))
        self.assertEqual(notes[0]["duration"],
                         int(song.notes[0].dur * svp.BLICK_PER_TICK))

    def test_lyrics_keep_han_characters(self) -> None:
        _, data = self._export()
        lyrics = [n["lyrics"] for n in data["tracks"][0]["mainGroup"]["notes"]]
        self.assertEqual(lyrics, ["你", "好", "世", "界"])

    def test_phonemes_are_left_empty(self) -> None:
        # 空字符串 = 让编辑器按歌词自己生成发音
        _, data = self._export()
        notes = data["tracks"][0]["mainGroup"]["notes"]
        self.assertTrue(all(n["phonemes"] == "" for n in notes))

    def test_group_reference_matches(self) -> None:
        _, data = self._export()
        track = data["tracks"][0]
        self.assertEqual(track["mainRef"]["groupID"], track["mainGroup"]["uuid"])

    def test_pitch_curve_is_flat_pairs(self) -> None:
        _, data = self._export()
        points = data["tracks"][0]["mainGroup"]["parameters"]["pitchDelta"]["points"]
        self.assertGreater(len(points), 0)
        self.assertEqual(len(points) % 2, 0)

    def test_empty_song_is_rejected(self) -> None:
        song = compose("", VoiceOptions(seed=1))
        with self.assertRaises(ValueError):
            svp.write_svp(song, "x.svp")

    def test_registry_lists_svp(self) -> None:
        self.assertEqual(formats()["svp"].extension, ".svp")
        self.assertEqual(len(formats()), 7)


if __name__ == "__main__":
    unittest.main()
