"""VocalSharp .vspx 导出的结构回归。

.vspx 是 XML，测试直接解析成树逐节点核对，不比对字符串。
"""
from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from vocaloidtts.formats import formats, vspx
from vocaloidtts.prosody import VoiceOptions, compose


def _tree():
    tmp = tempfile.TemporaryDirectory()
    path = vspx.FORMAT.writer(compose("你好世界", VoiceOptions(seed=42)),
                              str(Path(tmp.name) / "x.vspx"))
    return ET.fromstring(path.read_text(encoding="utf-8")), tmp


class VspxExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root, tmp = _tree()
        self.addCleanup(tmp.cleanup)
        self.project = self.root.find("Project")

    def test_root_and_version(self) -> None:
        self.assertEqual(self.root.tag, "VSPX")
        self.assertEqual(self.root.findtext("Version"), "Beta0.0.0")
        self.assertIsNotNone(self.project)

    def test_project_header(self) -> None:
        self.assertEqual(self.project.findtext("SamplesPerSec"), "44100")
        self.assertEqual(self.project.findtext("Resolution"), str(vspx.RESOLUTION))
        self.assertGreaterEqual(int(self.project.findtext("Duration")),
                                vspx.DURATION_FLOOR)

    def test_tempo_and_beat(self) -> None:
        tempo = self.project.find("Tempo")
        self.assertEqual(float(tempo.findtext("bpm")), 120.0)
        beat = self.project.find("Beat")
        self.assertEqual(beat.findtext("barIndex"), "0")
        self.assertEqual(beat.findtext("beatPerBar"), "4")
        self.assertEqual(beat.findtext("barDivide"), "4")

    def test_notes(self) -> None:
        track = self.project.find("NoteTrack")
        self.assertIsNotNone(track)
        notes = track.findall("Note")
        song = compose("你好世界", VoiceOptions(seed=42))
        self.assertEqual(len(notes), len(song.notes))
        first = notes[0]
        # pitch 是音名，不是 MIDI：60 = C4
        self.assertEqual(first.findtext("pitch"), "F#4")
        self.assertEqual(int(first.findtext("pos")), song.notes[0].start)
        self.assertEqual(int(first.findtext("duration")), song.notes[0].dur)
        self.assertEqual(first.findtext("lyric"), "你")
        self.assertIsNotNone(first.find("Syllable"))

    def test_note_names(self) -> None:
        self.assertEqual(vspx._note_name(60), "C4")
        self.assertEqual(vspx._note_name(69), "A4")
        self.assertEqual(vspx._note_name(0), "C-1")

    def test_empty_song_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            vspx.write_vspx(compose("", VoiceOptions(seed=1)), "x.vspx")

    def test_registry(self) -> None:
        self.assertEqual(formats()["vspx"].extension, ".vspx")


if __name__ == "__main__":
    unittest.main()
