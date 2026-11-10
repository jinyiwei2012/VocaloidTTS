"""Yuan77 工程（.y77）：一份 JSON，音符里直接带整条音高曲线。

格式细节参考 LibreSVIP 的 ``libresvip/plugins/y77``（MIT，见
THIRD_PARTY_NOTICES.md）。这里只保留**写**方向，做了两处简化：

- 只写单轨、单一速度（Yuan77 的工程本来就只有一个 ``bpm`` 字段）；
- ``pit`` 用我们自己的 PIT 曲线采样，不去复刻 LibreSVIP 的 pitch simulator。

两个容易写反的地方：

- ``pitch`` 是 **88 减去 MIDI**（Yuan77 的音高轴和 MIDI 方向相反），不是 MIDI；
- 时间单位是 30 tick（480 / 16），所以 ``start`` / ``len`` 都要除以 30 再取整。

``pit`` 的约定：500 个采样点，50 是音符本身的音高，±50 对应 ``pbs`` 个半音；
``pbs`` 字段存的是「上限减一」。全平直的音符 ``pbs`` 会写成 -1，和 LibreSVIP
一致。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from ..atomicio import atomic_write_text
from ..prosody import Song
from .base import Format, lyric_for, pitch_samples, resample

#: Yuan77 的时间单位：30 tick = 1 个单位。
TICKS_PER_UNIT = 30

#: 每个音符存多少个音高采样点。
PITCH_SAMPLES = 500

#: 音高轴的零点：pitch = 88 - MIDI。
PITCH_ORIGIN = 88


def _units(value: float) -> int:
    return int(round(value / TICKS_PER_UNIT))


def _pitch(note, song: Song) -> tuple[list[float], int]:
    """返回 (pit 列表, pbs)。pit 以 50 为中心，pbs 是上限减一。"""
    samples = [value / 100.0 for value in pitch_samples(song, note, PITCH_SAMPLES)]
    peak = max(abs(value) for value in samples)
    pbs = min(math.ceil(peak), 12)
    if pbs <= 0:
        return [50.0] * PITCH_SAMPLES, -1
    curve = [round(value * 50.0 / pbs + 50.0, 3) for value in samples]
    return curve, pbs - 1


def build_project(song: Song) -> dict:
    song = resample(song)
    notes = [note for note in song.notes if note.dur > 0]
    if not notes:
        raise ValueError("没有可导出的音符")

    numerator = max(1, min(16, int(song.numerator)))
    denominator = int(song.denominator)
    if denominator not in (2, 4, 8, 16):
        denominator = 4

    payload = []
    for note in notes:
        curve, pbs = _pitch(note, song)
        payload.append({
            # note.lyric 本来就是拼音，不用再转一次
            "py": note.lyric or lyric_for(note),
            "len": max(1, _units(note.dur)),
            "start": _units(note.start),
            "lyric": lyric_for(note),
            "pitch": PITCH_ORIGIN - max(0, min(127, int(note.midi))),
            "pbs": pbs,
            "pit": curve,
        })

    return {
        "bpm": max(1.0, float(song.bpm)),
        "bars": 100,
        "notes": payload,
        "nnote": len(payload),
        "bbar": numerator,
        "v": 10001,
        "bbeat": denominator,
    }


def write_y77(song: Song, path: str) -> Path:
    """把 Song 写成 Yuan77 的 .y77。"""
    project = build_project(song)
    target = Path(path).with_suffix(".y77")
    atomic_write_text(target, json.dumps(project, ensure_ascii=False))
    return target


FORMAT = Format(
    key="y77",
    label="Yuan77 工程",
    short="Yuan77",
    extension=".y77",
    filetype=("Yuan77 工程", "*.y77"),
    prefix="VocaloidTTS_Yuan77",
    writer=write_y77,
)
