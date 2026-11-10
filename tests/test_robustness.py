"""畸形输入的回归网。

这个应用的用户会往输入框里粘任何东西：五千位的数字、从别处下载的项目文件、
二进制文件改名成 .txt。这里把那些会让流程抛异常的输入固定下来，避免以后
改动把它们放回去。
"""
from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from vocaloidtts.edits import CharEdit, EditSet
from vocaloidtts.jobfile import write_job
from vocaloidtts.pinyin import normalize_text, text_to_syllables
from vocaloidtts.project import Project, load_project
from vocaloidtts.prosody import VoiceOptions, compose
from vocaloidtts.textio import decode_text


class ExtremeTextTests(unittest.TestCase):
    def test_very_long_digit_run_is_read_digit_by_digit(self) -> None:
        # Python 3.11+ 的 int() 只收 4300 位；5000 位曾让 normalize_text 直接抛
        digits = "9" * 5000
        spoken = normalize_text(digits)
        self.assertEqual(len(spoken), 5000)
        self.assertTrue(all(ch in "零一二三四五六七八九" for ch in spoken))

    def test_very_long_percentage_does_not_raise(self) -> None:
        spoken = normalize_text("9" * 5000 + "%")
        self.assertTrue(spoken.startswith("百分之"))

    def test_normal_percentage_still_reads_as_a_number(self) -> None:
        self.assertEqual(normalize_text("1000000%"), "百分之一百万")
        self.assertEqual(normalize_text("12.5%"), "百分之十二点五")

    def test_odd_unicode_does_not_break_parsing(self) -> None:
        for text in ("你\x00好", "你\x01\x02好", "你😀好", "\ud800",
                     "你好\u202e世界", "\u2066你好\u2069", "e\u0301" * 50):
            with self.subTest(text=repr(text)[:40]):
                self.assertIsInstance(normalize_text(text), str)
                self.assertIsInstance(text_to_syllables(text), list)

    def test_punctuation_only_and_empty_input(self) -> None:
        for text in ("", "，，，。。。", "   \n\t  ", "." * 200):
            with self.subTest(text=repr(text)[:20]):
                self.assertEqual(text_to_syllables(text), [])


class ExtremeProjectTests(unittest.TestCase):
    def _write(self, directory: str, name: str, body: str) -> Path:
        path = Path(directory) / name
        path.write_text(body, encoding="utf-8")
        return path

    def test_deeply_nested_json_becomes_a_clear_error(self) -> None:
        # 两万层嵌套会让 json.loads 抛 RecursionError；它不是 ValueError，
        # 不接住就会绕过界面的错误提示
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, "deep.json", "[" * 20000 + "]" * 20000)
            with self.assertRaises(ValueError) as caught:
                load_project(path)
            self.assertIn("嵌套太深", str(caught.exception))

    def test_non_object_json_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for name, body in (("empty", ""), ("null", "null"), ("list", "[]"),
                               ("number", "42"), ("string", '"hi"')):
                with self.subTest(body=body):
                    path = self._write(directory, f"{name}.json", body)
                    with self.assertRaises(ValueError):
                        load_project(path)

    def test_infinite_and_nan_options_fall_back_to_defaults(self) -> None:
        raw = {
            "app": "VocaloidTTS",
            "bpm": float("inf"),
            "numerator": float("nan"),
            "options": {"rate": float("inf"), "energy": float("nan")},
        }
        project = Project.from_dict(raw)
        self.assertTrue(math.isfinite(project.bpm))
        self.assertEqual(project.numerator, 4)
        self.assertTrue(math.isfinite(project.options.rate))
        self.assertTrue(math.isfinite(project.options.energy))

    def test_absurd_edit_values_are_clamped(self) -> None:
        edit = CharEdit.from_dict({
            "char": "你", "stress": 1e308, "dur_scale": -5,
            "pause_ms": 10**18,
        })
        self.assertEqual(edit.stress, 1.0)
        self.assertEqual(edit.dur_scale, 0.5)
        self.assertEqual(edit.pause_ms, 4000)

    def test_non_finite_edit_values_are_dropped(self) -> None:
        edit = CharEdit.from_dict({
            "char": "你", "stress": float("inf"), "dur_scale": float("nan"),
            "pause_ms": float("-inf"),
        })
        self.assertIsNone(edit.stress)
        self.assertIsNone(edit.dur_scale)
        self.assertIsNone(edit.pause_ms)

    def test_settings_schema_non_finite_falls_back_to_one(self) -> None:
        # {"schema": 1e999} 是合法 JSON，解析成 inf；int(inf) 抛 OverflowError，
        # 而它发生在 _apply_settings 的最前面，兜不住窗口就起不来。
        from vocaloidtts.app import schema_version
        self.assertEqual(schema_version(json.loads('{"schema": 1e999}')), 1)
        self.assertEqual(schema_version({"schema": float("inf")}), 1)
        self.assertEqual(schema_version({"schema": float("nan")}), 1)
        self.assertEqual(schema_version({"schema": "abc"}), 1)
        self.assertEqual(schema_version({"schema": None}), 1)
        self.assertEqual(schema_version({}), 1)
        self.assertEqual(schema_version(None), 1)
        self.assertEqual(schema_version({"schema": 10}), 10)
        self.assertEqual(schema_version({"schema": "7"}), 7)
        self.assertEqual(schema_version({"schema": 2.9}), 2)

    def test_huge_edit_offsets_do_not_crash(self) -> None:
        edits = EditSet.from_dict({
            "snapshot": "你好",
            "chars": {"999999999999": {"char": "你", "tone": 3}},
        })
        song = compose("你好", edits=edits)
        self.assertEqual(len(song.notes), 2)


class ExtremeExportTests(unittest.TestCase):
    def test_job_title_cannot_inject_extra_rows(self) -> None:
        song = compose("你好", VoiceOptions(seed=1))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "job.txt"
            write_job(song, path,
                      title="标题\nNOTE\t0\t1\t60\t100\t50\t啊\ta")
            lines = path.read_text(encoding="utf-8").splitlines()
        titles = [line for line in lines if line.startswith("TITLE")]
        self.assertEqual(len(titles), 1)
        self.assertNotIn("\n", titles[0])

    def test_extreme_song_parameters_still_export(self) -> None:
        from vocaloidtts.vsqx import write_vsqx
        from vocaloidtts.voicebank import Voicebank

        bank = Voicebank("BTESTBANK0000001", "Test", "测试", bs=4, pc=0,
                         source="test")
        with tempfile.TemporaryDirectory() as directory:
            for name, kwargs in (
                ("bpm_inf", {"bpm": float("inf")}),
                ("bpm_nan", {"bpm": float("nan")}),
                ("bpm_zero", {"bpm": 0}),
                ("num_huge", {"numerator": 10**9}),
                ("den_zero", {"denominator": 0}),
            ):
                with self.subTest(case=name):
                    song = compose("你好世界", VoiceOptions(seed=1), **kwargs)
                    out = Path(directory) / f"{name}.vsqx"
                    write_vsqx(song, str(out), bank)
                    self.assertGreater(out.stat().st_size, 0)


class ExtremeDecodeTests(unittest.TestCase):
    def test_bom_only_files_do_not_raise(self) -> None:
        for raw in (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff",
                    b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff"):
            with self.subTest(raw=raw):
                text, encoding = decode_text(raw)
                self.assertIsInstance(text, str)
                self.assertIsInstance(encoding, str)

    def test_binary_garbage_is_decoded_to_something(self) -> None:
        text, _ = decode_text(bytes(range(256)) * 8)
        self.assertIsInstance(text, str)


if __name__ == "__main__":
    unittest.main()
