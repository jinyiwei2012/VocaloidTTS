"""Synthesizer V Studio 工程（.svp）。

格式细节参考 LibreSVIP 的 ``libresvip/plugins/svp``（MIT，见
THIRD_PARTY_NOTICES.md），这里只保留**写**方向，并且做了三处简化：

- 单轨，不生成 ``groups`` / ``library`` 的引用关系；
- ``phonemes`` 留空——Synthesizer V 会按歌词自己生成发音，省掉一整张
  音素映射表（它的音素写法和 VOCALOID 的 X-SAMPA 不一样）；
- 只写 ``pitchDelta`` 一条曲线，其余参数留给编辑器。

时间单位：SVP 用 blick，1 个四分音符 = 705,600,000 blick。我们内部是
480 tick/四分音符，所以 1 tick = 1,470,000 blick（LibreSVIP 的 TICK_RATE）。
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from ..atomicio import atomic_write_text
from ..prosody import Song
from .base import Format, PitchIndex, lyric_for, pit_cents, resample

#: 1 tick（480/四分音符）对应的 blick 数。
BLICK_PER_TICK = 1_470_000

#: 写 Studio 2 的格式版本。Studio 1 的 153 需要文件末尾补一个 NUL，
#: 这一版没做兼容，打开旧编辑器会提示版本过新。
SVP_VERSION = 196


def _uuid() -> str:
    return str(uuid.uuid4())


def _pitch_points(song: Song, index: PitchIndex) -> list[float]:
    """把每个音符的 PIT 点摊平成 SVP 的 ``[x1, y1, x2, y2, ...]``。"""
    raw: list[tuple[int, float]] = []
    for note in song.notes:
        for rel_tick, cents in pit_cents(song, note, pitch_index=index):
            raw.append((int((note.start + rel_tick) * BLICK_PER_TICK),
                        round(cents, 3)))
    raw.sort(key=lambda pair: pair[0])
    return [value for pair in raw for value in pair]


def write_svp(song: Song, path: str) -> Path:
    """把 Song 写成 Synthesizer V Studio 2 的 .svp。"""
    song = resample(song)
    if not song.notes:
        raise ValueError("没有可导出的音符")

    index = PitchIndex(song.controls.get("P", []))
    notes = [
        {
            "onset": int(note.start * BLICK_PER_TICK),
            "duration": max(1, int(note.dur * BLICK_PER_TICK)),
            "lyrics": lyric_for(note),
            # 留空 = 让编辑器按歌词自动生成发音
            "phonemes": "",
            "pitch": int(note.midi),
            "musicalType": "singing",
            "uuid": _uuid(),
        }
        for note in song.notes
    ]

    group_uuid = _uuid()
    project = {
        "version": SVP_VERSION,
        "uuid": _uuid(),
        "time": {
            "meter": [{
                "index": 0,
                "numerator": max(1, min(16, int(song.numerator))),
                "denominator": int(song.denominator),
            }],
            "tempo": [{"position": 0, "bpm": float(song.bpm)}],
        },
        "library": [],
        "tracks": [{
            "name": "VocaloidTTS",
            "dispColor": "ff7db235",
            "dispOrder": 0,
            "renderEnabled": True,
            "mixer": {"pan": 0.0, "mute": False, "solo": False,
                      "display": True, "gainDecibel": 0.0},
            "groups": [],
            "mainGroup": {
                "name": "main",
                "uuid": group_uuid,
                "notes": notes,
                "parameters": {
                    "pitchDelta": {
                        "mode": "linear",
                        "points": _pitch_points(song, index),
                    },
                },
                "vocalModes": {},
                "pitchControls": [],
            },
            "mainRef": {
                "uuid": _uuid(),
                "groupID": group_uuid,
                "blickOffset": 0,
                "pitchOffset": 0,
                "isInstrumental": False,
                "dictionary": "",
                "voice": {},
                "database": {},
                "systemPitchDelta": {"mode": "linear", "points": []},
            },
        }],
        "renderConfig": {},
    }

    target = Path(path).with_suffix(".svp")
    atomic_write_text(target, json.dumps(project, ensure_ascii=False, indent=1))
    return target


FORMAT = Format(
    key="svp",
    label="Synthesizer V 工程",
    short="Synthesizer V",
    extension=".svp",
    filetype=("Synthesizer V 工程", "*.svp"),
    prefix="VocaloidTTS_SynthV",
    writer=write_svp,
)
