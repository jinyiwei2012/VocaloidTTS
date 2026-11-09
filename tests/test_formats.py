"""注册表层面的不变量：每个格式的元数据都得齐全。

「生成」菜单和保存对话框都只读 ``FORMATS``，元数据缺一项，用户就会在
点下菜单的那一刻撞上异常，而不是在加格式的时候。这些断言把错误提前。
"""
from __future__ import annotations

import unittest

from vocaloidtts.formats import Format, formats


class FormatRegistryTests(unittest.TestCase):
    def test_every_format_has_complete_metadata(self) -> None:
        for key, meta in formats().items():
            with self.subTest(format=key):
                self.assertIsInstance(meta, Format)
                self.assertEqual(meta.key, key)
                self.assertTrue(meta.label, key)
                self.assertTrue(meta.short, key)
                self.assertTrue(meta.extension.startswith("."), key)
                self.assertTrue(meta.prefix, key)
                self.assertTrue(callable(meta.writer), key)
                # filedialog 的 filetypes 只收两元组
                self.assertEqual(len(meta.filetype), 2, key)
                self.assertTrue(meta.filetype[0], key)
                self.assertTrue(meta.filetype[1].startswith("*."), key)

    def test_extensions_are_unique(self) -> None:
        extensions = [meta.extension for meta in formats().values()]
        self.assertEqual(len(extensions), len(set(extensions)))

    def test_vsqx_is_the_only_format_that_needs_a_voicebank(self) -> None:
        needs = {key for key, meta in formats().items() if meta.needs_voicebank}
        self.assertEqual(needs, {"vsqx"})

    def test_missing_voicebank_is_reported_before_writing(self) -> None:
        meta = formats()["vsqx"]
        with self.assertRaises(ValueError):
            meta.write(None, "x.vsqx")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
