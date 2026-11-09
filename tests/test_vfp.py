"""VOX Factory .vfp 导出的结构回归。

.vfp 是 zip + 键值表式 JSON，所以测试既解压也核对「对象在 bank 里、顺序在
order 里」这两处是否一致。
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from vocaloidtts.formats import formats, vfp
from vocaloidtts.prosody import VoiceOptions, compose


def _song():
    return compose("你好世界", VoiceOptions(seed=42))


class VfpExportTests(unittest.TestCase):
    def _read(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = vfp.FORMAT.writer(_song(), str(Path(tmp.name) / "x.vfp"))
        with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as archive:
            names = sorted(archive.namelist())
            payload = archive.read("project.json")
        return names, json.loads(payload)

    def test_container(self) -> None:
        names, _ = self._read()
        self.assertIn("project.json", names)
        self.assertTrue(any(name.startswith("resources/") for name in names))

    def test_top_level(self) -> None:
        _, project = self._read()
        self.assertEqual(project["version"], vfp.PROJECT_VERSION)
        self.assertEqual(project["tempo"], 120.0)
        self.assertEqual(project["timeSignature"], [4, 4])
        self.assertEqual(project["audioDataBank"], {})
        self.assertEqual(len(project["trackOrder"]), 1)
        self.assertEqual(project["trackOrder"], list(project["trackBank"]))

    def test_track_and_clip_banks_agree(self) -> None:
        _, project = self._read()
        track = project["trackBank"][project["trackOrder"][0]]
        self.assertEqual(track["type"], "vocal")
        self.assertEqual(track["clipOrder"], list(track["clipBank"]))
        clip = track["clipBank"][track["clipOrder"][0]]
        self.assertEqual(clip["type"], "vocal")
        self.assertEqual(clip["lengthType"], "quarter")
        self.assertEqual(clip["length"], vfp.CLIP_QUARTERS)
        self.assertEqual(clip["startQuarter"], 0)
        self.assertEqual(clip["noteOrder"], list(clip["noteBank"]))

    def test_notes(self) -> None:
        _, project = self._read()
        track = project["trackBank"][project["trackOrder"][0]]
        clip = track["clipBank"][track["clipOrder"][0]]
        notes = [clip["noteBank"][key] for key in clip["noteOrder"]]
        song = _song()
        self.assertEqual(len(notes), len(song.notes))
        first = notes[0]
        self.assertEqual(first["ticks"], song.notes[0].start)
        self.assertEqual(first["durationTicks"], song.notes[0].dur)
        self.assertEqual(first["midi"], song.notes[0].midi)
        self.assertEqual(first["name"], "你")
        self.assertEqual(first["syllable"], "ni")
        # 秒数也要写，且和 tick 换算一致
        self.assertAlmostEqual(first["time"], 0.0, places=6)
        self.assertGreater(first["duration"], 0.0)

    def test_export_is_reproducible(self) -> None:
        """键名用固定前缀，同一份 Song 导两次应当逐字节一致。"""
        first = vfp.build_project(_song())
        second = vfp.build_project(_song())
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))

    def test_empty_song_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            vfp.write_vfp(compose("", VoiceOptions(seed=1)), "x.vfp")

    def test_registry(self) -> None:
        self.assertEqual(formats()["vfp"].extension, ".vfp")


if __name__ == "__main__":
    unittest.main()
