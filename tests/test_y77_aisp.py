"""Yuan77 (.y77) 与 AISingers (.aisp) 导出的结构回归。

这两个格式都把整条音高曲线塞进音符里（500 点定长采样），一个用半音、一个用
十分之一半音，所以放在一起测。
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vocaloidtts.formats import aisp, formats, y77
from vocaloidtts.prosody import VoiceOptions, compose


def _song():
    return compose("你好世界", VoiceOptions(seed=42))


class Y77ExportTests(unittest.TestCase):
    def _project(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = y77.FORMAT.writer(_song(), str(Path(tmp.name) / "x.y77"))
        return json.loads(path.read_text(encoding="utf-8"))

    def test_top_level(self) -> None:
        project = self._project()
        song = _song()
        self.assertEqual(project["v"], 10001)
        self.assertEqual(project["bpm"], song.bpm)
        self.assertEqual(project["bbar"], song.numerator)
        self.assertEqual(project["bbeat"], song.denominator)
        self.assertEqual(project["nnote"], len(project["notes"]))
        self.assertEqual(project["nnote"], len(song.notes))

    def test_note_fields(self) -> None:
        project = self._project()
        song = _song()
        note = project["notes"][0]
        self.assertEqual(note["lyric"], "你")
        self.assertEqual(note["py"], song.notes[0].lyric)
        # 时间单位是 30 tick
        self.assertEqual(note["start"], round(song.notes[0].start / 30))
        self.assertEqual(note["len"], round(song.notes[0].dur / 30))
        # 音高轴是反的：pitch = 88 - MIDI
        self.assertEqual(note["pitch"], 88 - song.notes[0].midi)

    def test_pitch_curve_shape(self) -> None:
        project = self._project()
        for note in project["notes"]:
            self.assertEqual(len(note["pit"]), y77.PITCH_SAMPLES)
            self.assertTrue(all(0 <= value <= 100 for value in note["pit"]))
            self.assertGreaterEqual(note["pbs"], -1)
            self.assertLessEqual(note["pbs"], 11)


class AispExportTests(unittest.TestCase):
    def _parts(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = aisp.FORMAT.writer(_song(), str(Path(tmp.name) / "x.aisp"))
        head, _, body = path.read_text(encoding="utf-8").partition("\n")
        return json.loads(head), json.loads(body)

    def test_file_is_two_json_documents(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = aisp.FORMAT.writer(_song(), str(Path(tmp.name) / "x.aisp"))
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        json.loads(lines[0])
        json.loads(lines[1])

    def test_head(self) -> None:
        head, _ = self._parts()
        song = _song()
        self.assertEqual(head["tempo"][0]["tempo_float"], song.bpm)
        self.assertEqual(head["signature"][0]["beat_zi"], song.numerator)
        self.assertEqual(head["signature"][0]["beat_mu"], song.denominator)
        self.assertEqual(head["signature"][0]["str"],
                         f"{song.numerator}/{song.denominator}")
        self.assertEqual(head["flags"], -256)
        self.assertGreaterEqual(head["bar"], 100)

    def test_body(self) -> None:
        _, body = self._parts()
        self.assertEqual(body["num_track"], 1)
        track = body["tracks"][0]
        self.assertEqual(track["t"], 0)          # 唱轨
        notes = track["im"][0]["n"]
        self.assertEqual(len(notes), len(_song().notes))
        first = notes[0]
        # midi_no 是 MIDI 减 12
        self.assertEqual(first["m"], _song().notes[0].midi - aisp.MIDI_OFFSET)
        self.assertEqual(first["ly"], "你")
        self.assertEqual(first["s"], round(_song().notes[0].start / 15))

    def test_pitch_is_run_length_encoded(self) -> None:
        _, body = self._parts()
        pit = body["tracks"][0]["im"][0]["n"][0]["pit"]
        self.assertIsInstance(pit, str)
        total = 0
        for chunk in pit.split():
            value, _, count = chunk.partition("x")
            float(value)
            total += int(count) if count else 1
        self.assertEqual(total, aisp.PITCH_SAMPLES)

    def test_registry(self) -> None:
        self.assertEqual(formats()["y77"].extension, ".y77")
        self.assertEqual(formats()["aisp"].extension, ".aisp")


if __name__ == "__main__":
    unittest.main()
