"""Regression coverage for text readings, order and phrase boundaries."""
import unittest

from vocaloidtts.edits import CharEdit
from vocaloidtts.pinyin import (normalize_text, num_to_chinese,
                                pinyin_text_to_syllables, text_to_syllables)
from vocaloidtts.progress import Cancelled, Reporter


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

    def test_long_numbers_with_units_read_as_numbers(self):
        self.assertEqual(normalize_text("10000000人"), "一千万人")
        self.assertIn("万", normalize_text("12345678元"))
        # an 11-digit number without a unit is still read digit by digit
        self.assertEqual(normalize_text("13800138000"),
                         "一三八零零一三八零零零")

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


class ParseProgressTests(unittest.TestCase):
    def test_progress_is_monotonic_and_reaches_one(self):
        seen = []
        reporter = Reporter(lambda stage, frac: seen.append((stage, frac)))
        text_to_syllables("你好世界，今天天气真好。" * 40, reporter=reporter)
        self.assertTrue(seen)
        self.assertEqual({stage for stage, _ in seen}, {"parse"})
        fractions = [frac for _, frac in seen]
        self.assertEqual(fractions, sorted(fractions))
        self.assertAlmostEqual(fractions[-1], 1.0)

    def test_cancel_stops_the_parser(self):
        with self.assertRaises(Cancelled):
            text_to_syllables("你好世界。",
                              reporter=Reporter(should_cancel=lambda: True))

    def test_pinyin_input_reports_progress(self):
        seen = []
        reporter = Reporter(lambda stage, frac: seen.append((stage, frac)))
        pinyin_text_to_syllables("ni3 hao3 shi4 jie4", reporter=reporter)
        self.assertTrue(seen)
        self.assertAlmostEqual(seen[-1][1], 1.0)

    def test_pinyin_input_honours_cancel(self):
        with self.assertRaises(Cancelled):
            pinyin_text_to_syllables(
                "ni3 hao3", reporter=Reporter(should_cancel=lambda: True))


class CharEditTests(unittest.TestCase):
    def test_edit_overrides_one_reading(self):
        plain = text_to_syllables("中国人")
        self.assertEqual([s.pinyin for s in plain], ["zhong", "guo", "ren"])
        edited = text_to_syllables(
            "中国人", edits={0: CharEdit(char="中", pinyin="chong", tone=2)})
        self.assertEqual(edited[0].pinyin, "chong")
        self.assertEqual(edited[0].tone, 2)
        # 相邻的字不受影响
        self.assertEqual([s.pinyin for s in edited[1:]], ["guo", "ren"])

    def test_same_char_twice_only_the_edited_one_changes(self):
        plain = text_to_syllables("你好你好")
        syls = text_to_syllables(
            "你好你好", edits={3: CharEdit(char="好", pinyin="hao", tone=4)})
        self.assertEqual(syls[3].tone, 4)
        # 前三个音节的读法保持自动结果，不受影响
        self.assertEqual([s.tone for s in syls[:3]],
                         [s.tone for s in plain[:3]])

    def test_char_guard_skips_a_drifted_offset(self):
        # 记的是「中」，但偏移 0 现在是「国」：宁可跳过也不错配
        syls = text_to_syllables(
            "国中国", edits={0: CharEdit(char="中", pinyin="zhong", tone=1)})
        self.assertEqual(syls[0].pinyin, "guo")
        self.assertEqual(syls[0].tone, 2)

    def test_invalid_pinyin_keeps_the_reading_but_applies_the_tone(self):
        syls = text_to_syllables(
            "中国人", edits={0: CharEdit(char="中", pinyin="zzz", tone=4)})
        self.assertEqual(syls[0].pinyin, "zhong")
        self.assertEqual(syls[0].tone, 4)

    def test_stress_delta_is_added(self):
        base = text_to_syllables("你好")
        edited = text_to_syllables(
            "你好", edits={0: CharEdit(char="你", stress=0.5)})
        self.assertGreater(edited[0].stress, base[0].stress)

    def test_consecutive_punctuation_keeps_the_first_mark(self):
        # 「？！」被后面的「！」盖掉的话，问句升调就丢了
        self.assertEqual(text_to_syllables("真的吗？！")[-1].punct, "？")
        self.assertEqual(text_to_syllables("太好了！？")[-1].punct, "！")

    def test_trailing_space_still_marks_the_last_syllable_final(self):
        for source in ("你好", "你好 ", "你好，", "你好。"):
            with self.subTest(source=source):
                self.assertTrue(text_to_syllables(source)[-1].final)

    def test_letter_syllables_do_not_take_edits(self):
        # 一个字母拆成多个音节，共用 src 会让一条纠音套到三个音节上
        syls = text_to_syllables(
            "w", edits={0: CharEdit(char="w", pinyin="wei", tone=2)})
        self.assertEqual([s.pinyin for s in syls], ["da", "bu", "liu"])
        self.assertEqual({s.src for s in syls}, {-1})

    def test_number_expansion_keeps_the_edit_on_the_right_character(self):
        # 「100」会展开成「一百」，长度变化会让之后的偏移整体漂移
        syls = text_to_syllables(
            "100个人", edits={4: CharEdit(char="人", pinyin="ren", tone=4)})
        ren = [s for s in syls if s.text == "人"]
        self.assertTrue(ren)
        self.assertEqual(ren[0].tone, 4)

    def test_percent_expansion_keeps_the_edit_aligned(self):
        # 「50%」→「百分之五十」，原文偏移 4 的「人」要落到正确位置
        syls = text_to_syllables(
            "50%的人", edits={4: CharEdit(char="人", pinyin="ren", tone=4)})
        ren = [s for s in syls if s.text == "人"]
        self.assertTrue(ren)
        self.assertEqual(ren[0].tone, 4)

    def test_edit_without_char_is_skipped(self):
        # 手工改过的 JSON 可能没有 char，无法确认位置，一律不应用
        syls = text_to_syllables(
            "中国人", edits={0: CharEdit(pinyin="chong", tone=2)})
        self.assertEqual(syls[0].pinyin, "zhong")
        self.assertEqual(syls[0].tone, 1)

    def test_src_points_at_the_source_character(self):
        syls = text_to_syllables("你好世界")
        self.assertEqual([s.src for s in syls], [0, 1, 2, 3])


class UserDictionaryTests(unittest.TestCase):
    def test_dictionary_reading_wins_over_pypinyin(self):
        syls = text_to_syllables("重明", dictionary={"重明": "chong2 ming2"})
        self.assertEqual([s.pinyin for s in syls], ["chong", "ming"])
        self.assertEqual([s.tone for s in syls], [2, 2])

    def test_char_edit_beats_the_dictionary(self):
        syls = text_to_syllables(
            "重明",
            dictionary={"重明": "chong2 ming2"},
            edits={1: CharEdit(char="明", pinyin="ming", tone=1)})
        self.assertEqual(syls[0].tone, 2)
        self.assertEqual(syls[1].tone, 1)

    def test_bad_entry_leaves_the_text_alone(self):
        plain = text_to_syllables("重明")
        bad = text_to_syllables("重明", dictionary={"重明": "chong ming"})
        self.assertEqual([s.pinyin for s in plain], [s.pinyin for s in bad])


class ToneSandhiScopeTests(unittest.TestCase):
    def test_yi_and_bu_sandhi_only_touches_the_real_character(self):
        # 衣/医 的拼音也是 yi，布/步 也是 bu；按拼音匹配会把它们一起改调
        self.assertEqual([s.tone for s in text_to_syllables("衣服")], [1, 5])
        self.assertEqual(text_to_syllables("医院")[0].tone, 1)
        self.assertEqual([s.tone for s in text_to_syllables("布置")], [4, 4])

    def test_yi_and_bu_themselves_still_change(self):
        self.assertEqual(text_to_syllables("一天")[0].tone, 4)
        self.assertEqual(text_to_syllables("不对")[0].tone, 2)


class NumberEdgeTests(unittest.TestCase):
    def test_thousands_separator_is_not_a_pause(self):
        self.assertEqual(normalize_text("1,234元"), "一千二百三十四元")
        self.assertEqual(normalize_text("1,234,567人"),
                         "一百二十三万四千五百六十七人")

    def test_negative_sign_is_read_as_fu(self):
        self.assertEqual(normalize_text("温度-5度"), "温度负五度")

    def test_leading_zeros_are_read_digit_by_digit(self):
        self.assertEqual(normalize_text("007号"), "零零七号")
        self.assertEqual(normalize_text("0123"), "零一二三")


if __name__ == "__main__":
    unittest.main()
