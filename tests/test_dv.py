"""DeepVocal .dv 导出的结构回归。

.dv 是二进制（小端、u32 长度前缀的字符串、两种数组写法），所以测试里自带一个
独立写的读取器，按字段顺序切完再核对。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vocaloidtts.formats import dv, formats
from vocaloidtts.formats.base import lyric_for
from vocaloidtts.prosody import VoiceOptions, compose


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little")


def _i32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little", signed=True)


def _str(data: bytes, offset: int) -> tuple[str, int]:
    size = _u32(data, offset)
    offset += 4
    return data[offset:offset + size].decode("utf-8"), offset + size


def _prefixed(data: bytes, offset: int) -> tuple[int, int, int]:
    """u32 字节长度 + u32 元素个数，返回 (个数, 数据起点, 结束位置)。"""
    total = _u32(data, offset)
    offset += 4
    end = offset + total
    count = _u32(data, offset)
    return count, offset + 4, end


def _points(data: bytes, offset: int) -> tuple[list[tuple[int, int]], int]:
    count, start, end = _prefixed(data, offset)
    points = [(_i32(data, start + 8 * i), _i32(data, start + 8 * i + 4))
              for i in range(count)]
    return points, end


def _note(data: bytes, offset: int) -> tuple[dict, int]:
    note = {}
    note["start"] = _i32(data, offset)
    note["length"] = _u32(data, offset + 4)
    note["key"] = _u32(data, offset + 8)
    note["vibrato"] = _u32(data, offset + 12)
    offset += 16
    note["phoneme"], offset = _str(data, offset)
    note["word"], offset = _str(data, offset)
    offset += 1                                     # padding_1
    # note_vibrato_data 外面还有一层 u32 字节长度，里面是「u32 个数 + 三个参数曲线」
    total = _u32(data, offset)
    offset += 4
    vibrato_end = offset + total
    offset += 4                                     # 跳过外层个数
    _, offset = _points(data, offset)               # amplitude
    _, offset = _points(data, offset)               # frequency
    _, offset = _points(data, offset)               # vibrato
    offset = vibrato_end
    count, start, offset = _prefixed(data, offset)  # unknown
    note["unknown_count"] = count
    offset += 18                                    # phonemes 结构
    offset += 16                                    # 四个 u32
    note["timbre"] = _i32(data, offset)
    offset += 4
    _, offset = _str(data, offset)                  # cross_lyric
    note["cross_timbre"] = _i32(data, offset)
    offset += 4
    return note, offset


def _parse(data: bytes) -> dict:
    assert data[:8] == b"SHARPKEY", data[:8]
    version = _u32(data, 8)
    inner_len = _u32(data, 12)
    assert 16 + inner_len == len(data), (16 + inner_len, len(data))
    offset = 16
    features = data[offset:offset + 28]
    offset += 28

    tempo_count, start, offset = _prefixed(data, offset)
    tempos = [(_i32(data, start + 8 * i), _u32(data, start + 8 * i + 4))
              for i in range(tempo_count)]

    sig_count, start, offset = _prefixed(data, offset)
    signatures = [(_i32(data, start + 12 * i), _u32(data, start + 12 * i + 4),
                   _u32(data, start + 12 * i + 8)) for i in range(sig_count)]

    track_count = _u32(data, offset)
    offset += 4
    track_type = _u32(data, offset)
    offset += 4
    name, offset = _str(data, offset)
    mute, solo = data[offset], data[offset + 1]
    volume = _u32(data, offset + 2)
    offset += 6
    offset += 4                                     # balance
    seg_count, start, offset = _prefixed(data, offset)

    segment = {}
    seg_offset = start
    segment["start"] = _u32(data, seg_offset)
    segment["length"] = _u32(data, seg_offset + 4)
    seg_offset += 8
    _, seg_offset = _str(data, seg_offset)          # segment name
    _, seg_offset = _str(data, seg_offset)          # singer name
    note_count, note_start, seg_offset = _prefixed(data, seg_offset)
    notes = []
    for _ in range(note_count):
        note, note_start = _note(data, note_start)
        notes.append(note)
    seg_offset = note_start
    for _ in range(7):                              # 七个参数曲线
        _, seg_offset = _points(data, seg_offset)
    assert seg_offset == offset, (seg_offset, offset)

    return {
        "version": version, "features": features, "tempos": tempos,
        "signatures": signatures, "track_count": track_count,
        "track_type": track_type, "name": name, "mute": mute, "solo": solo,
        "volume": volume, "seg_count": seg_count, "segment": segment,
        "notes": notes,
    }


class DvExportTests(unittest.TestCase):
    def _parsed(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = dv.FORMAT.writer(compose("你好世界", VoiceOptions(seed=42)),
                                str(Path(tmp.name) / "x.dv"))
        return _parse(path.read_bytes())

    def test_header(self) -> None:
        parsed = self._parsed()
        self.assertEqual(parsed["version"], dv.FILE_VERSION)
        self.assertEqual(parsed["features"], dv.FEATURES)

    def test_tempo_and_signature(self) -> None:
        parsed = self._parsed()
        self.assertEqual(parsed["tempos"], [(0, 12000)])
        self.assertEqual(parsed["signatures"], [(0, 4, 4)])

    def test_track(self) -> None:
        parsed = self._parsed()
        self.assertEqual(parsed["track_count"], 1)
        self.assertEqual(parsed["track_type"], dv.TRACK_TYPE_SINGING)
        self.assertEqual(parsed["name"], "VocaloidTTS")
        self.assertEqual(parsed["volume"], dv.DEFAULT_VOLUME)
        self.assertEqual(parsed["seg_count"], 1)

    def test_segment_and_notes(self) -> None:
        parsed = self._parsed()
        song = compose("你好世界", VoiceOptions(seed=42))
        segment = parsed["segment"]
        self.assertEqual(segment["start"], 0)
        self.assertEqual(segment["length"],
                         max(n.start + n.dur for n in song.notes))
        self.assertEqual(len(parsed["notes"]), len(song.notes))
        for index, note in enumerate(parsed["notes"]):
            source = song.notes[index]
            self.assertEqual(note["start"], source.start)
            self.assertEqual(note["length"], source.dur)
            # 音高轴是反的：key = 115 - MIDI
            self.assertEqual(note["key"], dv.NOTE_KEY_SUM - source.midi)
            self.assertEqual(note["phoneme"], source.lyric)
            self.assertEqual(note["word"], lyric_for(source))

    def test_unknown_block_is_empty(self) -> None:
        """LibreSVIP 会塞一整块浮点常量，这里明确留空。"""
        for note in self._parsed()["notes"]:
            self.assertEqual(note["unknown_count"], 0)

    def test_empty_song_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            dv.write_dv(compose("", VoiceOptions(seed=1)), "x.dv")

    def test_registry(self) -> None:
        self.assertEqual(formats()["dv"].extension, ".dv")


if __name__ == "__main__":
    unittest.main()
