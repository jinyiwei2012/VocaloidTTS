"""VX-β .vxf 导出的结构回归。

.vxf 是二进制（MIDI 2.0 UMP 包），所以测试里自带一个独立写的读取器：按包体
首字节判断类型、按 UMP 约定还原音符号，再用它核对导出结果。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vocaloidtts.formats import formats, vxf
from vocaloidtts.prosody import VoiceOptions, compose

BASE_DELTA_TICKS = 0x40


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "big")


def _parse(data: bytes) -> dict:
    """独立实现的最小读取器，只认我们写出去的那几种包。"""
    assert data[:8] == b"SMF2CLIP", data[:8]
    result = {"ppqn": _u32(data, 8) - (0x30 << 16), "events": []}
    pos = 12
    # 轨道名包：d0 <seq_stat> 01 03 + 12 字节
    titles = []
    while data[pos] == 0xD0 and data[pos + 2:pos + 4] == b"\x01\x03":
        titles.append(data[pos + 4:pos + 16].rstrip(b"\x00").decode("utf-8"))
        pos += 16
    result["titles"] = titles
    assert data[pos:pos + 4] == b"\xf0\x20\x00\x00", data[pos:pos + 4]
    pos += 16

    tick = 0
    while True:
        if data[pos:pos + 4] == b"\xf0\x21\x00\x00":
            pos += 16
            break
        tick += _u32(data, pos) - (BASE_DELTA_TICKS << 16)
        pos += 4
        if data[pos:pos + 4] == b"\xd0\x10\x00\x00":
            result["events"].append((tick, "tempo", _u32(data, pos + 4)))
            pos += 16
        elif data[pos:pos + 4] == b"\xd0\x10\x00\x01":
            result["events"].append((tick, "time_signature",
                                     (data[pos + 4], 1 << data[pos + 5])))
            pos += 16
        elif data[pos] == 0xD0 and data[pos + 2:pos + 4] == b"\x01\x50":
            seq_stat = data[pos + 1]
            if (seq_stat - 16) // 64 <= 1:
                # seq_stat + magic 之后还有 2 字节的 seq_num
                text = data[pos + 6:pos + 16].rstrip(b"\x00").decode("ascii")
            else:
                text = data[pos + 4:pos + 16].rstrip(b"\x00").decode("ascii")
            result["events"].append((tick, "lyrics", text))
            pos += 16
        elif data[pos] == 0xD0 and data[pos + 2:pos + 4] == b"\x01\x51":
            result["events"].append((tick, "metadata",
                                     data[pos + 4:pos + 16].decode("utf-8")))
            pos += 16
        else:
            word = _u32(data, pos)
            kind = "note_on" if (word >> 16) == 0x4090 else "note_off"
            note = (word - (0x4090 << 16)) >> 8
            result["events"].append((tick, kind, note))
            pos += 8
    assert pos == len(data), (pos, len(data))
    return result


class VxfExportTests(unittest.TestCase):
    def _parsed(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = vxf.FORMAT.writer(compose("你好世界", VoiceOptions(seed=42)),
                                 str(Path(tmp.name) / "x.vxf"))
        return _parse(path.read_bytes())

    def test_header(self) -> None:
        parsed = self._parsed()
        self.assertEqual(parsed["ppqn"], vxf.TICKS_PER_BEAT)
        self.assertEqual("".join(parsed["titles"]), "VocaloidTTS")

    def test_tempo_and_time_signature(self) -> None:
        events = self._parsed()["events"]
        tempo = [item for item in events if item[1] == "tempo"]
        self.assertEqual(len(tempo), 1)
        # 反比存法：120 BPM -> 14208605
        self.assertEqual(tempo[0][2], int(1705032600 / 120))
        signature = [item for item in events if item[1] == "time_signature"]
        self.assertEqual(signature, [(0, "time_signature", (4, 4))])

    def test_notes(self) -> None:
        events = self._parsed()["events"]
        song = compose("你好世界", VoiceOptions(seed=42))
        ons = [item for item in events if item[1] == "note_on"]
        offs = [item for item in events if item[1] == "note_off"]
        self.assertEqual(len(ons), len(song.notes))
        self.assertEqual(len(offs), len(song.notes))
        self.assertEqual([item[2] for item in ons],
                         [note.midi for note in song.notes])
        self.assertEqual([item[0] for item in ons],
                         [note.start for note in song.notes])

    def test_lyrics_are_ascii(self) -> None:
        events = self._parsed()["events"]
        lyrics = [item[2] for item in events if item[1] == "lyrics"]
        self.assertEqual(lyrics, ["ni", "hao", "shi", "jie"])

    def test_metadata_carries_pitch_json(self) -> None:
        events = self._parsed()["events"]
        pieces = [item[2] for item in events if item[1] == "metadata"]
        self.assertGreater(len(pieces), 0)
        self.assertTrue(all(len(piece) == 12 for piece in pieces[:-1]))
        joined = "".join(pieces)
        self.assertIn("TimeBasedPitchSequence", joined)
        self.assertTrue(joined.startswith("{"))

    def test_event_times_are_monotonic(self) -> None:
        events = self._parsed()["events"]
        times = [item[0] for item in events]
        self.assertEqual(times, sorted(times))

    def test_empty_song_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            vxf.write_vxf(compose("", VoiceOptions(seed=1)), "x.vxf")

    def test_registry(self) -> None:
        self.assertEqual(formats()["vxf"].extension, ".vxf")


if __name__ == "__main__":
    unittest.main()
