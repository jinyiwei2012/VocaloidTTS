"""VOCALOID 5/6 .vpr 导出的结构回归。"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from vocaloidtts.formats import formats, vpr
from vocaloidtts.prosody import VoiceOptions, compose
from vocaloidtts.voicebank import Voicebank

COMP = "BTESTBANK0000001"


def _bank(bid: str = COMP) -> Voicebank:
    return Voicebank(bid, "Test", "测试", bs=4, pc=0, source="test")


class VprExportTests(unittest.TestCase):
    def _song(self):
        return compose("你好世界", VoiceOptions(seed=42))

    def _export(self):
        song = self._song()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = vpr.write_vpr(song, str(Path(tmp.name) / "x.vpr"), _bank())
        with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as archive:
            names = archive.namelist()
            payload = archive.read("Project/sequence.json")
        return song, path, names, json.loads(payload)

    def test_container_is_a_zip_with_one_entry(self) -> None:
        _, path, names, _ = self._export()
        self.assertEqual(path.suffix, ".vpr")
        self.assertEqual(names, ["Project/sequence.json"])

    def test_top_level_shape(self) -> None:
        _, _, _, project = self._export()
        self.assertEqual(project["vender"], "Yamaha Corporation")
        self.assertEqual(project["version"]["major"], 5)
        self.assertEqual(len(project["tracks"]), 1)
        self.assertEqual(project["tracks"][0]["type"], vpr.TRACK_TYPE_STANDARD)
        self.assertEqual(project["voices"][0]["compID"], COMP)

    def test_master_track(self) -> None:
        song, _, _, project = self._export()
        master = project["masterTrack"]
        self.assertEqual(master["tempo"]["events"],
                         [{"pos": 0, "value": int(song.bpm * vpr.BPM_RATE)}])
        # global 的默认值是 12000，跟着实际 BPM 走才不会自相矛盾
        self.assertEqual(master["tempo"]["global"]["value"],
                         int(song.bpm * vpr.BPM_RATE))
        self.assertEqual(master["timeSig"]["events"],
                         [{"bar": 0, "numer": song.numerator,
                           "denom": song.denominator}])
        self.assertEqual(master["samplingRate"], 44100)

    def test_notes(self) -> None:
        song, _, _, project = self._export()
        part = project["tracks"][0]["parts"][0]
        notes = part["notes"]
        self.assertEqual(len(notes), len(song.notes))
        first = notes[0]
        self.assertEqual(first["langID"], vpr.LANG_SIMPLIFIED_CHINESE)
        self.assertEqual(first["pos"], song.notes[0].start)
        self.assertEqual(first["duration"], song.notes[0].dur)
        self.assertEqual(first["number"], song.notes[0].midi)
        self.assertEqual(first["lyric"], "你")
        # 音素直接用 pinyin.py 的 X-SAMPA，不该退化成 l a
        self.assertEqual(first["phoneme"], song.notes[0].phonemes)
        self.assertNotEqual(first["phoneme"], vpr.DEFAULT_CHINESE_PHONEME)
        self.assertEqual(part["duration"],
                         max(n.start + n.dur for n in song.notes))

    def test_controllers_use_vpr_names(self) -> None:
        song = self._song()
        project = vpr.build_project(song, _bank())
        controllers = project["tracks"][0]["parts"][0]["controllers"]
        names = [c["name"] for c in controllers]
        self.assertIn("pitchBend", names)
        self.assertIn("pitchBendSens", names)
        self.assertIn("dynamics", names)
        # vpr 里 gender 通道叫 character，写成 gender 编辑器读不到
        self.assertIn("character", names)
        self.assertNotIn("gender", names)
        for controller in controllers:
            for event in controller["events"]:
                self.assertIsInstance(event["pos"], int)
                self.assertIsInstance(event["value"], int)

    def test_controller_values_are_clamped(self) -> None:
        song = self._song()
        song.controls = {"S": [(0, 99)]}     # PBS 上限是 24
        project = vpr.build_project(song, _bank())
        controllers = project["tracks"][0]["parts"][0]["controllers"]
        sens = next(c for c in controllers if c["name"] == "pitchBendSens")
        self.assertEqual(sens["events"], [{"pos": 0, "value": 24}])

    def test_comp_id_must_be_sixteen_ascii_characters(self) -> None:
        song = self._song()
        for bid in ("TEST", "BTESTBANK000000", "BTESTBANK00000012"):
            with self.subTest(id=bid):
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaises(ValueError):
                        vpr.write_vpr(song, str(Path(directory) / "x.vpr"),
                                      _bank(bid))

    def test_empty_song_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            vpr.write_vpr(compose("", VoiceOptions(seed=1)), "x.vpr", _bank())

    def test_registry_lists_vpr(self) -> None:
        self.assertEqual(formats()["vpr"].extension, ".vpr")
        self.assertTrue(formats()["vpr"].needs_voicebank)


if __name__ == "__main__":
    unittest.main()
