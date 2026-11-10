"""AISingers Studio 工程（.aisp）。

这个格式的文件结构比较特别：**一行 JSON 头 + 剩下的 JSON 体**，用换行分开，
不是单个 JSON 对象。头里放速度/拍号/总长度，体里放轨道和音符。

格式细节参考 LibreSVIP 的 ``libresvip/plugins/aisp``（MIT，见
THIRD_PARTY_NOTICES.md）。这里只保留**写**方向，做了三处简化：

- 只写单轨、单一速度；
- 不写音频轨（``im`` 里只放唱轨）；
- ``pit`` 用自己的 PIT 曲线采样，不复刻它的 pitch simulator。

单位换算有两处容易错：

- 时间单位是 15 tick（480 / 32），所以位置都要除以 15；
- ``m``（midi_no）是 **MIDI 减 12**，不是 MIDI 本身；
- ``pit`` 的数值是 **十分之一半音**（deci-semitone），不是音分。

``pit`` 在文件里是游程压缩的字符串：``"0x500"`` 表示「值 0 重复 500 次」，
不压缩的话一首歌会多出几十万个数字。
"""
from __future__ import annotations

import json
from itertools import groupby
from pathlib import Path

from ..atomicio import atomic_write_text
from ..prosody import Song
from .base import Format, lyric_for, pitch_samples, resample

#: 时间单位：15 tick = 1 个单位（32 个单位 = 一个四分音符）。
TICKS_PER_UNIT = 15

#: 每个四分音符的音符数，用来算工程总小节数。
UNITS_PER_BAR = 128

#: 每个音符存多少个音高采样点。
PITCH_SAMPLES = 500

#: midi_no 的偏移：AISingers 写的是 MIDI - 12。
MIDI_OFFSET = 12


def _units(value: float) -> int:
    return int(round(value / TICKS_PER_UNIT))


def _pit_string(song: Song, note) -> str:
    """把音高采样压成游程字符串，单位是十分之一半音。"""
    values = [round(value / 10.0, 2) for value in pitch_samples(song, note, PITCH_SAMPLES)]
    parts: list[str] = []
    for value, group in groupby(values):
        count = sum(1 for _ in group)
        parts.append(f"{value}x{count}" if count > 1 else f"{value}")
    return " ".join(parts)


def build_project(song: Song) -> tuple[dict, dict]:
    """返回 (头, 体) 两个字典，分别序列化成两行。"""
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
        start = _units(note.start)
        end = _units(note.start + note.dur)
        payload.append({
            "s": start,
            "l": max(1, end - start),
            "m": max(0, min(127, int(note.midi))) - MIDI_OFFSET,
            "ly": lyric_for(note),
            # note.lyric 本来就是拼音
            "py": note.lyric or lyric_for(note),
            "vel": 50,
            "tri": False,
            "pit": _pit_string(song, note),
            "bc": 0,
            "bj": 0,
            "bq": 0,
        })

    last_end = _units(max(note.start + note.dur for note in notes))
    bar_units = max(1, UNITS_PER_BAR * numerator // denominator)
    bars = max(100, -(-last_end // bar_units))

    head = {
        "tempo": [{
            "tempo_float": max(1.0, float(song.bpm)),
            "start_128": 0,
            "start_bar": 0,
            "start_beat_in_bar": 0,
        }],
        "signature": [{
            "beat_zi": numerator,
            "beat_mu": denominator,
            "start_bar": 0,
            "str": f"{numerator}/{denominator}",
        }],
        "flags": -256,
        "flage": -128,
        "time": last_end,
        "bar": bars,
    }
    body = {
        "tracks": [{
            "i": 0,
            "s": False,
            "m": False,
            "v": 0,
            "n": "VocaloidTTS",
            "t": 0,
            "sn": "",
            "se": "",
            "sh": "",
            "im": [{
                "uid": 0,
                "s": 0,
                "l": last_end,
                "n": payload,
            }],
        }],
        "num_track": 1,
    }
    return head, body


def write_aisp(song: Song, path: str) -> Path:
    """把 Song 写成 AISingers 的 .aisp。"""
    head, body = build_project(song)
    text = (json.dumps(head, ensure_ascii=False, separators=(", ", ": ")) + "\n"
            + json.dumps(body, ensure_ascii=False, separators=(", ", ": ")))
    target = Path(path).with_suffix(".aisp")
    atomic_write_text(target, text)
    return target


FORMAT = Format(
    key="aisp",
    label="AISingers 工程",
    short="AISingers",
    extension=".aisp",
    filetype=("AISingers Studio 工程", "*.aisp"),
    prefix="VocaloidTTS_AISingers",
    writer=write_aisp,
)
