"""Voicebank root configuration: JSON persistence, overrides, import/export."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vocaloidtts.voicebank import (
    VoicebankRoot,
    add_voicebank_root,
    detect_voicebanks,
    export_voicebank_roots,
    get_voicebank_roots,
    import_voicebank_roots,
    remove_voicebank_root,
)


class RootConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.appdata = base / "appdata"
        self.appdata.mkdir()
        self.lib = base / "lib"
        self.lib.mkdir()
        patcher = patch("vocaloidtts.voicebank.appdata_dir",
                        return_value=self.appdata)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _component(self, comp_id: str, files: list[str]) -> Path:
        comp = self.lib / comp_id
        comp.mkdir(parents=True)
        for name in files:
            (comp / name).write_bytes(b"")
        return comp

    def test_add_and_list_roots(self) -> None:
        add_voicebank_root(self.lib)
        roots = get_voicebank_roots()
        self.assertEqual([r.path for r in roots], [str(self.lib.resolve())])

    def test_duplicate_add_is_ignored(self) -> None:
        add_voicebank_root(self.lib)
        add_voicebank_root(self.lib)
        self.assertEqual(len(get_voicebank_roots()), 1)

    def test_override_is_applied_during_scan(self) -> None:
        self._component("BD79E492NWWK3DDF",
                        ["Luo_Tianyi_Ning.ddb", "Luo_Tianyi_Ning.ddi",
                         "_v4compatible.vvd"])
        add_voicebank_root(self.lib, bs=4, pc=0, display="洛天依 · V5")
        with patch("vocaloidtts.voicebank._scan_registry", return_value=[]), \
                patch("vocaloidtts.voicebank._scan_filesystem", return_value=[]):
            banks = detect_voicebanks()
        mine = [b for b in banks if b.id == "BD79E492NWWK3DDF"]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0].display, "洛天依 · V5")
        self.assertEqual((mine[0].bs, mine[0].pc), (4, 0))

    def test_export_import_round_trip(self) -> None:
        add_voicebank_root(self.lib, bs=4, pc=1, display="自定义")
        out = Path(self._tmp.name) / "roots.json"
        export_voicebank_roots(out)
        remove_voicebank_root(self.lib)
        self.assertEqual(get_voicebank_roots(), [])
        import_voicebank_roots(out)
        roots = get_voicebank_roots()
        self.assertEqual(len(roots), 1)
        self.assertEqual((roots[0].bs, roots[0].pc), (4, 1))
        self.assertEqual(roots[0].display, "自定义")

    def test_legacy_txt_is_read_and_migrated(self) -> None:
        (self.appdata / "voicebank_roots.txt").write_text(
            f"{self.lib}\n", encoding="utf-8")
        roots = get_voicebank_roots()
        self.assertEqual([r.path for r in roots], [str(self.lib)])
        add_voicebank_root(self.lib)
        self.assertTrue((self.appdata / "voicebank_roots.json").is_file())

    def test_disabled_root_is_skipped(self) -> None:
        self._component("BETDB8W6KWZPYEB9",
                        ["Tianyi_CHN.ddb", "Tianyi_CHN.ddi", "Tianyi_CHN.vvd"])
        root = add_voicebank_root(self.lib)
        root.enabled = False
        roots = [VoicebankRoot.from_dict(root.as_dict())]
        self.assertFalse(roots[0].enabled)
        with patch("vocaloidtts.voicebank._scan_registry", return_value=[]), \
                patch("vocaloidtts.voicebank._scan_filesystem", return_value=[]), \
                patch("vocaloidtts.voicebank.get_voicebank_roots", return_value=roots):
            self.assertEqual(detect_voicebanks(), [])


class SortModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.appdata = base / "appdata"
        self.appdata.mkdir()
        self.lib = base / "lib"
        self.lib.mkdir()
        patcher = patch("vocaloidtts.voicebank.appdata_dir",
                        return_value=self.appdata)
        patcher.start()
        self.addCleanup(patcher.stop)
        for comp_id, name in (("ZETA0000000000001", "Zeta"),
                              ("ALPHA0000000000001", "Alpha")):
            comp = self.lib / comp_id
            comp.mkdir()
            (comp / f"{name}.ddi").write_bytes(b"")
            (comp / "_v4compatible.vvd").write_bytes(b"")

    def test_sort_mode_name_orders_by_display(self) -> None:
        from vocaloidtts.voicebank import VoicebankRoot, _collect_voicebanks
        root = VoicebankRoot(str(self.lib))
        with patch("vocaloidtts.voicebank._scan_registry", return_value=[]), \
                patch("vocaloidtts.voicebank._scan_filesystem", return_value=[]), \
                patch("vocaloidtts.voicebank.get_voicebank_roots",
                      return_value=[root]):
            found = _collect_voicebanks({"scan": {"sort": "name"}, "roots": []})
        names = [bank.display.split(" · ")[0] for bank in found]
        self.assertEqual(names, ["Alpha", "Zeta"])


if __name__ == "__main__":
    unittest.main()
