"""Pure helpers in the Tk front-end are testable without opening a window."""
from __future__ import annotations

import unittest

from vocaloidtts.app import VocaloidTTSApp, note_name
from vocaloidtts.voicebank import Voicebank


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
