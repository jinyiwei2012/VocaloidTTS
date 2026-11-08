"""项目文件的往返、缺字段兜底与坏文件处理。"""
import json
import tempfile
import unittest
from pathlib import Path

from vocaloidtts.edits import CharEdit
from vocaloidtts.project import Project, load_project, save_project
from vocaloidtts.prosody import VoiceOptions


class ProjectRoundTripTests(unittest.TestCase):
    def test_full_project_survives_a_round_trip(self):
        project = Project(
            text="重明来了",
            mode="chinese",
            bpm=90.0,
            numerator=3,
            denominator=4,
            options=VoiceOptions(style="news", pitch=70, seed=7),
        )
        project.edits.set(0, CharEdit(char="重", pinyin="chong", tone=2,
                                      stress=0.3, pause_ms=150))
        project.edits.take_snapshot("重明来了")

        restored = Project.from_dict(project.to_dict())
        self.assertEqual(restored.text, "重明来了")
        self.assertEqual(restored.bpm, 90.0)
        self.assertEqual((restored.numerator, restored.denominator), (3, 4))
        self.assertEqual(restored.options.style, "news")
        self.assertEqual(restored.options.pitch, 70)
        self.assertEqual(restored.options.seed, 7)
        self.assertEqual(restored.edits.get(0).pinyin, "chong")
        self.assertEqual(restored.edits.get(0).pause_ms, 150)
        self.assertEqual(restored.edits.snapshot, "重明来了")

    def test_header_records_app_and_schema(self):
        data = Project().to_dict()
        self.assertEqual(data["app"], "VocaloidTTS")
        self.assertEqual(data["schema"], 1)
        self.assertIn("saved", data)


class ProjectFallbackTests(unittest.TestCase):
    def test_empty_dict_gives_defaults(self):
        project = Project.from_dict({})
        self.assertEqual(project.text, "")
        self.assertEqual(project.mode, "chinese")
        self.assertEqual(project.bpm, 120.0)
        self.assertEqual(project.options, VoiceOptions())

    def test_unknown_option_keys_are_ignored(self):
        project = Project.from_dict({"options": {"pitch": 72, "nonsense": 1}})
        self.assertEqual(project.options.pitch, 72)
        self.assertFalse(hasattr(project.options, "nonsense"))

    def test_bad_numbers_fall_back(self):
        project = Project.from_dict({"bpm": "fast", "numerator": None,
                                     "denominator": [4]})
        self.assertEqual(project.bpm, 120.0)
        self.assertEqual(project.numerator, 4)
        self.assertEqual(project.denominator, 4)

    def test_unknown_mode_becomes_chinese(self):
        self.assertEqual(Project.from_dict({"mode": "klingon"}).mode, "chinese")
        self.assertEqual(Project.from_dict({"mode": "pinyin"}).mode, "pinyin")

    def test_non_dict_raises(self):
        with self.assertRaises(ValueError):
            Project.from_dict(["not", "a", "dict"])


class ProjectFileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "song.vttsproj"

    def tearDown(self):
        self._tmp.cleanup()

    def test_save_then_load(self):
        project = Project(text="你好", bpm=100.0)
        save_project(self.path, project)
        self.assertTrue(self.path.exists())
        self.assertEqual(load_project(self.path).text, "你好")

    def test_saved_file_is_readable_json(self):
        save_project(self.path, Project(text="你好"))
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(raw["text"], "你好")
        self.assertEqual(raw["app"], "VocaloidTTS")

    def test_broken_json_raises_value_error(self):
        self.path.write_text("{nope", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_project(self.path)

    def test_missing_file_raises_value_error(self):
        with self.assertRaises(ValueError):
            load_project(self.path)


if __name__ == "__main__":
    unittest.main()
