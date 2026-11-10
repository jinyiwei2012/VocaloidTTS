"""VOCALOID2 .vsq 导出的结构回归。

.vsq 是「MIDI 文件里装文本」：外层 SMF，正文在 meta 0x01 文本事件里，
每条带 ``DM:nnnn:`` 前缀。测试自带一个 MIDI 读取器把文本事件拼回来。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vocaloidtts.formats import formats, vsq
from vocaloidtts.prosody import VoiceOptions, compose
from vocaloidtts.voicebank import Voicebank


def _vlq(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    while True:
        byte = data[offset]
        offset += 1
        value = (value << 7) | (byte & 0x7F)
        if byte < 0x80:
            return value, offset


def _tracks(data: bytes) -> list[bytes]:
    assert data[:4] == b"MThd", data[:4]
    length = int.from_bytes(data[4:8], "big")
    offset = 8 + length
    tracks = []
    while offset < len(data):
        assert data[offset:offset + 4] == b"MTrk", data[offset:offset + 4]
        size = int.from_bytes(data[offset + 4:offset + 8], "big")
        tracks.append(data[offset + 8:offset + 8 + size])
        offset += 8 + size
    return tracks


def _meta_events(body: bytes) -> list[tuple[int, int, bytes]]:
    events = []
    offset = 0
    while offset < len(body):
        _, offset = _vlq(body, offset)
        if body[offset] != 0xFF:
            raise AssertionError(f"只预期 meta 事件，遇到 {body[offset]:#04x}")
        kind = body[offset + 1]
        size, offset = _vlq(body, offset + 2)
        events.append((kind, size, body[offset:offset + size]))
        offset += size
    return events


def _vsq_text(data: bytes) -> str:
    events = _meta_events(_tracks(data)[1])
    pieces = [payload[8:].decode("utf-8") for kind, _, payload in events if kind == 0x01]
    return "".join(pieces)


class VsqExportTests(unittest.TestCase):
    def _bank(self):
        return Voicebank("BTESTBANK0000001", "Test", "测试", bs=4, pc=0, source="test")

    def _bytes(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = vsq.FORMAT.writer(compose("你好世界", VoiceOptions(seed=42)),
                                 str(Path(tmp.name) / "x.vsq"),
                                 voicebank=self._bank())
        return path.read_bytes()

    def test_midi_header(self) -> None:
        data = self._bytes()
        self.assertEqual(data[:4], b"MThd")
        self.assertEqual(int.from_bytes(data[8:10], "big"), 1)    # format 1
        self.assertEqual(int.from_bytes(data[10:12], "big"), 2)   # 两条轨道
        self.assertEqual(int.from_bytes(data[12:14], "big"), vsq.TICKS_PER_QUARTER)

    def test_master_track(self) -> None:
        events = _meta_events(_tracks(self._bytes())[0])
        kinds = [kind for kind, _, _ in events]
        self.assertEqual(kinds, [0x03, 0x51, 0x58, 0x2F])
        self.assertEqual(events[0][2], b"Master Track")
        self.assertEqual(len(events[1][2]), 3)          # tempo 3 字节
        self.assertEqual(events[2][2][:2], bytes([4, 2]))  # 4/4

    def test_text_is_chunked_with_prefix(self) -> None:
        body = _meta_events(_tracks(self._bytes())[1])
        texts = [payload for kind, _, payload in body if kind == 0x01]
        self.assertGreater(len(texts), 0)
        for index, payload in enumerate(texts):
            self.assertTrue(payload.startswith(f"DM:{index:04d}:".encode("ascii")))
        self.assertEqual(body[-1][0], 0x2F)

    def test_vsq_sections(self) -> None:
        text = _vsq_text(self._bytes())
        for marker in ("[Common]", "Version=DSB301", "[Master]", "[Mixer]",
                       "[EventList]", "[ID#0000]", "[h#0000]"):
            self.assertIn(marker, text)
        self.assertIn("PreMeasure=1", text)
        self.assertIn("Tracks=1", text)

    def test_notes_and_lyrics(self) -> None:
        text = _vsq_text(self._bytes())
        song = compose("你好世界", VoiceOptions(seed=42))
        self.assertIn("[ID#0001]", text)
        self.assertIn("Type=Anote", text)
        self.assertIn(f"Note#={song.notes[0].midi}", text)
        self.assertIn(f"Length={song.notes[0].dur}", text)
        self.assertIn('L0="ni"', text)
        self.assertIn("IDS=Test", text)
        # 事件表里的 tick 带前导小节
        self.assertIn(f"{song.notes[0].start + vsq.PREFIX_TICKS}=ID#0001", text)
        self.assertIn("=EOS", text)

    def test_curves(self) -> None:
        text = _vsq_text(self._bytes())
        self.assertIn("[PitchBendBPList]", text)
        self.assertIn("[PitchBendSensBPList]", text)
        self.assertIn("[DynamicsBPList]", text)

    def test_utf8_chunks_stay_under_limit(self) -> None:
        """切段按字节算，中文不会被切坏。"""
        body = _meta_events(_tracks(self._bytes())[1])
        for kind, _, payload in body:
            if kind == 0x01:
                self.assertLessEqual(len(payload), 0x7F)

    def test_empty_song_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            vsq.write_vsq(compose("", VoiceOptions(seed=1)), "x.vsq",
                          voicebank=self._bank())

    def test_registry(self) -> None:
        self.assertEqual(formats()["vsq"].extension, ".vsq")
        self.assertTrue(formats()["vsq"].needs_voicebank)


if __name__ == "__main__":
    unittest.main()
