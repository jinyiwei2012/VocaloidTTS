"""VoiSona 手机版 .tsmsln 导出的结构回归。

和 .tssln 共用 JUCE ValueTree 容器，但根节点名、版本号和轨道层级都不一样，
所以单独测一遍差异点。读取器直接复用 test_tssln 里的那份。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.test_tssln import _find, _parse
from vocaloidtts.formats import formats, tsmsln
from vocaloidtts.prosody import VoiceOptions, compose


class TsmslnExportTests(unittest.TestCase):
    def _root(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = tsmsln.FORMAT.writer(compose("你好世界", VoiceOptions(seed=42)),
                                    str(Path(tmp.name) / "x.tsmsln"))
        return _parse(path.read_bytes())

    def test_root_name_and_version(self) -> None:
        root = self._root()
        self.assertEqual(root["name"], tsmsln.ROOT_NAME)
        self.assertEqual(root["attrs"]["VersionOfAppFileSaved"], tsmsln.APP_VERSION)

    def test_no_desktop_only_children(self) -> None:
        root = self._root()
        names = [child["name"] for child in root["children"]]
        self.assertEqual(names, ["Tracks"])

    def test_track_has_one_less_layer(self) -> None:
        root = self._root()
        tracks = _find(root, "Tracks")
        self.assertEqual(len(tracks["children"]), 1)
        item = tracks["children"][0]
        self.assertEqual(item["name"], "Track")
        # 手机版直接挂唱轨，没有外层容器，所以这里就已经带 PluginData 了
        self.assertIn("PluginData", item["attrs"])

    def test_state_information_version(self) -> None:
        root = self._root()
        item = _find(root, "Tracks")["children"][0]
        inner = _parse(item["attrs"]["PluginData"])
        self.assertEqual(inner["name"], "StateInformation")
        self.assertEqual(inner["attrs"]["VersionOfAppFileSaved"], tsmsln.APP_VERSION)
        song = _find(inner, "Song")
        self.assertEqual([child["name"] for child in song["children"]],
                         ["Tempo", "Beat", "Score"])

    def test_notes_match_song(self) -> None:
        root = self._root()
        item = _find(root, "Tracks")["children"][0]
        inner = _parse(item["attrs"]["PluginData"])
        score = _find(_find(inner, "Song"), "Score")
        song = compose("你好世界", VoiceOptions(seed=42))
        self.assertEqual(len(score["children"]), len(song.notes))
        self.assertEqual(score["children"][0]["attrs"]["Lyric"], "ni")

    def test_empty_song_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            tsmsln.write_tsmsln(compose("", VoiceOptions(seed=1)), "x.tsmsln")

    def test_registry(self) -> None:
        self.assertEqual(formats()["tsmsln"].extension, ".tsmsln")


if __name__ == "__main__":
    unittest.main()
