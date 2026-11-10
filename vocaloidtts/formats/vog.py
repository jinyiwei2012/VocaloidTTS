"""Vogen 工程（.vog）：一个 zip 包，里面只有一份 ``chart.json``。

结构很小：``timeSig0`` 是 "4/4" 这样的字符串、``bpm0`` 是一个数字、``utts``
是轨道数组，每条轨道挂音符。音符带歌词（``lyric``）和罗马字/拼音
（``rom``），所以中文用户能直接用。

格式细节参考 LibreSVIP 的 ``libresvip/plugins/vog``（MIT，见
THIRD_PARTY_NOTICES.md）。时间单位和我们一样是 480 tick / 四分音符。

简化：只写单轨、单一速度，不绑歌手（``singerId`` 留 null，由编辑器自己挑）。
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from ..atomicio import atomic_write_bytes
from ..prosody import Song
from .base import Format, lyric_for, resample


def build_project(song: Song, title: str = "VocaloidTTS") -> dict:
    song = resample(song)
    notes = [note for note in song.notes if note.dur > 0]
    if not notes:
        raise ValueError("没有可导出的音符")

    numerator = max(1, min(16, int(song.numerator)))
    denominator = int(song.denominator)
    if denominator not in (2, 4, 8, 16):
        denominator = 4

    payload = [{
        "pitch": max(0, min(127, int(note.midi))),
        "lyric": lyric_for(note),
        # note.lyric 本来就是拼音，直接当 rom 用
        "rom": note.lyric or lyric_for(note),
        "on": max(0, int(note.start)),
        "dur": max(1, int(note.dur)),
    } for note in notes]

    return {
        "timeSig0": f"{numerator}/{denominator}",
        "bpm0": max(1.0, float(song.bpm)),
        "accomOffset": 0,
        "utts": [{
            "name": title or "VocaloidTTS",
            "singerId": None,
            "romScheme": "",
            "notes": payload,
        }],
    }


def write_vog(song: Song, path: str) -> Path:
    """把 Song 写成 Vogen 的 .vog。"""
    project = build_project(song)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("chart.json",
                         json.dumps(project, ensure_ascii=False,
                                    separators=(",", ":")))
    target = Path(path).with_suffix(".vog")
    atomic_write_bytes(target, buffer.getvalue())
    return target


FORMAT = Format(
    key="vog",
    label="Vogen 工程",
    short="Vogen",
    extension=".vog",
    filetype=("Vogen 工程", "*.vog"),
    prefix="VocaloidTTS_Vogen",
    writer=write_vog,
)
