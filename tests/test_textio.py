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

    def test_utf8_korean_is_not_mistaken_for_garbage(self) -> None:
        # 韩文音节曾被当成「坏码位」整批否决，导致合法 UTF-8 韩文掉进
        # gb18030 变成乱码；带不带空格还会给出不同结果。
        for source in ("안녕하세요세", "안녕 하세요 세"):
            with self.subTest(source=source):
                text, encoding = decode_text(source.encode("utf-8"))
                self.assertEqual(text, source)
                self.assertIn("utf-8", encoding)

    def test_gbk_file_is_not_decoded_as_hangul(self) -> None:
        # 反过来也要成立：中文 GBK 文件不能被 utf-16 抢先解成 Hangul
        text, encoding = decode_text("你好世界今天天气不错".encode("gb18030"))
        self.assertEqual(text, "你好世界今天天气不错")
        self.assertEqual(encoding, "gb18030")


if __name__ == "__main__":
    unittest.main()
