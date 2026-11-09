"""袅袅虚拟歌手工程（.nn）：纯文本、按行排的格式。

文件长这样（每行一个音符，行首有一个空格）::

    120.0 4 4 4 19 0 0 0 0 0
    4
     你 ni 0 4 17 0 50 0 0 0 0 100,50,... 100,... 2

第二行是音符数，之后每行是：歌词、读音、起点、时长、音高、清澈度、力度、
滑音、颤音长度/深度/速率、力度包络、音高包络、音高灵敏度。

格式细节参考 LibreSVIP 的 ``libresvip/plugins/nn``（MIT，见
THIRD_PARTY_NOTICES.md），文法在它的 ``model.py`` 里用 Tatsu 写着，这里直接
按那个文法拼字符串。

几处约定：

- 版本 19 的时间单位是 60 tick（480 / 8）；版本 30 是 30 tick。这里写 19。
- ``key`` 是 **83 减去 MIDI**，又是反的音高轴。
- 音高包络是 100 个 0..100 的整数，50 是音符本身的音高，±50 对应
  ``pitch_bend_sensitivity`` 个半音。LibreSVIP 这里写的是
  ``50 + round(偏移 / pbs)``，量化到只剩 49/50/51 三个值，等于把曲线抹平了；
  我们按「±50 对应 ±pbs 个半音」的正确比例映射。
- 力度包络留中性（全 50），不猜它的语义。
"""
from __future__ import annotations

import math
from pathlib import Path

from ..atomicio import atomic_write_text
from ..prosody import Song
from .base import Format, lyric_for, pitch_samples

#: 版本 19 的时间单位：60 tick = 1 个单位。
TICKS_PER_UNIT = 60

#: 工程版本号。19 是老版本，时间单位 60 tick。
PROJECT_VERSION = 19

#: 音高/力度包络的点数。
ENVELOPE_POINTS = 100

#: 音高轴零点：key = 83 - MIDI。
KEY_ORIGIN = 83

#: 力度包络的中性值。
NEUTRAL_DYNAMICS = [50] * ENVELOPE_POINTS


def _points(values: list[int]) -> str:
    return f"{len(values)}," + ",".join(str(value) for value in values)


def _pitch(note, song: Song) -> tuple[list[int], int]:
    """返回 (100 点音高包络, 音高灵敏度)。灵敏度存的是上限减一。"""
    semitones = [value / 100.0 for value in pitch_samples(song, note, ENVELOPE_POINTS)]
    peak = max(abs(value) for value in semitones)
    pbs = min(math.ceil(peak), 12)
    if pbs <= 0:
        return [50] * ENVELOPE_POINTS, 0
    curve = [max(0, min(100, int(round(50 + value * 50.0 / pbs))))
             for value in semitones]
    return curve, pbs - 1


def build_text(song: Song) -> str:
    notes = [note for note in song.notes if note.dur > 0]
    if not notes:
        raise ValueError("没有可导出的音符")

    numerator = max(1, min(16, int(song.numerator)))
    denominator = int(song.denominator)
    if denominator not in (2, 4, 8, 16):
        denominator = 4
    bar_length = 1920 * numerator / denominator

    rows: list[str] = []
    last_end = 0
    for note in notes:
        start = int(note.start) // TICKS_PER_UNIT
        duration = max(1, int(note.dur) // TICKS_PER_UNIT)
        last_end = max(last_end, start + duration)
        curve, pbs = _pitch(note, song)
        rows.append(
            f" {lyric_for(note)} {note.lyric or lyric_for(note)} "
            f"{start} {duration} {KEY_ORIGIN - int(note.midi)} 0 50 0 0 0 0 "
            f"{_points(NEUTRAL_DYNAMICS)} {_points(curve)} {pbs}")

    bar_count = math.ceil(last_end * TICKS_PER_UNIT / bar_length)
    header = (f"{max(1.0, float(song.bpm))} {numerator} {denominator} "
              f"{bar_count} {PROJECT_VERSION} 0 0 0 0 0")
    return "\n".join([header, str(len(rows)), *rows]) + "\n"


def write_nn(song: Song, path: str) -> Path:
    """把 Song 写成袅袅的 .nn。"""
    target = Path(path).with_suffix(".nn")
    atomic_write_text(target, build_text(song))
    return target


FORMAT = Format(
    key="nn",
    label="袅袅虚拟歌手工程",
    short="袅袅",
    extension=".nn",
    filetype=("袅袅虚拟歌手工程", "*.nn"),
    prefix="VocaloidTTS_NiaoNiao",
    writer=write_nn,
)
