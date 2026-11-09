"""Synthesizer V Studio 2 工程（.s5p）。

SynthV 换了一代工程格式：Studio 1 用 ``.svp``，Studio 2 改用 ``.s5p``。
两者内容高度相似（都是 JSON、都用 blick 计时、都有 meter/tempo/tracks），
但字段名和结构不一样，所以各写一个模块，不共用序列化代码。

格式细节参考 LibreSVIP 的 ``libresvip/plugins/s5p``（MIT，见
THIRD_PARTY_NOTICES.md），这里只保留**写**方向，并做了三处简化：

- 单轨，不写 ``instrumental`` 音频轨（留空文件名）；
- 参数曲线留空——``pitchDelta`` 存的是「相对 SynthV 自己算的基础音高的偏移」，
  要复现得先实现它的 pitch simulator，收益不抵成本；
- 音符的可选字段（``dF0Vbr`` / ``tF0Left`` / ``tSylOnset`` …）一律留 null，
  由编辑器按 ``dbDefaults`` 的默认值补。

时间单位：blicks，1 个四分音符 = 1,470,000 blick。我们的内部 tick 是 480/四分
音符，所以 1 tick = 1,470,000 blick。SynthV 没有 resolution 字段，基准是写死的，
``song.resolution`` 不是 480 时按比例换算。
"""
from __future__ import annotations

import json
from pathlib import Path

from ..atomicio import atomic_write_text
from ..prosody import Song
from .base import Format, lyric_for
from .svp import BLICK_PER_TICK

#: .s5p 的工程版本号，7 对应 SynthV Studio 2。
PROJECT_VERSION = 7

#: 参数曲线的采样间隔：3.75 个四分音符，和 LibreSVIP 一致。
PARAM_INTERVAL = round(BLICK_PER_TICK * 3.75)

#: 声库默认参数，缺省值照抄 SynthV 新建工程的 dbDefaults。
DB_DEFAULTS = {
    "lyric": "la",
    "breathiness": 0.0,
    "gender": 0.0,
    "tension": 0.0,
    "dF0Vbr": 0.025,
    "pF0Vbr": 0.0,
    "tF0VbrLeft": 0.15,
    "tF0VbrRight": 0.15,
    "tF0VbrStart": 0.25,
    "fF0Vbr": 5.5,
    "tF0Left": 0.0,
    "tF0Right": 0.0,
    "dF0Left": 0.0,
    "dF0Right": 0.0,
    "dF0Jitter": 1.0,
}

#: 每个音符都要出现、但我们可以留 null 的可选字段。
NOTE_OPTIONAL_FIELDS = (
    "dF0Vbr", "pF0Vbr", "tF0VbrLeft", "tF0VbrRight", "tF0VbrStart", "fF0Vbr",
    "tF0Left", "tF0Right", "dF0Left", "dF0Right", "dF0Jitter", "tF0Offset",
    "tNoteOffset", "tSylOnset", "tSylCoda", "wSylNucleus", "sublib",
)


def _blick(song: Song, ticks: float) -> int:
    """内部 tick → blick。"""
    resolution = int(getattr(song, "resolution", 480) or 480)
    if resolution == 480:
        return int(round(ticks * BLICK_PER_TICK))
    return int(round(ticks * BLICK_PER_TICK * 480 / resolution))


def _note(note, song: Song) -> dict:
    data = {
        "lyric": lyric_for(note),
        "onset": _blick(song, note.start),
        "duration": max(1, _blick(song, note.dur)),
        "comment": "",
        "pitch": max(0, min(127, int(note.midi))),
    }
    data.update({name: None for name in NOTE_OPTIONAL_FIELDS})
    return data


def build_project(song: Song) -> dict:
    """把 Song 转成 .s5p 的工程字典。"""
    notes = [n for n in song.notes if n.dur > 0]
    if not notes:
        raise ValueError("没有可导出的音符")

    numerator = max(1, min(16, int(song.numerator)))
    denominator = int(song.denominator)
    if denominator not in (2, 4, 8, 16):
        denominator = 4

    track = {
        "name": "VocaloidTTS",
        "dbName": "",
        "color": "15e879",
        "displayOrder": 0,
        "dbDefaults": dict(DB_DEFAULTS),
        "notes": [_note(n, song) for n in notes],
        "gsEvents": None,
        "mixer": {
            "gainDecibel": 0.0,
            "pan": 0.0,
            "muted": False,
            "solo": False,
            "engineOn": True,
            "display": True,
        },
        "parameters": {
            "interval": PARAM_INTERVAL,
            "pitchDelta": [],
            "vibratoEnv": [],
            "loudness": [],
            "tension": [],
            "breathiness": [],
            "voicing": [],
            "gender": [],
        },
    }

    return {
        "version": PROJECT_VERSION,
        "meter": [{"measure": 0, "beatPerMeasure": numerator,
                   "beatGranularity": denominator}],
        "tempo": [{"position": 0, "beatPerMinute": max(1.0, float(song.bpm))}],
        "tracks": [track],
        "instrumental": {"filename": "", "offset": 0.0},
        "mixer": {
            "gainInstrumentalDecibel": 0.0,
            "gainVocalMasterDecibel": 0.0,
            "instrumentalMuted": False,
            "vocalMasterMuted": False,
        },
    }


def write_s5p(song: Song, path: str) -> Path:
    """把 Song 写成 Synthesizer V Studio 2 的 .s5p。"""
    project = build_project(song)
    target = Path(path).with_suffix(".s5p")
    atomic_write_text(target, json.dumps(project, ensure_ascii=False, indent=1))
    return target


FORMAT = Format(
    key="s5p",
    label="Synthesizer V 2 工程",
    short="SynthV 2",
    extension=".s5p",
    filetype=("Synthesizer V 2 工程", "*.s5p"),
    prefix="VocaloidTTS_SynthV2",
    writer=write_s5p,
)
