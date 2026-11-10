"""DiffScope 工程交换格式（.dspx）：zstd 压缩的 JSON。

容器和 ACE Studio 的 ``.acep`` 是同一套思路——zstd 帧里装一份 JSON——所以直接
复用 :func:`vocaloidtts.formats.base.zstd_store`（Raw 块，零依赖）。区别是这里
没有 base64 包装，压缩后的字节就是整个文件。

格式细节参考 LibreSVIP 的 ``libresvip/plugins/dspx``（MIT，见
THIRD_PARTY_NOTICES.md）。它的模型是 ``extra="forbid"`` + ``strict=True``，
也就是**每个字段都必须出现**，少一个就解析失败，所以下面把
pronunciation / phonemes / vibrato / workspace 这些空壳也一并写出来。

简化之处：

- 只写一条唱轨、一个 clip，``params`` 留空（音高曲线交给 DiffScope 自己算）；
- ``sources`` 写 null，不绑定歌手；
- clip 的 ``pos`` / ``length`` 都是 0，实际范围由 ``clipStart`` / ``clipLen``
  给出（和 LibreSVIP 的写法一致）。
"""
from __future__ import annotations

import json
from pathlib import Path

from ..atomicio import atomic_write_bytes
from ..prosody import Song
from .base import Format, lyric_for, zstd_store, resample

#: 工程版本号，目前只有 1.0.0。
PROJECT_VERSION = "1.0.0"


def _neutral_vibrato() -> dict:
    return {
        "start": 0.0,
        "end": 1.0,
        "amp": 0,
        "freq": 0.0,
        "phase": 0.0,
        "offset": 0,
        "points": {"amp": [], "freq": []},
    }


def _note(note) -> dict:
    return {
        "pos": max(0, int(note.start)),
        "length": max(1, int(note.dur)),
        "keyNum": max(0, min(127, int(note.midi))),
        "centShift": 0,
        "language": "",
        "lyric": lyric_for(note),
        "pronunciation": {"original": "", "edited": ""},
        "phonemes": {"original": [], "edited": []},
        "vibrato": _neutral_vibrato(),
        "workspace": {},
    }


def _control() -> dict:
    return {"gain": 0.0, "mute": False, "pan": 0.0}


def build_model(song: Song, title: str = "VocaloidTTS") -> dict:
    song = resample(song)
    notes = [note for note in song.notes if note.dur > 0]
    if not notes:
        raise ValueError("没有可导出的音符")

    numerator = max(1, min(16, int(song.numerator)))
    denominator = int(song.denominator)
    if denominator not in (1, 2, 4, 8, 16, 32, 64, 128):
        denominator = 4
    bpm = max(10.0, min(1000.0, float(song.bpm)))
    clip_len = max(int(note.start) + int(note.dur) for note in notes)

    clip = {
        "type": "singing",
        "name": title or "VocaloidTTS",
        "time": {"pos": 0, "length": 0, "clipStart": 0, "clipLen": clip_len},
        "control": _control(),
        "notes": [_note(note) for note in notes],
        "params": {},
        "sources": None,
        "workspace": {},
    }
    track = {
        "name": title or "VocaloidTTS",
        "control": {**_control(), "solo": False},
        "clips": [clip],
        "workspace": {},
    }
    content = {
        "global": {
            "author": "",
            "centShift": 0,
            "editorId": "vocaloidtts",
            "editorName": "VocaloidTTS",
            "name": title or "",
        },
        "master": {"control": _control()},
        "timeline": {
            "labels": [],
            "tempos": [{"pos": 0, "value": bpm}],
            "timeSignatures": [{"index": 0, "numerator": numerator,
                                "denominator": denominator}],
        },
        "tracks": [track],
        "workspace": {},
    }
    return {"version": PROJECT_VERSION, "content": content}


def write_dspx(song: Song, path: str) -> Path:
    """把 Song 写成 DiffScope 的 .dspx。"""
    model = build_model(song)
    payload = json.dumps(model, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    target = Path(path).with_suffix(".dspx")
    atomic_write_bytes(target, zstd_store(payload))
    return target


FORMAT = Format(
    key="dspx",
    label="DiffScope 工程",
    short="DiffScope",
    extension=".dspx",
    filetype=("DiffScope 工程", "*.dspx"),
    prefix="VocaloidTTS_DiffScope",
    writer=write_dspx,
)
