"""Regression coverage for text readings, order and phrase boundaries."""
import unittest

from vocaloidtts.pinyin import normalize_text, num_to_chinese, text_to_syllables


class NumberReadingTests(unittest.TestCase):
    def test_percentages_keep_prefix_before_number(self):
        for source, expected in (
            ("50%", "百分之五十"),
            ("12.5%", "百分之十二点五"),
            ("0%", "百分之零"),
            ("0.05%", "百分之零点零五"),
            ("增长５０％。", "增长百分之五十。"),
            ("50%和12.5%", "百分之五十和百分之十二点五"),
            ("1000000%", "百分之一百万"),
        ):
            with self.subTest(source=source):
                self.assertEqual(normalize_text(source), expected)

    def test_grouped_numbers_insert_zeros_without_dropping_one(self):
        for number, expected in (
            (0, "零"),
            (10, "十"),
            (19, "十九"),
            (101, "一百零一"),
            (1010, "一千零一十"),
            (10000, "一万"),
            (10001, "一万零一"),
            (10010, "一万零一十"),
            (10019, "一万零一十九"),
            (10100, "一万零一百"),
            (11000, "一万一千"),
            (100000, "十万"),
            (100001, "十万零一"),
            (100000000, "一亿"),
            (100000001, "一亿零一"),
            (100010000, "一亿零一万"),
            (100010010, "一亿零一万零一十"),
            (110001001, "一亿一千万一千零一"),
            (-10010, "负一万零一十"),
        ):
            with self.subTest(number=number):
                self.assertEqual(num_to_chinese(number), expected)
        self.assertEqual(normalize_text("10001和10010"), "一万零一和一万零一十")

    def test_years_phone_numbers_and_decimal_digits_keep_their_readings(self):
        for source, expected in (
            ("1999年和2026年", "一九九九年和二零二六年"),
            ("2026个", "二千零二十六个"),
            ("13800138000", "一三八零零一三八零零零"),
            ("01234567890", "零一二三四五六七八九零"),
            ("3.1415", "三点一四一五"),
            ("10001.05", "一万零一点零五"),
            ("1000000000000.5", "一零零零零零零零零零零零零点五"),
        ):
            with self.subTest(source=source):
                self.assertEqual(normalize_text(source), expected)


class TextSyllableTests(unittest.TestCase):
    def test_mixed_text_stays_in_source_order_and_one_phrase(self):
        for source in ("请用AI读", "AI请读", "请读AI"):
            with self.subTest(source=source):
                syllables = text_to_syllables(source)
                self.assertEqual("".join(s.text for s in syllables), source)
                self.assertEqual({s.phrase for s in syllables}, {0})
                self.assertTrue(all(s.pause_after_ms == 0 for s in syllables))
                self.assertEqual([s.index for s in syllables], list(range(len(syllables))))
                self.assertEqual([s.final for s in syllables], [False] * (len(syllables) - 1) + [True])

    def test_letters_keep_all_name_syllables_and_punctuation(self):
        syllables = text_to_syllables("请读Fw。")
        self.assertEqual([s.pinyin for s in syllables], ["qing", "du", "ai", "fu", "da", "bu", "liu"])
        self.assertEqual([s.text for s in syllables], ["请", "读", "F", "F", "w", "w", "w"])
        self.assertTrue(all(s.phonemes for s in syllables))
        self.assertEqual([s.pause_after_ms for s in syllables], [0] * 6 + [420])
        self.assertEqual({s.phrase for s in syllables}, {0})
        # E is spelled yi, but is not the Chinese word 一 subject to sandhi.
        self.assertEqual([(s.pinyin, s.tone) for s in text_to_syllables("EF")],
                         [("yi", 1), ("ai", 1), ("fu", 1)])

    def test_chinese_sandhi_and_neutral_tones_survive_mixed_text(self):
        for source in ("你好，妈妈不对。", "你好AI妈妈不对。"):
            with self.subTest(source=source):
                syllables = text_to_syllables(source)
                chinese = [s for s in syllables if not s.text.isascii()]
                self.assertEqual([(s.pinyin, s.tone) for s in chinese],
                                 [("ni", 2), ("hao", 3), ("ma", 1), ("ma", 5), ("bu", 2), ("dui", 4)])
        mixed = text_to_syllables("你好AI妈妈不对。")
        self.assertEqual({s.phrase for s in mixed}, {0})
        self.assertEqual([s.pause_after_ms for s in mixed], [0] * 7 + [420])

    def test_context_readings_and_adverbial_neutral_tones_are_preserved(self):
        syllables = text_to_syllables("一个人慢慢地走。")
        self.assertEqual([(s.pinyin, s.tone) for s in syllables],
                         [("yi", 2), ("ge", 5), ("ren", 2), ("man", 4), ("man", 4), ("de", 5), ("zou", 3)])
        self.assertEqual([s.pinyin for s in text_to_syllables("了解目的")],
                         ["liao", "jie", "mu", "di"])

    def test_ascii_period_matches_chinese_period(self):
        self.assertEqual(text_to_syllables("你好.世界"), text_to_syllables("你好。世界"))
        syllables = text_to_syllables("你好.世界")
        self.assertEqual(syllables[1].pause_after_ms, 420)
        self.assertEqual([s.phrase for s in syllables], [0, 0, 1, 1])

    def test_decimals_are_not_sentence_breaks(self):
        self.assertEqual(normalize_text("3.14.值为12.5%。"), "三点一四。值为百分之十二点五。")
        syllables = text_to_syllables("值为12.5%。")
        self.assertEqual("".join(s.text for s in syllables), "值为百分之十二点五")
        self.assertEqual({s.phrase for s in syllables}, {0})
        self.assertEqual([s.pause_after_ms for s in syllables], [0] * (len(syllables) - 1) + [420])

    def test_empty_and_punctuation_only_input_has_no_syllables(self):
        for source in ("", " \t\n", "...，！？", "🙂"):
            with self.subTest(source=source):
                self.assertEqual(text_to_syllables(source), [])
        # Repeated marks add neither empty phrases nor duplicate syllables.
        syllables = text_to_syllables("..你好...世界。")
        self.assertEqual("".join(s.text for s in syllables), "你好世界")
        self.assertEqual([s.phrase for s in syllables], [0, 0, 1, 1])
        self.assertEqual([s.pause_after_ms for s in syllables], [0, 420, 0, 420])


if __name__ == "__main__":
    unittest.main()
