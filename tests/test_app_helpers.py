"""Pure helpers in the Tk front-end are testable without opening a window."""
from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

from vocaloidtts.app import (DUR_CHOICES, PAUSE_CHOICES, STRESS_CHOICES,
                             VocaloidTTSApp, choice_label, choice_value,
                             note_name, parse_bpm, parse_meter)
from vocaloidtts.voicebank import Voicebank


class ChoiceHelperTests(unittest.TestCase):
    def test_every_choice_round_trips(self) -> None:
        for choices in (STRESS_CHOICES, DUR_CHOICES, PAUSE_CHOICES):
            for label, value in choices:
                with self.subTest(label=label):
                    self.assertEqual(choice_value(choices, label), value)
                    self.assertEqual(choice_label(choices, value), label)

    def test_unknown_value_falls_back_to_auto(self) -> None:
        self.assertEqual(choice_label(STRESS_CHOICES, 0.123), "自动")
        self.assertIsNone(choice_value(STRESS_CHOICES, "不存在的选项"))

    def test_auto_label_maps_to_none(self) -> None:
        for choices in (STRESS_CHOICES, DUR_CHOICES, PAUSE_CHOICES):
            self.assertIsNone(choice_value(choices, "自动"))
            self.assertEqual(choice_label(choices, None), "自动")


class AppHelperTests(unittest.TestCase):
    def test_note_name_uses_vocaloid_octaves(self) -> None:
        self.assertEqual(note_name(60), "C3")
        self.assertEqual(note_name(67), "G3")

    def test_fmt_num_trims_integral_floats(self) -> None:
        self.assertEqual(VocaloidTTSApp._fmt_num(120.0), "120")
        self.assertEqual(VocaloidTTSApp._fmt_num(90.5), "90.5")

    def test_bank_badge_recognises_known_banks(self) -> None:
        bank = Voicebank("X", "LuoTianyi", "洛天依", 4, 0)
        self.assertIn("LUO", VocaloidTTSApp._bank_badge_text(bank))


class ParseInputTests(unittest.TestCase):
    def test_bad_bpm_falls_back_to_120(self) -> None:
        for raw in ("", "abc", "   "):
            with self.subTest(raw=raw):
                self.assertEqual(parse_bpm(raw), 120.0)

    def test_bpm_is_clamped(self) -> None:
        self.assertEqual(parse_bpm("0"), 40.0)
        self.assertEqual(parse_bpm("999"), 240.0)
        self.assertEqual(parse_bpm(" 90 "), 90.0)
        self.assertEqual(parse_bpm("90.5"), 90.5)

    def test_meter_repairs_out_of_range_values(self) -> None:
        self.assertEqual(parse_meter("4", "4"), (4, 4))
        self.assertEqual(parse_meter("x", "4"), (4, 4))
        self.assertEqual(parse_meter("0", "3"), (1, 4))
        self.assertEqual(parse_meter("20", "4"), (16, 4))
        self.assertEqual(parse_meter("3", "8"), (3, 8))


class ExcepthookTests(unittest.TestCase):
    class _FakeApp:
        def __init__(self) -> None:
            self.lines: list[str] = []

        def _append_log_file(self, line: str) -> None:
            self.lines.append(line)

    def test_the_same_error_is_logged_every_time_but_pops_once(self) -> None:
        from vocaloidtts import app as appmod

        fake = self._FakeApp()
        original = sys.excepthook
        self.addCleanup(setattr, sys, "excepthook", original)
        with patch.object(appmod, "messagebox") as box:
            appmod._install_excepthooks(fake)
            hook = sys.excepthook
            try:
                raise ValueError("boom")
            except ValueError:
                info = sys.exc_info()
            for _ in range(3):
                hook(*info)
            self.assertEqual(box.showerror.call_count, 1)
        # 日志每条都写，方便事后查；弹窗只弹一次，避免 after 回调每帧刷屏
        self.assertEqual(len(fake.lines), 3)
        self.assertIn("boom", fake.lines[0])


if __name__ == "__main__":
    unittest.main()
