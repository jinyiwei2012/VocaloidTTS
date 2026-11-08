import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from vocaloidtts.jobfile import write_job
from vocaloidtts.prosody import VoiceOptions, compose


class VsqxJobTests(unittest.TestCase):
    def test_vsqx_and_plugin_preserve_notes_and_controls(self):
        # Importing voicebank reads editor settings. Keep that app data isolated
        # and supply a placeholder directly, without scanning installed banks.
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"APPDATA": directory, "LOCALAPPDATA": directory}):
                from vocaloidtts.voicebank import Voicebank
                from vocaloidtts.vsqx import write_vsqx

                bank = Voicebank("TEST", "Test", "测试", bs=4, pc=0, source="test")
                for text, mode in [("你好，世界！", "chinese"),
                                   ("ni3 hao3, shi4 jie4!", "pinyin")]:
                    with self.subTest(mode=mode):
                        song = compose(text, VoiceOptions(seed=42, pbs=6), bpm=90,
                                       numerator=3, denominator=4, input_mode=mode)
                        xml_path = Path(directory) / f"{mode}.vsqx"
                        title = "测试 <工程> & ]]>"
                        write_vsqx(song, str(xml_path), bank, title=title)
                        root = ET.parse(xml_path).getroot()
                        self.assertEqual(root.findtext(".//{*}seqName"), title)
                        self.assertEqual(int(root.findtext(".//{*}resolution")), 480)
                        self.assertEqual(int(root.findtext(".//{*}tempo/{*}v")), 9000)
                        self.assertEqual(int(root.findtext(".//{*}vsPart/{*}t")), song.part_start)
                        notes = root.findall(".//{*}note")
                        self.assertEqual(len(notes), len(song.notes))
                        for node, note in zip(notes, song.notes):
                            for field, expected in [("t", note.start), ("dur", note.dur),
                                                    ("n", note.midi), ("v", note.velocity)]:
                                self.assertEqual(int(node.findtext("{*}" + field)), expected)
                            self.assertEqual(node.findtext("{*}y"), note.lyric)
                            self.assertEqual(node.findtext("{*}p"), note.phonemes)
                        controls = {}
                        for node in root.findall(".//{*}cc"):
                            value = node.find("{*}v")
                            controls.setdefault(value.attrib["id"], []).append(
                                (int(node.findtext("{*}t")), int(value.text)))
                        self.assertEqual(controls, song.controls)

                        job = write_job(song, Path(directory) / f"{mode}.txt")
                        rows = [line.split("\t") for line in job.read_text(encoding="utf-8").splitlines()]
                        note_rows = [row for row in rows if row[0] == "NOTE"]
                        self.assertEqual(len(note_rows), len(song.notes))
                        for row, note in zip(note_rows, song.notes):
                            self.assertEqual(list(map(int, row[1:5])),
                                             [note.start, note.dur, note.midi, note.velocity])
                            self.assertEqual(row[6:8], [note.lyric, note.phonemes])
                        expected = [("PBS" if name == "S" else "PIT" if name == "P" else name,
                                     tick, value)
                                    for name, points in song.controls.items()
                                    for tick, value in points]
                        actual = [(row[1], int(row[2]), int(row[3]))
                                  for row in rows if row[0] == "CC"]
                        self.assertCountEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
