"""Cadencii .xvsq 导出的结构回归。

.xvsq 是 XML，所以这里用标准库 ElementTree 当**独立读取器**：按 Cadencii /
LibreSVIP 的元素顺序把文件读回来逐层核对，不复用导出代码里的任何常量。
"""
from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from vocaloidtts.formats import base, formats, xvsq
from vocaloidtts.prosody import VoiceOptions, compose

TEXT = "你好，世界"

#: VsqFileEx 的直接子元素顺序（Cadencii 按这个顺序读）。
ROOT_ORDER = ["Track", "TempoTable", "TimesigTable", "TotalClocks", "Master",
              "Mixer", "AttachedCurves", "BgmFiles", "cacheDir", "config"]


def _song(**kwargs):
    return compose(TEXT, VoiceOptions(seed=42), **kwargs)


def _root(song=None) -> ET.Element:
    song = song or _song()
    return ET.fromstring(xvsq.build_xml(song))


def _tracks(root: ET.Element) -> list[ET.Element]:
    return root.findall("Track/VsqTrack")


def _events(track: ET.Element) -> list[ET.Element]:
    return track.findall("MetaText/Events/Events/VsqEvent")


def _notes(root: ET.Element) -> list[ET.Element]:
    return [event for event in _events(_tracks(root)[1])
            if event.findtext("ID/type") == "Anote"]


class XvsqExportTests(unittest.TestCase):
    def test_root_children_follow_cadencii_order(self) -> None:
        root = _root()
        self.assertEqual(root.tag, "VsqFileEx")
        self.assertEqual([child.tag for child in root], ROOT_ORDER)

    def test_first_track_is_an_empty_master_track(self) -> None:
        """读的时候会跳过第 0 条轨，所以它必须存在且为空。"""
        tracks = _tracks(_root())
        self.assertEqual(len(tracks), 2)
        self.assertIsNone(tracks[0].find("MetaText"))

    def test_common_block(self) -> None:
        common = _tracks(_root())[1].find("MetaText/Common")
        self.assertIsNotNone(common)
        self.assertEqual(common.findtext("Version"), xvsq.VSQ_VERSION)
        self.assertEqual(common.findtext("Color"), xvsq.DEFAULT_COLOR)
        self.assertEqual(common.findtext("DynamicsMode"), "1")
        self.assertEqual(common.findtext("PlayMode"), "1")

    def test_singer_event_comes_first(self) -> None:
        events = _events(_tracks(_root())[1])
        self.assertEqual(events[0].findtext("InternalID"), "0")
        self.assertEqual(events[0].findtext("Clock"), "0")
        self.assertEqual(events[0].findtext("ID/type"), "Singer")
        # 必填字段：VsqID 的 note / length 在 pydantic 模型里没有默认值
        self.assertEqual(events[0].findtext("ID/Note"), "0")
        self.assertEqual(events[0].findtext("ID/Length"), "0")

    def test_note_events_carry_time_pitch_and_lyrics(self) -> None:
        song = _song()
        events = _notes(_root(song))
        self.assertEqual(len(events), len(song.notes))
        for index, (event, note) in enumerate(zip(events, song.notes), start=1):
            with self.subTest(index=index):
                self.assertEqual(event.findtext("InternalID"), str(index))
                self.assertEqual(event.findtext("Clock"),
                                 str(int(note.start) + xvsq.PREFIX_TICKS))
                self.assertEqual(event.findtext("ID/type"), "Anote")
                self.assertEqual(event.findtext("ID/Note"), str(note.midi))
                self.assertEqual(event.findtext("ID/Length"), str(note.dur))
                self.assertEqual(event.findtext("ID/LyricHandle/L0/Phrase"),
                                 note.lyric)
                self.assertEqual(
                    event.findtext("ID/LyricHandle/L0/PhoneticSymbol"),
                    note.phonemes)

    def test_phonetic_symbol_comes_last_in_the_lyric_block(self) -> None:
        lyric = _notes(_root())[0].find("ID/LyricHandle/L0")
        tags = [child.tag for child in lyric]
        self.assertEqual(tags[0], "Phrase")
        self.assertEqual(tags[-1], "PhoneticSymbol")
        self.assertEqual(tags, ["Phrase", "UnknownFloat",
                                "PhoneticSymbolProtected", "ConsonantAdjustment",
                                "PhoneticSymbol"])

    def test_lyric_handle_has_index_and_trailing(self) -> None:
        handle = _notes(_root())[0].find("ID/LyricHandle")
        self.assertEqual([child.tag for child in handle], ["L0", "Index", "Trailing"])

    def test_no_placeholder_text_leaks_into_the_file(self) -> None:
        """音素行曾经漏了 f 前缀，整份文件里会留下字面量 {phonetic}。"""
        text = xvsq.build_xml(_song())
        self.assertNotIn("{phonetic}", text)
        self.assertNotIn("{phrase}", text)

    def test_every_event_has_an_ust_event(self) -> None:
        for event in _events(_tracks(_root())[1]):
            with self.subTest(internal_id=event.findtext("InternalID")):
                self.assertIsNotNone(event.find("UstEvent"))

    def test_curve_lists_use_capitalised_fields(self) -> None:
        meta = _tracks(_root())[1].find("MetaText")
        for name in ("PIT", "PBS", "DYN", "BRE", "BRI", "CLE",
                     "reso1FreqBPList", "reso4AmpBPList", "harmonics",
                     "fx2depth", "GEN", "POR", "OPE"):
            with self.subTest(curve=name):
                node = meta.find(name)
                self.assertIsNotNone(node)
                self.assertEqual([child.tag for child in node],
                                 ["Data", "Default", "Name", "Maximum", "Minimum"])
        self.assertEqual(meta.findtext("PIT/Default"), "0")
        self.assertEqual(meta.findtext("PBS/Default"), "2")
        self.assertEqual(meta.findtext("DYN/Default"), "64")

    def test_total_clocks_and_tables(self) -> None:
        song = _song()
        root = _root(song)
        end = max(note.start + note.dur for note in song.notes)
        self.assertEqual(root.findtext("TotalClocks"),
                         str(int(end) + xvsq.PREFIX_TICKS))
        self.assertEqual(root.findtext("TempoTable/TempoTableEntry/Clock"), "0")
        self.assertEqual(root.findtext("TempoTable/TempoTableEntry/Tempo"),
                         str(round(60_000_000 / 120)))
        self.assertEqual(root.findtext("TimesigTable/TimeSigTableEntry/Numerator"),
                         "4")
        self.assertEqual(root.findtext("TimesigTable/TimeSigTableEntry/Denominator"),
                         "4")

    def test_mixer_and_config_blocks(self) -> None:
        root = _root()
        self.assertEqual(root.findtext("Master/PreMeasure"), "1")
        self.assertEqual(root.findtext("Mixer/OutputMode"), "0")
        self.assertIsNotNone(root.find("Mixer/Slave"))
        self.assertIsNotNone(root.find("AttachedCurves/Curves"))
        self.assertIsNotNone(root.find("BgmFiles"))
        self.assertEqual(root.findtext("config/SamplingRate"), "44100")

    def test_non_default_resolution_is_converted_to_480(self) -> None:
        song = _song(resolution=960)
        flat = base.resample(song)
        root = _root(song)
        end = max(note.start + note.dur for note in flat.notes)
        self.assertEqual(root.findtext("TotalClocks"),
                         str(int(end) + xvsq.PREFIX_TICKS))
        events = _notes(root)
        self.assertEqual(len(events), len(flat.notes))
        for event, note in zip(events, flat.notes):
            self.assertEqual(event.findtext("Clock"),
                             str(int(note.start) + xvsq.PREFIX_TICKS))
        # 960 分辨率下的原始 tick 是两倍：最后一个音的时钟必须明显更小
        last_raw = max(n.start for n in song.notes)
        last_out = int(events[-1].findtext("Clock")) - xvsq.PREFIX_TICKS
        self.assertLess(last_out, last_raw)

    def test_empty_song_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            xvsq.write_xvsq(compose("", VoiceOptions(seed=1)), "x.xvsq")

    def test_registry_entry(self) -> None:
        entry = formats()["xvsq"]
        self.assertEqual(entry.extension, ".xvsq")
        self.assertFalse(entry.needs_voicebank)


if __name__ == "__main__":
    unittest.main()
