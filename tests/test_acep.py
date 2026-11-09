"""ACE Studio .acep 导出的结构回归。"""
from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path

from vocaloidtts.formats import acep, formats
from vocaloidtts.prosody import VoiceOptions, compose

try:  # Python 3.14+ 自带 zstd；更早的版本装 zstandard 也能解
    from compression.zstd import decompress as _zstd_decompress
except ImportError:  # pragma: no cover - 取决于解释器版本
    try:
        from zstandard import ZstdDecompressor as _ZC

        _zstd_decompress = lambda data: _ZC().decompress(data)  # noqa: E731
    except ImportError:
        _zstd_decompress = None


def _walk_frame(data: bytes) -> list[tuple[int, int, int]]:
    """按 RFC 8878 拆 zstd 帧，返回 [(块类型, 块长度, 是否最后一块)]。"""
    if data[:4] != b"\x28\xb5\x2f\xfd":
        raise AssertionError(f"zstd magic 不对：{data[:4]!r}")
    descriptor = data[4]
    if descriptor != 0xA0:
        raise AssertionError(f"帧头描述符不是 0xa0：{descriptor:#04x}")
    declared = int.from_bytes(data[5:9], "little")
    pos, blocks = 9, []
    while True:
        header = int.from_bytes(data[pos:pos + 3], "little")
        pos += 3
        last = header & 1
        block_type = (header >> 1) & 3
        length = header >> 3
        blocks.append((block_type, length, last))
        pos += length
        if last:
            break
    if pos != len(data):
        raise AssertionError(f"帧尾有多余字节：{pos} != {len(data)}")
    if sum(length for _, length, _ in blocks) != declared:
        raise AssertionError("帧头声明的内容长度和块长度之和不一致")
    return blocks


class AcepFrameTests(unittest.TestCase):
    def test_single_raw_block(self) -> None:
        payload = "你好，世界".encode()
        frame = acep._zstd_store(payload)
        self.assertEqual(_walk_frame(frame), [(0, len(payload), 1)])

    def test_payload_is_split_into_blocks(self) -> None:
        payload = b"x" * (acep.ZSTD_BLOCK_MAX * 2 + 5)
        blocks = _walk_frame(acep._zstd_store(payload))
        self.assertEqual([length for _, length, _ in blocks],
                         [acep.ZSTD_BLOCK_MAX, acep.ZSTD_BLOCK_MAX, 5])
        self.assertEqual([last for _, _, last in blocks], [0, 0, 1])

    def test_empty_payload_still_has_a_last_block(self) -> None:
        self.assertEqual(_walk_frame(acep._zstd_store(b"")), [(0, 0, 1)])

    @unittest.skipIf(_zstd_decompress is None, "当前解释器没有 zstd 解码器")
    def test_frame_round_trips_through_a_real_decoder(self) -> None:
        payload = json.dumps({"a": "中文", "n": list(range(50))}).encode()
        self.assertEqual(_zstd_decompress(acep._zstd_store(payload)), payload)


class AcepExportTests(unittest.TestCase):
    def _song(self):
        return compose("你好世界", VoiceOptions(seed=42))

    def _export(self):
        song = self._song()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = acep.write_acep(song, str(Path(tmp.name) / "x.acep"))
        return song, path, json.loads(path.read_text(encoding="utf-8"))

    def test_container_wrapper(self) -> None:
        _, path, wrapper = self._export()
        self.assertEqual(path.suffix, ".acep")
        self.assertEqual(wrapper["compressMethod"], "zstd")
        self.assertEqual(wrapper["version"], acep.CONTAINER_VERSION)
        self.assertEqual(wrapper["salt"], "")
        # content 必须是能 base64 解开的 zstd 帧
        raw = base64.b64decode(wrapper["content"])
        _walk_frame(raw)

    @unittest.skipIf(_zstd_decompress is None, "当前解释器没有 zstd 解码器")
    def test_content_decompresses_to_the_project(self) -> None:
        _, _, wrapper = self._export()
        project = json.loads(_zstd_decompress(base64.b64decode(wrapper["content"])))
        self.assertEqual(project["version"], acep.PROJECT_VERSION)
        self.assertEqual(len(project["tracks"]), 1)
        self.assertEqual(project["tracks"][0]["type"], "sing")
        self.assertEqual(project["tracks"][0]["language"], "CHN")
        notes = project["tracks"][0]["patterns"][0]["notes"]
        self.assertEqual(len(notes), len(self._song().notes))

    def test_project_structure(self) -> None:
        song = self._song()
        project = acep.build_project(song)
        track = project["tracks"][0]
        pattern = track["patterns"][0]
        notes = pattern["notes"]
        self.assertEqual(len(notes), len(song.notes))
        self.assertEqual(pattern["timeUnit"], "tick")
        self.assertEqual(project["timeSignatures"][0]["numerator"], song.numerator)
        self.assertEqual(project["beatsPerBar"], song.numerator * 4 // song.denominator)
        self.assertEqual(project["tempos"][0]["bpm"], song.bpm)
        # 音符位置是相对 pattern 起点的
        self.assertEqual(notes[0]["pos"], song.notes[0].start - pattern["pos"])
        self.assertEqual(notes[0]["pitch"], song.notes[0].midi)
        self.assertEqual(notes[0]["dur"], song.notes[0].dur)
        # 参数曲线留空，交给 ACE 自己算
        self.assertEqual(pattern["parameters"]["pitchDelta"], [])

    def test_chinese_lyric_stays_han(self) -> None:
        """ACE 的中文歌词栏收汉字，不像 VSQX 那样要拼音。"""
        project = acep.build_project(self._song())
        notes = project["tracks"][0]["patterns"][0]["notes"]
        self.assertEqual([n["lyric"] for n in notes], list("你好世界"))
        self.assertTrue(all(n["pronunciation"] is None for n in notes))

    def test_empty_song_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            acep.write_acep(compose("", VoiceOptions(seed=1)), "x.acep")

    def test_registry_lists_acep(self) -> None:
        self.assertEqual(formats()["acep"].extension, ".acep")


if __name__ == "__main__":
    unittest.main()
