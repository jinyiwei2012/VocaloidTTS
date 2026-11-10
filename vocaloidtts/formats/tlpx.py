"""TuneLab 新版工程（.tlpx）：和 ``.tlp`` 结构几乎一样，但用 CBOR 编码。

差别只有三处：

- 序列化用 CBOR 而不是 JSON（见 :func:`vocaloidtts.formats.base.cbor_dumps`）；
- part 用 ``startOffset`` / ``endOffset`` 两个字段表达范围，不再是单个 ``dur``；
- 工程多了 ``editorInfo``（播放头位置）和 ``exportConfig``（导出设置）。

音符、音高曲线、速度、拍号的结构和 ``.tlp`` 完全一致，所以音高曲线直接复用
:func:`vocaloidtts.formats.tlp.pitch_curve`。

格式细节参考 LibreSVIP 的 ``libresvip/plugins/tlpx``（MIT，见
THIRD_PARTY_NOTICES.md）。只写单轨、单一速度、不写音频轨。
"""
from __future__ import annotations

import math
from pathlib import Path

from ..atomicio import atomic_write_bytes
from ..prosody import Song
from .base import Format, cbor_dumps, lyric_for
from .tlp import pitch_curve

#: TuneLab 的时间单位和内部 tick 一致。
TICKS_PER_QUARTER = 480

#: 导出设置的默认值（跟 LibreSVIP 写出来的一致）。
EXPORT_CONFIG = {
    "exportPath": "",
    "fileName": "",
    "sampleRate": 44100,
    "bitDepth": 16,
    "masterExportChannels": 2,
    "masterExportEnabled": True,
}


def build_project(song: Song) -> dict:
    notes = [note for note in song.notes if note.dur > 0]
    if not notes:
        raise ValueError("没有可导出的音符")

    numerator = max(1, min(16, int(song.numerator)))
    denominator = int(song.denominator)
    if denominator not in (2, 4, 8, 16):
        denominator = 4
    bar_length = TICKS_PER_QUARTER * 4 * numerator / denominator
    last_end = max(note.start + note.dur for note in notes)
    end_offset = int(math.ceil(last_end / bar_length) * bar_length)

    payload = [{
        "pos": int(note.start),
        "dur": max(1, int(note.dur)),
        "pitch": max(0, min(127, int(note.midi))),
        "lyric": lyric_for(note),
        "pronunciation": note.lyric or None,
        "phonemes": [],
        "properties": {},
    } for note in notes]

    part = {
        "name": "VocaloidTTS",
        "pos": 0,
        "startOffset": 0,
        "endOffset": end_offset,
        "type": "midi",
        "gain": 0.0,
        "voice": {"type": "", "id": ""},
        "properties": {},
        "notes": payload,
        "automations": {},
        "pitch": pitch_curve(song),
        "vibratos": [],
    }

    return {
        "version": 1,
        "tempos": [{"pos": 0, "bpm": max(1.0, float(song.bpm))}],
        "timeSignatures": [{
            "numerator": numerator,
            "denominator": denominator,
            "barIndex": 0,
        }],
        "tracks": [{
            "name": "VocaloidTTS",
            "gain": 0.0,
            "pan": 0.0,
            "mute": False,
            "solo": False,
            "color": "",
            "asRefer": False,
            "parts": [part],
            "exportEnabled": False,
            "exportChannels": 1,
        }],
        "editorInfo": {"playheadPos": 0.0},
        "exportConfig": dict(EXPORT_CONFIG),
    }


def write_tlpx(song: Song, path: str) -> Path:
    """把 Song 写成 TuneLab 的 .tlpx。"""
    target = Path(path).with_suffix(".tlpx")
    atomic_write_bytes(target, cbor_dumps(build_project(song)))
    return target


FORMAT = Format(
    key="tlpx",
    label="TuneLab 工程",
    short="TuneLab X",
    extension=".tlpx",
    filetype=("TuneLab 工程", "*.tlpx"),
    prefix="VocaloidTTS_TuneLabX",
    writer=write_tlpx,
)
