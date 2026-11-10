"""VoiSona .tssln 导出的结构回归。

.tssln 是 JUCE ValueTree 二进制，所以测试里自带一个独立写的读取器：
压缩整数、CString、类型标签、递归节点全部按格式规范解一遍。
"""
from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from vocaloidtts.formats import formats, tssln
from vocaloidtts.prosody import VoiceOptions, compose


def _cint(data: bytes, offset: int) -> tuple[int, int]:
    width = data[offset]
    offset += 1
    return int.from_bytes(data[offset:offset + width], "little"), offset + width


def _cstring(data: bytes, offset: int) -> tuple[str, int]:
    end = data.index(b"\x00", offset)
    return data[offset:end].decode("utf-8"), end + 1


def _variant(data: bytes, offset: int):
    length, offset = _cint(data, offset)
    if length == 0:
        return None, offset
    end = offset + length
    kind = data[offset]
    offset += 1
    if kind == 1:
        value = int.from_bytes(data[offset:offset + 4], "little", signed=True)
        offset += 4
    elif kind == 2:
        value = True
    elif kind == 3:
        value = False
    elif kind == 4:
        value = struct.unpack("<d", data[offset:offset + 8])[0]
        offset += 8
    elif kind == 5:
        value, offset = _cstring(data, offset)
    elif kind == 8:
        value = data[offset:end]
        offset = end
    else:
        raise AssertionError(f"未处理的变体类型：{kind}")
    assert offset == end, (offset, end)
    return value, offset


def _node(data: bytes, offset: int):
    name, offset = _cstring(data, offset)
    count, offset = _cint(data, offset)
    attrs = {}
    for _ in range(count):
        attr_name, offset = _cstring(data, offset)
        value, offset = _variant(data, offset)
        attrs[attr_name] = value
    child_count, offset = _cint(data, offset)
    children = []
    for _ in range(child_count):
        child, offset = _node(data, offset)
        children.append(child)
    return {"name": name, "attrs": attrs, "children": children}, offset


def _parse(data: bytes) -> dict:
    root, offset = _node(data, 0)
    assert offset == len(data), (offset, len(data))
    return root


def _find(node: dict, name: str) -> dict:
    for child in node["children"]:
        if child["name"] == name:
            return child
    raise AssertionError(f"找不到节点 {name}")


class TsslnExportTests(unittest.TestCase):
    def _root(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = tssln.FORMAT.writer(compose("你好世界", VoiceOptions(seed=42)),
                                   str(Path(tmp.name) / "x.tssln"))
        return _parse(path.read_bytes())

    def test_root(self) -> None:
        root = self._root()
        self.assertEqual(root["name"], "TSSolution")
        self.assertEqual(root["attrs"]["VersionOfAppFileSaved"], tssln.APP_VERSION)
        self.assertEqual([child["name"] for child in root["children"]],
                         ["PlayControl", "Tracks", "GUIStatus"])

    def test_play_control_and_gui(self) -> None:
        root = self._root()
        play = _find(root, "PlayControl")
        self.assertIs(play["attrs"]["Loop"], False)
        self.assertEqual(play["attrs"]["PlayPosition"], 0.0)
        gui = _find(root, "GUIStatus")
        self.assertEqual(gui["attrs"]["ScaleX"], 100.0)

    def test_track_layers(self) -> None:
        root = self._root()
        tracks = _find(root, "Tracks")
        self.assertEqual(len(tracks["children"]), 1)
        wrapper = tracks["children"][0]
        self.assertEqual(wrapper["name"], "Track")
        self.assertEqual(len(wrapper["children"]), 1)
        item = wrapper["children"][0]
        self.assertEqual(item["name"], "Track")
        self.assertEqual(item["attrs"]["Type"], tssln.TRACK_TYPE_SINGING)
        self.assertEqual(item["attrs"]["Name"], "VocaloidTTS")

    def test_plugin_data_is_a_nested_tree(self) -> None:
        root = self._root()
        item = _find(root, "Tracks")["children"][0]["children"][0]
        inner = _parse(item["attrs"]["PluginData"])
        self.assertEqual(inner["name"], "StateInformation")
        song = _find(inner, "Song")
        self.assertEqual([child["name"] for child in song["children"]],
                         ["Tempo", "Beat", "Score"])

    def test_tempo_and_beat(self) -> None:
        root = self._root()
        inner = _parse(_find(root, "Tracks")["children"][0]["children"][0]["attrs"]["PluginData"])
        song = _find(inner, "Song")
        sound = _find(song, "Tempo")["children"][0]
        self.assertEqual(sound["name"], "Sound")
        self.assertEqual(sound["attrs"]["Tempo"], 120.0)
        self.assertEqual(sound["attrs"]["Clock"], 0)
        time_item = _find(song, "Beat")["children"][0]
        self.assertEqual(time_item["name"], "Time")
        self.assertEqual((time_item["attrs"]["Beats"], time_item["attrs"]["BeatType"]), (4, 4))

    def test_notes(self) -> None:
        root = self._root()
        inner = _parse(_find(root, "Tracks")["children"][0]["children"][0]["attrs"]["PluginData"])
        score = _find(_find(inner, "Song"), "Score")
        song = compose("你好世界", VoiceOptions(seed=42))
        self.assertEqual(len(score["children"]), len(song.notes))
        first = score["children"][0]["attrs"]
        # clock 是 tick 的两倍
        self.assertEqual(first["Clock"], song.notes[0].start * tssln.CLOCK_PER_TICK)
        self.assertEqual(first["Duration"], song.notes[0].dur * tssln.CLOCK_PER_TICK)
        # 音高拆成八度 + 音级
        self.assertEqual(first["PitchOctave"], song.notes[0].midi // 12 + tssln.OCTAVE_OFFSET)
        self.assertEqual(first["PitchStep"], song.notes[0].midi % 12)
        self.assertEqual(first["Lyric"], "ni")

    def test_empty_song_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            tssln.write_tssln(compose("", VoiceOptions(seed=1)), "x.tssln")

    def test_registry(self) -> None:
        self.assertEqual(formats()["tssln"].extension, ".tssln")


if __name__ == "__main__":
    unittest.main()
