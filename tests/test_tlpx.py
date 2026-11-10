"""TuneLab 新版 .tlpx 导出的结构回归。

.tlpx 是 CBOR 而不是 JSON。为了不让测试依赖 cbor2，这里自带一个最小的
CBOR 解码器——独立实现，正好用来验证 base.cbor_dumps 编出来的东西能被读懂。
"""
from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from vocaloidtts.formats import formats, tlpx
from vocaloidtts.formats.base import cbor_dumps
from vocaloidtts.prosody import VoiceOptions, compose


def _read(data: bytes, offset: int):
    initial = data[offset]
    offset += 1
    major, info = initial >> 5, initial & 0x1F
    if info < 24:
        arg = info
    elif info == 24:
        arg = data[offset]
        offset += 1
    elif info == 25:
        arg = int.from_bytes(data[offset:offset + 2], "big")
        offset += 2
    elif info == 26:
        arg = int.from_bytes(data[offset:offset + 4], "big")
        offset += 4
    elif info == 27:
        arg = int.from_bytes(data[offset:offset + 8], "big")
        offset += 8
    else:
        raise AssertionError(f"不支持的附加信息：{info}")

    if major == 0:
        return arg, offset
    if major == 1:
        return -1 - arg, offset
    if major == 2:
        return bytes(data[offset:offset + arg]), offset + arg
    if major == 3:
        return data[offset:offset + arg].decode("utf-8"), offset + arg
    if major == 4:
        items = []
        for _ in range(arg):
            item, offset = _read(data, offset)
            items.append(item)
        return items, offset
    if major == 5:
        result = {}
        for _ in range(arg):
            key, offset = _read(data, offset)
            item, offset = _read(data, offset)
            result[key] = item
        return result, offset
    if major == 7:
        if info == 20:
            return False, offset
        if info == 21:
            return True, offset
        if info == 22:
            return None, offset
        if info == 27:
            return struct.unpack(">d", arg.to_bytes(8, "big"))[0], offset
    raise AssertionError(f"不支持的 CBOR 类型：major={major} info={info}")


def _decode(data: bytes):
    value, offset = _read(data, 0)
    if offset != len(data):
        raise AssertionError(f"帧尾有多余字节：{offset} != {len(data)}")
    return value


def _song():
    return compose("你好世界", VoiceOptions(seed=42))


class CborEncoderTests(unittest.TestCase):
    def test_scalars_round_trip(self) -> None:
        for value in (0, 23, 24, 255, 256, 65535, 65536, 2**33,
                      -1, -24, -25, -65537, 1.5, -0.25, True, False, None,
                      "你好", ""):
            with self.subTest(value=value):
                decoded = _decode(cbor_dumps(value))
                self.assertEqual(decoded, value)
                self.assertIs(type(decoded), type(value))

    def test_containers_round_trip(self) -> None:
        value = {"a": [1, 2, {"b": "中文"}], "c": None, "d": [True, False]}
        self.assertEqual(_decode(cbor_dumps(value)), value)

    def test_empty_containers(self) -> None:
        self.assertEqual(_decode(cbor_dumps([])), [])
        self.assertEqual(_decode(cbor_dumps({})), {})

    def test_unknown_type_is_reported(self) -> None:
        with self.assertRaises(TypeError):
            cbor_dumps({1, 2})


class TlpxExportTests(unittest.TestCase):
    def _project(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = tlpx.FORMAT.writer(_song(), str(Path(tmp.name) / "x.tlpx"))
        return _decode(path.read_bytes())

    def test_top_level(self) -> None:
        project = self._project()
        self.assertEqual(project["version"], 1)
        self.assertEqual(project["tempos"], [{"pos": 0, "bpm": 120.0}])
        self.assertEqual(project["timeSignatures"],
                         [{"numerator": 4, "denominator": 4, "barIndex": 0}])
        self.assertEqual(len(project["tracks"]), 1)
        self.assertIn("editorInfo", project)
        self.assertIn("exportConfig", project)

    def test_part_uses_offsets_not_dur(self) -> None:
        part = self._project()["tracks"][0]["parts"][0]
        self.assertEqual(part["type"], "midi")
        self.assertEqual(part["startOffset"], 0)
        self.assertNotIn("dur", part)
        self.assertEqual(part["endOffset"] % 1920, 0)
        self.assertGreater(part["endOffset"], 0)

    def test_notes(self) -> None:
        part = self._project()["tracks"][0]["parts"][0]
        song = _song()
        self.assertEqual(len(part["notes"]), len(song.notes))
        first = part["notes"][0]
        self.assertEqual(first["pos"], song.notes[0].start)
        self.assertEqual(first["dur"], song.notes[0].dur)
        self.assertEqual(first["pitch"], song.notes[0].midi)
        self.assertEqual(first["lyric"], "你")
        self.assertEqual(first["pronunciation"], "ni")

    def test_pitch_curve_is_flat_float_list(self) -> None:
        part = self._project()["tracks"][0]["parts"][0]
        self.assertEqual(len(part["pitch"]), 1)
        flat = part["pitch"][0]
        self.assertEqual(len(flat) % 2, 0)
        self.assertEqual(flat[0::2], sorted(flat[0::2]))

    def test_export_is_reproducible(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        first = tlpx.FORMAT.writer(_song(), str(Path(tmp.name) / "a.tlpx")).read_bytes()
        second = tlpx.FORMAT.writer(_song(), str(Path(tmp.name) / "b.tlpx")).read_bytes()
        self.assertEqual(first, second)

    def test_empty_song_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            tlpx.write_tlpx(compose("", VoiceOptions(seed=1)), "x.tlpx")

    def test_registry(self) -> None:
        self.assertEqual(formats()["tlpx"].extension, ".tlpx")


if __name__ == "__main__":
    unittest.main()
