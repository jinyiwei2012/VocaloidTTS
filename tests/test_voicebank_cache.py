"""detect_voicebanks caches results and invalidates them when roots change."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vocaloidtts.voicebank import (_cache_signature, add_voicebank_root,
                                   detect_voicebanks)


class CacheTests(unittest.TestCase):
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

    def test_second_call_uses_cache(self) -> None:
        with patch("vocaloidtts.voicebank._scan_registry",
                   return_value=[]) as registry, \
                patch("vocaloidtts.voicebank._scan_filesystem", return_value=[]):
            detect_voicebanks()
            detect_voicebanks()
        self.assertEqual(registry.call_count, 1)

    def test_force_refresh_bypasses_cache(self) -> None:
        with patch("vocaloidtts.voicebank._scan_registry",
                   return_value=[]) as registry, \
                patch("vocaloidtts.voicebank._scan_filesystem", return_value=[]):
            detect_voicebanks()
            detect_voicebanks(use_cache=False)
        self.assertEqual(registry.call_count, 2)

    def test_root_change_invalidates_cache(self) -> None:
        comp = self.lib / "BD79E492NWWK3DDF"
        comp.mkdir()
        (comp / "Luo_Tianyi_Ning.ddi").write_bytes(b"")
        (comp / "_v4compatible.vvd").write_bytes(b"")
        add_voicebank_root(self.lib)
        with patch("vocaloidtts.voicebank._scan_registry",
                   return_value=[]) as registry, \
                patch("vocaloidtts.voicebank._scan_filesystem", return_value=[]):
            detect_voicebanks()
            (self.lib / "newdir").mkdir()
            detect_voicebanks()
        self.assertEqual(registry.call_count, 2)

    def test_signature_tracks_nested_component_entries(self) -> None:
        """往已存在的组件目录里塞新声库，签名必须变。"""
        nested = self.lib / "comp" / "inner"
        nested.mkdir(parents=True)
        cfg = {"roots": [{"path": str(self.lib)}], "scan": {"max_depth": 8}}
        before = _cache_signature(cfg)
        (nested / "new.vvd").write_bytes(b"\0" * 16)
        self.assertNotEqual(_cache_signature(cfg), before)

    def test_nested_component_change_invalidates_cache(self) -> None:
        comp = self.lib / "BD79E492NWWK3DDF"
        comp.mkdir()
        (comp / "Luo_Tianyi_Ning.ddi").write_bytes(b"")
        add_voicebank_root(self.lib)
        with patch("vocaloidtts.voicebank._scan_registry",
                   return_value=[]) as registry, \
                patch("vocaloidtts.voicebank._scan_filesystem", return_value=[]):
            detect_voicebanks()
            (comp / "_v4compatible.vvd").write_bytes(b"")
            detect_voicebanks()
        self.assertEqual(registry.call_count, 2)

    def test_signature_tracks_auto_discovered_roots(self) -> None:
        """注册表 / 默认 VoiceDB 不在配置里，换了内容也要让缓存失效。"""
        auto = Path(self._tmp.name) / "VoiceDB"
        auto.mkdir()
        cfg = {"roots": [], "scan": {"max_depth": 8}}
        with patch("vocaloidtts.voicebank._voice_db_roots",
                   return_value=[auto]):
            before = _cache_signature(cfg)
            (auto / "newbank").mkdir()
            self.assertNotEqual(_cache_signature(cfg), before)


if __name__ == "__main__":
    unittest.main()
