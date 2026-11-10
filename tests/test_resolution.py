"""非默认 resolution 的换算回归。

``compose(resolution=...)`` 允许内部 tick 用 96..1920 之间的分辨率，而绝大多数
工程格式的文件里**不写分辨率**、位置一律按固定 480 tick / 四分音符解释。这些
导出器必须在入口调用 ``base.resample()``，否则 960 分辨率导出的时间轴会整体
翻倍；像 VFP 这种同时写 tick 和秒的格式，两套字段还会互相矛盾。

这里用一条不变式统一守住：**先把 Song 手工 resample 再导出，结果必须和直接
导出逐字节（zip 则逐成员）相同**——也就是「导出器自己做过换算」。漏掉换算的
导出器会在这条断言上失败。

``vsqx`` 不在名单里：它的文件自带 ``<resolution>`` 字段，960 就该写 960，
不能被压回 480。
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from vocaloidtts.formats import base, ccs, formats, mid, svp, tssln, vfp, vpr
from vocaloidtts.prosody import VoiceOptions, compose
from vocaloidtts.voicebank import Voicebank

COMP = "BTESTBANK0000001"
TEXT = "你好，世界"

#: 固定 480 时基、且导出结果可复现（不含 uuid）的格式。
#: acep / s5p 不在这里：它们本来就自己换算，而「先 resample 再算」和「先算再
#: resample」在音高曲线的相对偏移上会差 1 tick 的舍入，逐字节比对没有意义。
DETERMINISTIC = [
    "tlp", "tlpx", "ccs", "tssln", "tsmsln", "ust", "vsq", "vspx", "svip",
    "svip3", "ustx", "vog", "dspx", "dv", "mtp", "nn", "y77", "aisp", "vxf",
    "mid", "vfp",
]


def _bank() -> Voicebank:
    return Voicebank(COMP, "Test", "测试", bs=4, pc=0, source="test")


def _payload(path: Path) -> object:
    """把导出的文件变成可比对的载荷；zip 拆成员，避免时间戳干扰。"""
    data = path.read_bytes()
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return tuple((item.filename, archive.read(item.filename))
                         for item in archive.infolist())
    return data


class ResampleTests(unittest.TestCase):
    def test_scales_notes_controls_and_metadata(self) -> None:
        song = compose(TEXT, VoiceOptions(seed=42), resolution=960)
        flat = base.resample(song)
        self.assertEqual(flat.resolution, 480)
        self.assertEqual(len(flat.notes), len(song.notes))
        for before, after in zip(song.notes, flat.notes):
            self.assertEqual(after.start, round(before.start / 2))
            self.assertEqual(after.dur, max(1, round(before.dur / 2)))
        self.assertEqual(flat.total_ticks, round(song.total_ticks / 2))
        self.assertEqual(flat.part_start, round(song.part_start / 2))
        self.assertEqual(set(flat.controls), set(song.controls))
        for name, points in song.controls.items():
            self.assertEqual([t for t, _ in flat.controls[name]],
                             [round(t / 2) for t, _ in points])
            self.assertEqual([v for _, v in flat.controls[name]],
                             [v for _, v in points])

    def test_is_a_noop_at_the_default_resolution(self) -> None:
        song = compose(TEXT, VoiceOptions(seed=42))
        self.assertIs(base.resample(song), song)

    def test_seconds_are_unchanged(self) -> None:
        song = compose(TEXT, VoiceOptions(seed=42), resolution=960)
        flat = base.resample(song)
        for before, after in zip(song.notes, flat.notes):
            self.assertAlmostEqual(base.seconds(song, before.start),
                                   base.seconds(flat, after.start), places=9)
        self.assertAlmostEqual(song.duration_s, flat.duration_s, places=9)


class WriterAppliesResampleTests(unittest.TestCase):
    def test_every_fixed_timebase_writer_resamples(self) -> None:
        song = compose(TEXT, VoiceOptions(seed=42), resolution=960)
        flat = base.resample(song)
        registry = formats()
        bank = _bank()
        for key in DETERMINISTIC:
            with self.subTest(format=key):
                meta = registry[key]
                with tempfile.TemporaryDirectory() as tmp:
                    first = meta.write(song, Path(tmp) / "a", voicebank=bank)
                    second = meta.write(flat, Path(tmp) / "b", voicebank=bank)
                    self.assertEqual(_payload(Path(first)), _payload(Path(second)))


class ConcreteScalingTests(unittest.TestCase):
    """抽查几个「文件里不写分辨率」的格式，确认写出的数字是对的一半。"""

    def setUp(self) -> None:
        self.song = compose(TEXT, VoiceOptions(seed=42), resolution=960)
        self.note = self.song.notes[2]  # start != 0，否则缩放错误看不出来
        self.half = round(self.note.start / 2)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def test_svp_onset_uses_half_the_ticks(self) -> None:
        path = svp.write_svp(self.song, str(self.tmp / "a.svp"))
        notes = json.loads(Path(path).read_text(encoding="utf-8"))["tracks"][0]["mainGroup"]["notes"]
        self.assertEqual(notes[2]["onset"], self.half * svp.BLICK_PER_TICK)
        self.assertEqual(notes[2]["duration"],
                         round(self.note.dur / 2) * svp.BLICK_PER_TICK)

    def test_vpr_position_uses_half_the_ticks(self) -> None:
        path = vpr.write_vpr(self.song, str(self.tmp / "a.vpr"), _bank())
        with zipfile.ZipFile(path) as archive:
            project = json.loads(archive.read("Project/sequence.json"))
        notes = project["tracks"][0]["parts"][0]["notes"]
        self.assertEqual(notes[2]["pos"], self.half)
        self.assertEqual(notes[2]["duration"], round(self.note.dur / 2))

    def test_preconverted_formats_are_not_double_scaled(self) -> None:
        """acep/s5p 自己会换算；resample 之后再走一次必须得到相同结果。"""
        from vocaloidtts.formats import acep, s5p
        start = self.note.start
        self.assertEqual(acep._ticks(self.song, start),
                         int(round(start / 2)))
        self.assertEqual(s5p._blick(self.song, start),
                         int(round(start / 2)) * s5p.BLICK_PER_TICK)
        self.assertEqual(s5p._blick(base.resample(self.song), self.half),
                         int(round(start / 2)) * s5p.BLICK_PER_TICK)

    def test_vfp_ticks_and_seconds_agree(self) -> None:
        path = vfp.write_vfp(self.song, str(self.tmp / "a.vfp"))
        with zipfile.ZipFile(path) as archive:
            project = json.loads(archive.read("project.json"))
        clip = next(iter(project["trackBank"][project["trackOrder"][0]]["clipBank"].values()))
        notes = list(clip["noteBank"].values())
        bpm = project["tempo"]
        for note in notes:
            self.assertEqual(note["durationTicks"],
                             max(1, round(note["duration"] * bpm * 480 / 60)))
            self.assertEqual(note["ticks"],
                             round(note["time"] * bpm * 480 / 60))

    def test_midi_division_stays_at_480(self) -> None:
        path = mid.write_mid(self.song, str(self.tmp / "a.mid"))
        data = Path(path).read_bytes()
        self.assertEqual(int.from_bytes(data[12:14], "big"), mid.DIVISION)
        self.assertEqual(mid.DIVISION, 480)

    def test_voisona_clock_is_twice_the_half_tick(self) -> None:
        path = tssln.write_tssln(self.song, str(self.tmp / "a.tssln"))
        # 结构由 test_tssln 的读取器负责解析，这里只确认换算常量没有被改坏
        self.assertTrue(Path(path).read_bytes())
        self.assertEqual(tssln._clock(self.half), self.half * tssln.CLOCK_PER_TICK)

    def test_cevio_clock_uses_half_the_ticks(self) -> None:
        path = ccs.write_ccs(self.song, str(self.tmp / "a.ccs"))
        import xml.etree.ElementTree as ET
        root = ET.fromstring(Path(path).read_text(encoding="utf-8"))
        clocks = [int(el.get("Clock", "0")) for el in root.iter()
                  if el.tag.lower().endswith("note")]
        self.assertIn(self.half * ccs.CLOCK_PER_TICK, clocks)


if __name__ == "__main__":
    unittest.main()
