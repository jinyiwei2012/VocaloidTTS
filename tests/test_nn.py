"""袅袅虚拟歌手 .nn 导出的结构回归。

.nn 是纯文本、按行排的格式，所以测试直接按空格/换行切开逐字段核对。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vocaloidtts.formats import formats, nn
from vocaloidtts.prosody import VoiceOptions, compose


class NnExportTests(unittest.TestCase):
    def _lines(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = nn.FORMAT.writer(compose("你好世界", VoiceOptions(seed=42)),
                                str(Path(tmp.name) / "x.nn"))
        return path.read_text(encoding="utf-8").splitlines()

    def test_header(self) -> None:
        header = self._lines()[0].split()
        self.assertEqual(len(header), 10)
        self.assertEqual(float(header[0]), 120.0)
        self.assertEqual(header[1:3], ["4", "4"])
        self.assertEqual(header[4], str(nn.PROJECT_VERSION))
        self.assertEqual(header[5:], ["0"] * 5)

    def test_note_count_line(self) -> None:
        lines = self._lines()
        self.assertEqual(int(lines[1]), 4)
        self.assertEqual(len(lines), 2 + 4)

    def test_note_line_fields(self) -> None:
        line = self._lines()[2]
        # 每行行首有一个空格
        self.assertTrue(line.startswith(" "))
        fields = line.split()
        self.assertEqual(len(fields), 14)
        song = compose("你好世界", VoiceOptions(seed=42))
        note = song.notes[0]
        self.assertEqual(fields[0], "你")
        self.assertEqual(fields[1], note.lyric)
        self.assertEqual(int(fields[2]), note.start // nn.TICKS_PER_UNIT)
        self.assertEqual(int(fields[3]), note.dur // nn.TICKS_PER_UNIT)
        # 音高轴是反的：key = 83 - MIDI
        self.assertEqual(int(fields[4]), nn.KEY_ORIGIN - note.midi)

    def test_envelopes(self) -> None:
        for line in self._lines()[2:]:
            fields = line.split()
            for index, expected in ((11, nn.ENVELOPE_POINTS), (12, nn.ENVELOPE_POINTS)):
                count, _, values = fields[index].partition(",")
                self.assertEqual(int(count), expected)
                points = [int(value) for value in values.split(",")]
                self.assertEqual(len(points), expected)
                self.assertTrue(all(0 <= value <= 100 for value in points))

    def test_pitch_sensitivity_range(self) -> None:
        for line in self._lines()[2:]:
            pbs = int(line.split()[13])
            self.assertGreaterEqual(pbs, 0)
            self.assertLessEqual(pbs, 11)

    def test_empty_song_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            nn.write_nn(compose("", VoiceOptions(seed=1)), "x.nn")

    def test_registry(self) -> None:
        self.assertEqual(formats()["nn"].extension, ".nn")


if __name__ == "__main__":
    unittest.main()
