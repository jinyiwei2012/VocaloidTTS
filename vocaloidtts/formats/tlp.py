"""TuneLab 旧版工程（.tlp）：一份 JSON，音符 + 分段音高曲线。

格式细节参考 LibreSVIP 的 ``libresvip/plugins/tlp``（MIT，见
THIRD_PARTY_NOTICES.md）。这里只保留**写**方向，做了两处简化：

- 只写单轨、单一速度、不写音频轨；
- ``automations`` / ``vibratos`` 留空，让编辑器用默认值。

时间单位和我们一样是 480 tick / 四分音符，不需要换算。

音高曲线（``pitch``）是**绝对音高**（半音），不是相对偏移：每个段是一串
``[pos1, value1, pos2, value2, ...]``。我们的 PIT 是相对音符的，所以要加上
音符自己的 MIDI 才是绝对音高。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from ..atomicio import atomic_write_text
from ..prosody import Song
from .base import Format, lyric_for, pit_cents

#: TuneLab 的时间单位和内部 tick 一致。
TICKS_PER_QUARTER = 480


def _pitch_curve(song: Song) -> list[list[float]]:
    """把所有音符的 PIT 转成一条绝对音高曲线。"""
    points: list[tuple[float, float]] = []
    for note in song.notes:
        for rel_tick, cents in pit_cents(song, note):
            points.append((float(note.start + rel_tick),
                           round(note.midi + cents / 100.0, 4)))
    if not points:
        return []
    points.sort(key=lambda pair: pair[0])
    flat: list[float] = []
    for tick, value in points:
        flat.extend((tick, value))
    return [flat]


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
    duration = math.ceil(last_end / bar_length) * bar_length

    payload = [{
        "pos": int(note.start),
        "dur": max(1, int(note.dur)),
        "pitch": max(0, min(127, int(note.midi))),
        "lyric": lyric_for(note),
        # TuneLab 把歌词和读音分开存；我们的 note.lyric 本来就是拼音
        "pronunciation": note.lyric or None,
        "phonemes": [],
        "properties": {},
    } for note in notes]

    return {
        "version": 0,
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
            "parts": [{
                "name": "VocaloidTTS",
                "pos": 0,
                "dur": int(duration),
                "type": "midi",
                "gain": 0.0,
                "voice": {"type": "", "id": ""},
                "properties": {},
                "notes": payload,
                "automations": {},
                "pitch": _pitch_curve(song),
                "vibratos": [],
            }],
        }],
    }


def write_tlp(song: Song, path: str) -> Path:
    """把 Song 写成 TuneLab 的 .tlp。"""
    project = build_project(song)
    target = Path(path).with_suffix(".tlp")
    atomic_write_text(target, json.dumps(project, ensure_ascii=False))
    return target


FORMAT = Format(
    key="tlp",
    label="TuneLab 工程（旧）",
    short="TuneLab",
    extension=".tlp",
    filetype=("TuneLab 旧版工程", "*.tlp"),
    prefix="VocaloidTTS_TuneLab",
    writer=write_tlp,
)
