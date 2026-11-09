"""时间轴歌词/字幕（.lrc / .srt / .ass）导出的结构回归。

这三种格式本质是一件事：把音符按停顿切成歌词行，再给每行打上起止时间。
所以放在一个文件里测，重点验证「切行」和「时间戳格式」两件事。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vocaloidtts.formats import ass, formats, lrc, srt
from vocaloidtts.formats.base import lyric_lines, lyric_text, seconds
from vocaloidtts.prosody import VoiceOptions, compose

TEXT = "你好，世界。这是第二句，还有一个停顿。"


def _song():
    return compose(TEXT, VoiceOptions(seed=3))


class LineSplitTests(unittest.TestCase):
    def test_splits_on_punctuation_pauses(self) -> None:
        lines = lyric_lines(_song())
        self.assertEqual([lyric_text(group) for group in lines],
                         ["你好", "世界", "这是第二句", "还有一个停顿"])

    def test_empty_song_has_no_lines(self) -> None:
        self.assertEqual(lyric_lines(compose("", VoiceOptions(seed=1))), [])

    def test_seconds_follow_bpm_and_resolution(self) -> None:
        song = _song()
        # 480 tick = 一个四分音符；120 BPM 下是 0.5 秒
        self.assertAlmostEqual(seconds(song, 480), 0.5, places=6)
        song.resolution = 960
        self.assertAlmostEqual(seconds(song, 960), 0.5, places=6)

    def test_latin_lyrics_get_spaces(self) -> None:
        song = compose("ni hao", VoiceOptions(seed=3), input_mode="pinyin")
        text = lyric_text(lyric_lines(song)[0])
        self.assertNotIn("nihao", text)


class TimelineExportTests(unittest.TestCase):
    def _write(self, module, suffix):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = module.FORMAT.writer(_song(), str(Path(tmp.name) / ("x" + suffix)))
        return path.read_text(encoding="utf-8")

    def test_lrc(self) -> None:
        text = self._write(lrc, ".lrc")
        lines = [line for line in text.splitlines() if line.startswith("[")]
        stamps = [line for line in lines if line[1:3].isdigit()]
        self.assertEqual(len(stamps), 4)
        self.assertTrue(all("]" in line for line in stamps))
        self.assertEqual(stamps[0].split("]")[1], "你好")
        # [mm:ss.xx] 两位小数
        body = stamps[0][1:stamps[0].index("]")]
        self.assertRegex(body, r"^\d{2}:\d{2}\.\d{2}$")

    def test_srt(self) -> None:
        text = self._write(srt, ".srt")
        self.assertTrue(text.startswith("1\n"))
        self.assertIn(" --> ", text)
        # SubRip 用逗号分隔毫秒，不是点
        self.assertRegex(text, r"\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}")
        self.assertEqual(text.count(" --> "), 4)
        self.assertIn("你好", text)

    def test_ass(self) -> None:
        text = self._write(ass, ".ass")
        self.assertTrue(text.startswith("[Script Info]"))
        self.assertIn("[V4+ Styles]", text)
        self.assertIn("[Events]", text)
        self.assertEqual(text.count("Dialogue: "), 4)
        # ASS 用百分秒，两位
        self.assertRegex(
            text, r"Dialogue: 0,\d:\d{2}:\d{2}\.\d{2},\d:\d{2}:\d{2}\.\d{2},Default,")

    def test_all_three_are_registered(self) -> None:
        for key, extension in (("lrc", ".lrc"), ("srt", ".srt"), ("ass", ".ass")):
            with self.subTest(key=key):
                self.assertEqual(formats()[key].extension, extension)


if __name__ == "__main__":
    unittest.main()
