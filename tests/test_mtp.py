"""Muta .mtp 导出的结构回归。

.mtp 是二进制（小端、UTF-16LE 字符串、数组前带换行标记），所以测试里自带
一个独立写的读取器：按固定长度切出各段，再逐字段核对。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vocaloidtts.formats import formats, mtp
from vocaloidtts.prosody import VoiceOptions, compose

NOTE_SIZE = 4 + 4 + 4 + 16 + 16 + 40


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little")


def _i32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little", signed=True)


def _array(data: bytes, offset: int, item_size: int) -> tuple[list[bytes], int]:
    """读一个「换行 + u32 个数 + 每个元素前再加换行」的数组。"""
    assert data[offset:offset + 1] == b"\n", (offset, data[offset:offset + 1])
    offset += 1
    count = _u32(data, offset)
    offset += 4
    items = []
    for _ in range(count):
        assert data[offset:offset + 1] == b"\n"
        offset += 1
        items.append(data[offset:offset + item_size])
        offset += item_size
    return items, offset


def _parse(data: bytes) -> dict:
    version = _u32(data, 0)
    tempos, offset = _array(data, 4, 8)
    signatures, offset = _array(data, offset, 12)

    assert data[offset:offset + 1] == b"\n"
    offset += 1
    track_count = _u32(data, offset)
    offset += 4
    tracks = []
    for _ in range(track_count):
        assert data[offset:offset + 1] == b"\n"
        offset += 1
        track_type = _u32(data, offset)
        seq_count = _u32(data, offset + 4)
        offset += 8
        assert data[offset:offset + 1] == b"\n"
        offset += 1
        mute, solo, volume, pan = (_u32(data, offset + 4 * i) for i in range(4))
        offset += 16
        name = data[offset:offset + 12].decode("utf-16-le").rstrip("\x00")
        offset += 12 + 52

        assert data[offset:offset + 1] == b"\n"
        offset += 1
        start = _u32(data, offset)
        length = _u32(data, offset + 4)
        offset += 8
        singer = data[offset:offset + 516]
        offset += 516
        speaker = _u32(data, offset)
        offset += 4
        raw_notes, offset = _array(data, offset, NOTE_SIZE)
        params = []
        for _ in range(8):
            points, offset = _array(data, offset, 8)
            params.append(points)

        notes = [{
            "start": _i32(item, 0),
            "length": _u32(item, 4),
            "key": _u32(item, 8),
            "lyric": "".join(
                chr(int.from_bytes(item[12 + 2 * i:14 + 2 * i], "little"))
                for i in range(8)
            ).rstrip("\x00"),
            "phoneme": item[28:44].decode("utf-16-le").rstrip("\x00"),
        } for item in raw_notes]
        tracks.append({
            "type": track_type, "seq": seq_count, "name": name,
            "mute": mute, "solo": solo, "volume": volume, "pan": pan,
            "start": start, "length": length, "singer": singer,
            "speaker": speaker, "notes": notes, "params": params,
        })

    assert data[offset:offset + 1] == b"\n"
    offset += 1
    assert offset == len(data), (offset, len(data))
    return {"version": version, "tempos": tempos, "signatures": signatures,
            "tracks": tracks}


class MtpExportTests(unittest.TestCase):
    def _parsed(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = mtp.FORMAT.writer(compose("你好世界", VoiceOptions(seed=42)),
                                 str(Path(tmp.name) / "x.mtp"))
        return _parse(path.read_bytes())

    def test_header(self) -> None:
        parsed = self._parsed()
        self.assertEqual(parsed["version"], mtp.FILE_VERSION)
        self.assertEqual(len(parsed["tempos"]), 1)
        tempo = parsed["tempos"][0]
        self.assertEqual(_i32(tempo, 0), 0)
        self.assertEqual(_u32(tempo, 4), 12000)      # BPM 乘 100

    def test_time_signature(self) -> None:
        signatures = self._parsed()["signatures"]
        self.assertEqual(len(signatures), 1)
        item = signatures[0]
        self.assertEqual((_i32(item, 0), _u32(item, 4), _u32(item, 8)), (0, 4, 4))

    def test_track_header(self) -> None:
        track = self._parsed()["tracks"][0]
        self.assertEqual(track["type"], mtp.TRACK_TYPE_SONG)
        self.assertEqual(track["seq"], 1)
        # 轨道名字段只有 12 字节 = 6 个 UTF-16 字符，长标题会被截断
        self.assertEqual(track["name"], "Vocalo")
        self.assertEqual((track["mute"], track["solo"]), (0, 0))
        self.assertEqual((track["volume"], track["pan"]), (50, 50))
        self.assertEqual(track["start"], 0)

    def test_notes(self) -> None:
        track = self._parsed()["tracks"][0]
        song = compose("你好世界", VoiceOptions(seed=42))
        self.assertEqual(len(track["notes"]), len(song.notes))
        for index, note in enumerate(track["notes"]):
            source = song.notes[index]
            self.assertEqual(note["start"], source.start)
            self.assertEqual(note["length"], source.dur)
            # 音高轴是反的：key = 139 - MIDI
            self.assertEqual(note["key"], mtp.KEY_ORIGIN - source.midi)
            self.assertEqual(note["lyric"], source.lyric)
            self.assertEqual(note["phoneme"], source.lyric)

    def test_params_order(self) -> None:
        """参数区有八个数组，pitch_data 是第四个——顺序错了就写进别的通道。"""
        track = self._parsed()["tracks"][0]
        self.assertEqual(len(track["params"]), 8)
        self.assertEqual([len(item) for item in track["params"][:3]], [0, 0, 0])
        self.assertGreater(len(track["params"][3]), 0)
        self.assertEqual([len(item) for item in track["params"][4:]], [0, 0, 0, 0])
        time, value = _i32(track["params"][3][0], 0), _i32(track["params"][3][0], 4)
        self.assertGreaterEqual(time, 0)
        self.assertLess(value, 12900)

    def test_singer_name_is_utf16(self) -> None:
        track = self._parsed()["tracks"][0]
        # 258 个 u16 的名字槽位，前四个是 "Muta"
        self.assertEqual(track["singer"][:8].decode("utf-16-le"), "Muta")

    def test_empty_song_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            mtp.write_mtp(compose("", VoiceOptions(seed=1)), "x.mtp")

    def test_registry(self) -> None:
        self.assertEqual(formats()["mtp"].extension, ".mtp")


if __name__ == "__main__":
    unittest.main()
