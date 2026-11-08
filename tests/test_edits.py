"""逐字纠音的数据模型：序列化、快照校验、词典换算。"""
import json
import tempfile
import unittest
from pathlib import Path

from vocaloidtts.edits import (CharEdit, EditSet, dictionary_overrides,
                               load_userdict, parse_reading, save_userdict)


class ParseReadingTests(unittest.TestCase):
    def test_reads_toned_syllables(self):
        self.assertEqual(parse_reading("zhong1 guo2"),
                         [("zhong", 1), ("guo", 2)])

    def test_accepts_u_umlaut_and_colon(self):
        self.assertEqual(parse_reading("nv3 hai2"), [("nv", 3), ("hai", 2)])
        self.assertEqual(parse_reading("nu:3"), [("nv", 3)])

    def test_rejects_missing_tone(self):
        self.assertIsNone(parse_reading("zhong guo"))
        self.assertIsNone(parse_reading("zhong1 guo"))

    def test_rejects_empty_and_garbage(self):
        for source in ("", "   ", "zhong6", "123", "zhong1 guo2!"):
            with self.subTest(source=source):
                self.assertIsNone(parse_reading(source))


class DictionaryTests(unittest.TestCase):
    def test_word_applies_to_every_occurrence(self):
        out = dictionary_overrides("重明来了，重明走了",
                                   {"重明": "chong2 ming2"})
        self.assertEqual(out[0], ("chong", 2))
        self.assertEqual(out[1], ("ming", 2))
        self.assertEqual(out[5], ("chong", 2))
        self.assertEqual(out[6], ("ming", 2))

    def test_longer_word_wins_over_shorter(self):
        out = dictionary_overrides("中国人", {"中国": "zhong1 guo2",
                                              "国": "guo2"})
        self.assertEqual(out[0], ("zhong", 1))
        self.assertEqual(out[1], ("guo", 2))

    def test_length_mismatch_is_ignored(self):
        out = dictionary_overrides("中国人", {"中国": "zhong1"})
        self.assertEqual(out, {})

    def test_bad_reading_is_ignored(self):
        out = dictionary_overrides("中国人", {"中国": "zhong guo"})
        self.assertEqual(out, {})


class CharEditTests(unittest.TestCase):
    def test_round_trip_keeps_only_set_fields(self):
        edit = CharEdit(pinyin="zhong", tone=4, pause_ms=120)
        data = edit.to_dict()
        self.assertEqual(data, {"pinyin": "zhong", "tone": 4, "pause_ms": 120})
        self.assertEqual(CharEdit.from_dict(data), edit)

    def test_empty_edit_round_trips_as_empty(self):
        self.assertTrue(CharEdit().is_empty())
        self.assertEqual(CharEdit.from_dict({}), CharEdit())

    def test_from_dict_clamps_tone_and_ignores_junk(self):
        edit = CharEdit.from_dict({"tone": 99, "stress": "x", "dur_scale": 1.5})
        self.assertEqual(edit.tone, 5)
        self.assertIsNone(edit.stress)
        self.assertEqual(edit.dur_scale, 1.5)


class EditSetTests(unittest.TestCase):
    def test_set_and_get(self):
        edits = EditSet()
        edits.set(3, CharEdit(pinyin="zhong", tone=1))
        self.assertEqual(edits.get(3).pinyin, "zhong")
        self.assertIsNone(edits.get(4))

    def test_empty_edit_removes_the_entry(self):
        edits = EditSet()
        edits.set(3, CharEdit(pinyin="zhong", tone=1))
        edits.set(3, CharEdit())
        self.assertEqual(edits.chars, {})

    def test_snapshot_guards_against_drifted_text(self):
        edits = EditSet()
        edits.take_snapshot("你好世界")
        self.assertTrue(edits.matches("你好世界"))
        self.assertFalse(edits.matches("你好，世界"))

    def test_blank_snapshot_accepts_anything(self):
        self.assertTrue(EditSet().matches("随便什么"))

    def test_round_trip_through_dict(self):
        edits = EditSet(snapshot="你好")
        edits.set(1, CharEdit(pinyin="hao", tone=3, stress=0.2))
        restored = EditSet.from_dict(edits.to_dict())
        self.assertEqual(restored, edits)

    def test_from_dict_skips_bad_offsets(self):
        restored = EditSet.from_dict({
            "snapshot": "x",
            "chars": {"-1": {"pinyin": "a", "tone": 1},
                      "abc": {"pinyin": "b", "tone": 1},
                      "2": {"pinyin": "c", "tone": 1}},
        })
        self.assertEqual(list(restored.chars), [2])


class UserDictFileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "userdict.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_round_trip(self):
        save_userdict(self.path, {"重明": "chong2 ming2", "阿": "a1"})
        self.assertEqual(load_userdict(self.path),
                         {"重明": "chong2 ming2", "阿": "a1"})

    def test_missing_file_is_empty(self):
        self.assertEqual(load_userdict(self.path), {})

    def test_broken_file_is_empty(self):
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(load_userdict(self.path), {})

    def test_wrong_shape_is_empty(self):
        self.path.write_text(json.dumps({"words": [1, 2]}), encoding="utf-8")
        self.assertEqual(load_userdict(self.path), {})

    def test_blank_keys_are_dropped(self):
        save_userdict(self.path, {"": "x1", "好": "hao3"})
        self.assertEqual(load_userdict(self.path), {"好": "hao3"})


if __name__ == "__main__":
    unittest.main()
