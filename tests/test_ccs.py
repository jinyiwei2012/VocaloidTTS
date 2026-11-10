"""CeVIO .ccs 导出的结构回归。

.ccs 是 XML，测试解析成树逐节点核对。重点验证「音符、速度、拍号都是属性」，
写反成子元素 CeVIO 会当成空工程。
"""
from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from vocaloidtts.formats import ccs, formats
from vocaloidtts.prosody import VoiceOptions, compose


class CcsExportTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = ccs.FORMAT.writer(compose("你好世界", VoiceOptions(seed=42)),
                                 str(Path(tmp.name) / "x.ccs"))
        self.root = ET.fromstring(path.read_text(encoding="utf-8"))

    def test_root(self) -> None:
        self.assertEqual(self.root.tag, "Scenario")
        self.assertIsNotNone(self.root.find("Generation"))
        self.assertIsNotNone(self.root.find("Sequence"))

    def test_sound_source(self) -> None:
        source = self.root.find("Generation/SVSS/SoundSources/SoundSource")
        self.assertIsNotNone(source)
        self.assertEqual(source.get("Name"), ccs.DEFAULT_SINGER_NAME)
        self.assertEqual(source.get("Version"), ccs.APP_VERSION)

    def test_unit_attributes(self) -> None:
        unit = self.root.find("Sequence/Scene/Units/Unit")
        self.assertIsNotNone(unit)
        self.assertEqual(unit.get("Category"), ccs.CATEGORY)
        self.assertEqual(unit.get("StartTime"), "00:00:00.000")
        self.assertRegex(unit.get("Duration"), r"^\d{2}:\d{2}:\d{2}\.\d{3}$")

    def test_tempo_and_beat_are_elements_with_attributes(self) -> None:
        song = self.root.find("Sequence/Scene/Units/Unit/Song")
        sound = song.find("Tempo/Sound")
        self.assertIsNotNone(sound)
        self.assertEqual(sound.get("Clock"), "0")
        self.assertEqual(float(sound.get("Tempo")), 120.0)
        time_item = song.find("Beat/Time")
        self.assertEqual((time_item.get("Beats"), time_item.get("BeatType")), ("4", "4"))

    def test_notes_are_attributes(self) -> None:
        notes = self.root.findall("Sequence/Scene/Units/Unit/Song/Score/Note")
        song = compose("你好世界", VoiceOptions(seed=42))
        self.assertEqual(len(notes), len(song.notes))
        first = notes[0]
        self.assertEqual(len(first), 0)          # 没有子元素
        self.assertEqual(first.get("Clock"), "0")
        self.assertEqual(first.get("Lyric"), "ni")
        self.assertEqual(first.get("Duration"),
                         str(song.notes[0].dur * ccs.CLOCK_PER_TICK))

    def test_pitch_is_split_into_octave_and_step(self) -> None:
        notes = self.root.findall("Sequence/Scene/Units/Unit/Song/Score/Note")
        song = compose("你好世界", VoiceOptions(seed=42))
        first = notes[0]
        midi = song.notes[0].midi
        self.assertEqual(int(first.get("PitchStep")), midi % 12)
        self.assertEqual(int(first.get("PitchOctave")), midi // 12 + ccs.OCTAVE_OFFSET)

    def test_groups(self) -> None:
        groups = self.root.find("Sequence/Scene/Groups")
        self.assertEqual(groups.get("ActiveGroup"), "group")
        group = groups.find("Group")
        self.assertEqual(group.get("Category"), ccs.CATEGORY)
        self.assertEqual(group.get("IsMuted"), "False")

    def test_empty_song_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ccs.write_ccs(compose("", VoiceOptions(seed=1)), "x.ccs")

    def test_registry(self) -> None:
        self.assertEqual(formats()["ccs"].extension, ".ccs")


if __name__ == "__main__":
    unittest.main()
