"""Pure helpers in the Tk front-end are testable without opening a window."""
from __future__ import annotations

import unittest

from vocaloidtts.app import (DUR_CHOICES, PAUSE_CHOICES, STRESS_CHOICES,
                             VocaloidTTSApp, choice_label, choice_value,
                             note_name)
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


if __name__ == "__main__":
    unittest.main()
