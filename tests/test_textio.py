"""Decoding of imported text files: BOM first, then Chinese-friendly fallbacks."""
from __future__ import annotations

import unittest

from vocaloidtts.textio import decode_text


class DecodeTextTests(unittest.TestCase):
    def test_gbk_file_keeps_chinese(self) -> None:
        sample = "你好世界，今天天气真好。"
        text, encoding = decode_text(sample.encode("gb18030"))
        self.assertEqual(text, sample)
        self.assertEqual(encoding, "gb18030")

    def test_plain_utf8(self) -> None:
        sample = "今天天气不错，我们用AI读一段文字。"
        text, encoding = decode_text(sample.encode("utf-8"))
        self.assertEqual(text, sample)
        self.assertEqual(encoding, "utf-8-sig")

    def test_utf8_with_bom(self) -> None:
        sample = "带 BOM 的文本"
        text, encoding = decode_text(sample.encode("utf-8-sig"))
        self.assertEqual(text, sample)
        self.assertEqual(encoding, "utf-8-sig")

    def test_utf16_le_with_bom(self) -> None:
        sample = "UTF-16 小端"
        raw = b"\xff\xfe" + sample.encode("utf-16-le")
        text, encoding = decode_text(raw)
        self.assertEqual(text, sample)
        self.assertEqual(encoding, "utf-16-le")

    def test_utf16_be_with_bom(self) -> None:
        sample = "UTF-16 大端"
        raw = b"\xfe\xff" + sample.encode("utf-16-be")
        text, encoding = decode_text(raw)
        self.assertEqual(text, sample)
        self.assertEqual(encoding, "utf-16-be")

    def test_empty_file(self) -> None:
        self.assertEqual(decode_text(b"")[0], "")

    def test_binary_garbage_does_not_raise(self) -> None:
        text, encoding = decode_text(bytes(range(256)) * 4)
        self.assertIsInstance(text, str)
        self.assertIsInstance(encoding, str)


if __name__ == "__main__":
    unittest.main()
