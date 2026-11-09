"""DiffScope .dspx 导出的结构回归。

.dspx 是 zstd 帧里装 JSON，所以测试要先把帧解开再核对字段。
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vocaloidtts.formats import dspx, formats
from vocaloidtts.formats.base import ZSTD_BLOCK_MAX, zstd_store
from vocaloidtts.prosody import VoiceOptions, compose

try:
    from compression.zstd import decompress as _zstd_decompress
except ImportError:  # pragma: no cover - 取决于解释器版本
    try:
        from zstandard import ZstdDecompressor as _ZC

        _zstd_decompress = lambda data: _ZC().decompress(data)  # noqa: E731
    except ImportError:
        _zstd_decompress = None


class DspxExportTests(unittest.TestCase):
    def _bytes(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = dspx.FORMAT.writer(compose("你好世界", VoiceOptions(seed=42)),
                                  str(Path(tmp.name) / "x.dspx"))
        return path.read_bytes()

    def _model(self):
        return dspx.build_model(compose("你好世界", VoiceOptions(seed=42)))

    def test_file_is_a_zstd_frame(self) -> None:
        data = self._bytes()
        self.assertEqual(data[:4], b"\x28\xb5\x2f\xfd")

    @unittest.skipIf(_zstd_decompress is None, "当前解释器没有 zstd 解码器")
    def test_frame_decompresses_to_json(self) -> None:
        payload = _zstd_decompress(self._bytes())
        model = json.loads(payload)
        self.assertEqual(model["version"], "1.0.0")
        self.assertIn("content", model)

    def test_top_level_shape(self) -> None:
        model = self._model()
        self.assertEqual(model["version"], dspx.PROJECT_VERSION)
        content = model["content"]
        for key in ("global", "master", "timeline", "tracks", "workspace"):
            self.assertIn(key, content)
        self.assertEqual(content["global"]["editorName"], "VocaloidTTS")
        self.assertEqual(len(content["tracks"]), 1)

    def test_timeline(self) -> None:
        content = self._model()["content"]
        timeline = content["timeline"]
        self.assertEqual(timeline["tempos"], [{"pos": 0, "value": 120.0}])
        self.assertEqual(timeline["timeSignatures"],
                         [{"index": 0, "numerator": 4, "denominator": 4}])
        self.assertEqual(timeline["labels"], [])

    def test_clip_and_notes(self) -> None:
        content = self._model()["content"]
        track = content["tracks"][0]
        self.assertEqual(track["control"]["solo"], False)
        clip = track["clips"][0]
        self.assertEqual(clip["type"], "singing")
        self.assertEqual(clip["time"]["pos"], 0)
        self.assertEqual(clip["time"]["length"], 0)
        self.assertEqual(clip["time"]["clipStart"], 0)
        self.assertIsNone(clip["sources"])
        song = compose("你好世界", VoiceOptions(seed=42))
        self.assertEqual(len(clip["notes"]), len(song.notes))
        first = clip["notes"][0]
        self.assertEqual(first["pos"], song.notes[0].start)
        self.assertEqual(first["length"], song.notes[0].dur)
        self.assertEqual(first["keyNum"], song.notes[0].midi)
        self.assertEqual(first["lyric"], "你")

    def test_every_required_field_is_present(self) -> None:
        """模型是 extra=forbid + strict，缺字段在编辑器里就是打不开。"""
        clip = self._model()["content"]["tracks"][0]["clips"][0]
        note = clip["notes"][0]
        expected = {"pos", "length", "keyNum", "centShift", "language", "lyric",
                    "pronunciation", "phonemes", "vibrato", "workspace"}
        self.assertEqual(set(note), expected)
        self.assertEqual(set(note["vibrato"]),
                         {"start", "end", "amp", "freq", "phase", "offset", "points"})
        self.assertEqual(set(note["vibrato"]["points"]), {"amp", "freq"})

    def test_shared_zstd_helper(self) -> None:
        """.acep 和 .dspx 共用同一个帧写入器，钉住它的分块行为。"""
        frame = zstd_store(b"x" * (ZSTD_BLOCK_MAX * 2 + 5))
        self.assertEqual(frame[:4], b"\x28\xb5\x2f\xfd")
        self.assertEqual(frame[4], 0xA0)

    def test_empty_song_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            dspx.write_dspx(compose("", VoiceOptions(seed=1)), "x.dspx")

    def test_registry(self) -> None:
        self.assertEqual(formats()["dspx"].extension, ".dspx")


if __name__ == "__main__":
    unittest.main()
