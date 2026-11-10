"""UTAU .ust 导出的结构回归。

.ust 是 INI 风格的纯文本，测试按小节切开逐键核对。
"""
from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from vocaloidtts.formats import formats, ust
from vocaloidtts.prosody import VoiceOptions, compose


def _sections(text: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    current = ""
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith("[#") and line.endswith("]"):
            current = line[2:-1]
            result[current] = {}
        elif current:
            key, _, value = line.partition("=")
            result[current][key] = value
    return result


class UstExportTests(unittest.TestCase):
    def _sections(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = ust.FORMAT.writer(compose("你好世界", VoiceOptions(seed=42)),
                                 str(Path(tmp.name) / "x.ust"))
        return _sections(path.read_text(encoding="utf-8"))

    def test_version_and_setting(self) -> None:
        sections = self._sections()
        self.assertEqual(list(sections)[:2], ["VERSION", "SETTING"])
        self.assertEqual(sections["VERSION"]["UST Version"], ust.UST_VERSION)
        self.assertEqual(sections["VERSION"]["Charset"], "UTF-8")
        self.assertEqual(sections["SETTING"]["Tempo"], "120.00")
        self.assertEqual(sections["SETTING"]["Tracks"], "1")
        self.assertEqual(sections["SETTING"]["Project"], "VocaloidTTS")

    def test_track_end_is_last(self) -> None:
        sections = self._sections()
        self.assertEqual(list(sections)[-1], "TRACKEND")

    def test_notes(self) -> None:
        sections = self._sections()
        song = compose("你好世界", VoiceOptions(seed=42))
        note_sections = [name for name in sections if name.isdigit()]
        self.assertEqual(len(note_sections), len(song.notes))
        self.assertEqual(note_sections[0], "0000")
        first = sections["0000"]
        self.assertEqual(first["Length"], str(song.notes[0].dur))
        self.assertEqual(first["Lyric"], song.notes[0].lyric)
        self.assertEqual(first["NoteNum"], str(song.notes[0].midi))

    def test_note_numbers_are_zero_padded(self) -> None:
        sections = self._sections()
        note_sections = [name for name in sections if name.isdigit()]
        self.assertTrue(all(len(name) == 4 for name in note_sections))

    def test_gaps_become_rest_notes(self) -> None:
        """UST 没有 start 字段，标点带来的停顿必须写成 Lyric=R。"""
        song = compose("你好，世界", VoiceOptions(seed=42))
        sections = _sections(ust.build_text(song))
        entries = [sections[name] for name in sections if name.isdigit()]
        total = sum(int(entry["Length"]) for entry in entries)
        self.assertEqual(total, max(n.start + n.dur for n in song.notes))
        gaps = [b.start - (a.start + a.dur)
                for a, b in zip(song.notes, song.notes[1:]) if b.start > a.start + a.dur]
        rests = [int(entry["Length"]) for entry in entries if entry["Lyric"] == "R"]
        self.assertEqual(rests, gaps)
        self.assertTrue(rests, "带标点的输入应该至少产生一个休止")
        for entry in entries:
            if entry["Lyric"] == "R":
                self.assertEqual(entry["NoteNum"], str(ust.REST_MIDI))

    def test_leading_gap_gets_a_rest(self) -> None:
        song = compose("你好世界", VoiceOptions(seed=42))
        shifted = replace(song, notes=[replace(n, start=n.start + 100)
                                       for n in song.notes])
        sections = _sections(ust.build_text(shifted))
        first = sections["0000"]
        self.assertEqual(first["Lyric"], "R")
        self.assertEqual(first["Length"], "100")

    def test_contiguous_notes_have_no_rests(self) -> None:
        sections = self._sections()
        lyrics = [sections[name]["Lyric"] for name in sections if name.isdigit()]
        self.assertNotIn("R", lyrics)

    def test_empty_song_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ust.write_ust(compose("", VoiceOptions(seed=1)), "x.ust")

    def test_registry(self) -> None:
        self.assertEqual(formats()["ust"].extension, ".ust")


if __name__ == "__main__":
    unittest.main()
