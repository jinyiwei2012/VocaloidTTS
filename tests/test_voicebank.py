"""Voicebank discovery: V3 / V4 / V5 component layouts and naming."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vocaloidtts.voicebank import _match_known, scan_voicebank_folder


class VoicebankComponentTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _component(self, root: Path, comp_id: str, files: list[str],
                   eula: list[str] | None = None) -> Path:
        comp = root / comp_id
        comp.mkdir(parents=True)
        for name in files:
            (comp / name).write_bytes(b"")
        if eula:
            eula_dir = comp / "EULA"
            eula_dir.mkdir()
            for name in eula:
                (eula_dir / name).write_text("", encoding="utf-8")
        return comp

    def test_v3_component_uses_real_vvd_name(self) -> None:
        lib = self.root / "v3声库"
        lib.mkdir()
        self._component(lib, "BETDB8W6KWZPYEB9",
                        ["Tianyi_CHN.ddb", "Tianyi_CHN.ddi", "Tianyi_CHN.vvd"])
        banks = scan_voicebank_folder(lib)
        self.assertEqual(len(banks), 1)
        bank = banks[0]
        self.assertEqual(bank.id, "BETDB8W6KWZPYEB9")
        self.assertEqual(bank.name, "Tianyi_CHN")
        self.assertEqual(bank.version, "V3")
        self.assertNotIn("_v4compatible", bank.display)

    def test_v4_component_keeps_real_name_and_version(self) -> None:
        lib = self.root / "MikuV4C"
        lib.mkdir()
        self._component(lib, "BNGE7CP7EMTRSNC3",
                        ["MIKU_V4_Chinese.ddb", "MIKU_V4_Chinese.ddi",
                         "MIKU_V4_Chinese.vvd"])
        banks = scan_voicebank_folder(lib)
        self.assertEqual(len(banks), 1)
        bank = banks[0]
        self.assertEqual(bank.name, "MIKU_V4_Chinese")
        self.assertEqual(bank.version, "V4")
        self.assertEqual((bank.bs, bank.pc), (4, 0))
        self.assertIn("V4", bank.display)

    def test_v5_component_uses_ddi_name_and_eula_version(self) -> None:
        lib = self.root / "语调专用"
        lib.mkdir()
        self._component(
            lib, "BD79E492NWWK3DDF",
            ["Luo_Tianyi_Ning.ddb", "Luo_Tianyi_Ning.ddi", "_v4compatible.vvd"],
            eula=["LICENSES_V5_SHANGHAI HENIAN Luo Tianyi_CHS.txt"])
        banks = scan_voicebank_folder(lib)
        self.assertEqual(len(banks), 1)
        bank = banks[0]
        self.assertEqual(bank.id, "BD79E492NWWK3DDF")
        self.assertEqual(bank.name, "Luo_Tianyi_Ning")
        self.assertEqual(bank.version, "V5")
        self.assertEqual((bank.bs, bank.pc), (4, 0))
        self.assertNotEqual(bank.display, "_v4compatible")
        self.assertIn("V5", bank.display)

    def test_v5_without_eula_is_still_not_named_v4compatible(self) -> None:
        lib = self.root / "lib"
        lib.mkdir()
        self._component(lib, "BE9C82Y5FDYNTEDD",
                        ["Moqingxian.ddb", "Moqingxian.ddi", "_v4compatible.vvd"])
        banks = scan_voicebank_folder(lib)
        self.assertEqual(len(banks), 1)
        bank = banks[0]
        self.assertEqual(bank.name, "Moqingxian")
        self.assertEqual(bank.version, "V5")
        self.assertEqual((bank.bs, bank.pc), (4, 0))

    def test_multiple_versions_are_distinguishable(self) -> None:
        v3_lib = self.root / "v3声库" / "绫"
        v5_lib = self.root / "语调专用" / "绫"
        v3_lib.mkdir(parents=True)
        v5_lib.mkdir(parents=True)
        self._component(v3_lib, "BE8A88G3FWXLTEBD",
                        ["YuezhenglingV3.ddb", "YuezhenglingV3.ddi",
                         "YuezhenglingV3.vvd"])
        self._component(
            v5_lib, "BMBNDB8EM5222MK3",
            ["Yuezheng_Ling_You.ddb", "Yuezheng_Ling_You.ddi",
             "_v4compatible.vvd"],
            eula=["LICENSES_V5_SHANGHAI HENIAN Yuezheng Ling_CHS.txt"])
        banks = scan_voicebank_folder(self.root)
        self.assertEqual(len(banks), 2)
        by_id = {b.id: b for b in banks}
        self.assertEqual(by_id["BE8A88G3FWXLTEBD"].version, "V3")
        self.assertEqual(by_id["BMBNDB8EM5222MK3"].version, "V5")
        labels = {b.display for b in banks}
        self.assertEqual(len(labels), 2)


class MatchKnownTests(unittest.TestCase):
    def test_chinese_miku_is_not_treated_as_japanese(self) -> None:
        matched = _match_known("MIKU_V4_Chinese", r"C:\vc\MikuV4C")
        self.assertIsNotNone(matched)
        self.assertEqual(matched[0], 4)

    def test_spaced_yane_and_moqingxian_are_chinese(self) -> None:
        for name in ("Yan_He_Mu", "Moqingxian"):
            matched = _match_known(name, r"C:\vc\lib")
            self.assertIsNotNone(matched, name)
            self.assertEqual(matched[0], 4, name)

    def test_japanese_banks_stay_japanese(self) -> None:
        for name in ("kaito", "miku", "luka"):
            matched = _match_known(name, r"C:\vc\jp")
            self.assertIsNotNone(matched, name)
            self.assertEqual(matched[0], 1, name)


if __name__ == "__main__":
    unittest.main()
