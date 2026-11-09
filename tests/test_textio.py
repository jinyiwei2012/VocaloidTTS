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


class BomOrderTests(unittest.TestCase):
    def test_utf32_le_with_bom_is_not_read_as_utf16(self) -> None:
        # FF FE 00 00 同时以 FF FE 开头，先判 UTF-16 会得到「NUL + 字符」
        sample = "UTF-32 小端"
        raw = b"\xff\xfe\x00\x00" + sample.encode("utf-32-le")
        text, encoding = decode_text(raw)
        self.assertEqual(text, sample)
        self.assertEqual(encoding, "utf-32-le")

    def test_utf32_be_with_bom(self) -> None:
        sample = "UTF-32 大端"
        raw = b"\x00\x00\xfe\xff" + sample.encode("utf-32-be")
        text, encoding = decode_text(raw)
        self.assertEqual(text, sample)
        self.assertEqual(encoding, "utf-32-be")

    def test_declared_encoding_that_fails_stays_with_that_encoding(self) -> None:
        # UTF-8 BOM 后面跟非法字节，曾整份掉进 utf-16 分支读成韩文
        raw = b"\xef\xbb\xbf" + b"\xff\xfe\xfd"
        text, encoding = decode_text(raw)
        self.assertTrue(encoding.startswith("utf-8-sig"))
        self.assertFalse(any("\uac00" <= ch <= "\ud7af" for ch in text))


class NoBomUtf16Tests(unittest.TestCase):
    def test_ascii_utf16_be_without_bom(self) -> None:
        text, encoding = decode_text("hello world".encode("utf-16-be"))
        self.assertEqual(text, "hello world")
        self.assertEqual(encoding, "utf-16-be")

    def test_ascii_utf16_le_without_bom(self) -> None:
        text, encoding = decode_text("hello world".encode("utf-16-le"))
        self.assertEqual(text, "hello world")
        self.assertEqual(encoding, "utf-16-le")

    def test_pure_chinese_utf16_without_bom_never_yields_control_chars(self) -> None:
        # 没有 NUL 分布可依据，不猜端序；但至少要挡住控制字符
        for encoding in ("utf-16-be", "utf-16-le"):
            with self.subTest(encoding=encoding):
                text, _ = decode_text("你好世界".encode(encoding))
                self.assertFalse(
                    any(ord(ch) < 0x20 and ch not in "\t\n\r" for ch in text))


if __name__ == "__main__":
    unittest.main()
