"""VocalSharp 工程（.vspx）：一份 XML。

结构是 ``<VSPX>`` 包一个 ``<Project>``，里面放采样率、分辨率、时长、速度、
拍号和若干轨道；每条唱轨挂一串 ``<Note>``。

格式细节参考 LibreSVIP 的 ``libresvip/plugins/vspx``（MIT，见
THIRD_PARTY_NOTICES.md），这里只保留**写**方向，手拼 XML（和 vsqx.py 一样的
做法），不引 xsdata 那套序列化框架。简化之处：

- 只写唱轨，不写音频轨；
- ``<Parameter>`` 留空，音高/表情曲线交给 VocalSharp 自己算；
- ``<Syllable>`` 留空（格式允许，由编辑器按歌词查字典）。

两个单位约定：

- ``<Resolution>`` 写 1920，但音符位置用的是 480 tick / 四分音符——这是
  LibreSVIP 的写法，说明 1920 是「一个 4/4 小节的 tick 数」而不是每拍的
  tick 数，两者正好差 4 倍。
- ``<pitch>`` 是音名（``C4``），不是 MIDI 数字；MIDI 60 = C4。
"""
from __future__ import annotations

import math
from pathlib import Path
from xml.sax.saxutils import escape

from ..atomicio import atomic_write_text
from ..prosody import Song
from .base import Format, lyric_for

#: 写进 <Resolution> 的值：一个 4/4 小节的 tick 数。
RESOLUTION = 1920

#: <Duration> 的对齐单位（LibreSVIP 的写法）。
DURATION_STEP = 30720

#: <Duration> 的最小值。
DURATION_FLOOR = 122880

#: 音名表。
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def _note_name(midi: int) -> str:
    midi = max(0, min(127, int(midi)))
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def _duration(song: Song) -> int:
    end = max((int(note.start) + int(note.dur) for note in song.notes), default=0)
    return math.ceil(max(end - DURATION_FLOOR, 0) / DURATION_STEP) * DURATION_STEP \
        + DURATION_FLOOR


def _note_xml(note) -> str:
    return (
        "\t\t\t<Note>\n"
        f"\t\t\t\t<pitch>{_note_name(note.midi)}</pitch>\n"
        f"\t\t\t\t<pos>{int(note.start)}</pos>\n"
        f"\t\t\t\t<duration>{max(1, int(note.dur))}</duration>\n"
        f"\t\t\t\t<lyric>{escape(lyric_for(note))}</lyric>\n"
        "\t\t\t\t<Syllable/>\n"
        "\t\t\t</Note>\n"
    )


def build_xml(song: Song, title: str = "VocaloidTTS") -> str:
    notes = [note for note in song.notes if note.dur > 0]
    if not notes:
        raise ValueError("没有可导出的音符")

    numerator = max(1, min(16, int(song.numerator)))
    denominator = int(song.denominator)
    if denominator not in (2, 4, 8, 16):
        denominator = 4

    body = "".join(_note_xml(note) for note in notes)
    return (
        '<?xml version="1.0" encoding="utf-8" standalone="no"?>\n'
        "<VSPX>\n"
        "\t<Version>Beta0.0.0</Version>\n"
        "\t<Project>\n"
        "\t\t<SamplesPerSec>44100</SamplesPerSec>\n"
        f"\t\t<Resolution>{RESOLUTION}</Resolution>\n"
        f"\t\t<Duration>{_duration(song)}</Duration>\n"
        "\t\t<DefaultTrill>\n"
        "\t\t\t<pos>0.25</pos>\n"
        "\t\t\t<amplitude>0</amplitude>\n"
        "\t\t\t<frequency>5.5</frequency>\n"
        "\t\t\t<phase>0</phase>\n"
        "\t\t</DefaultTrill>\n"
        "\t\t<Tempo>\n"
        "\t\t\t<pos>0</pos>\n"
        f"\t\t\t<bpm>{max(1.0, float(song.bpm))}</bpm>\n"
        "\t\t</Tempo>\n"
        "\t\t<Beat>\n"
        "\t\t\t<barIndex>0</barIndex>\n"
        f"\t\t\t<beatPerBar>{numerator}</beatPerBar>\n"
        f"\t\t\t<barDivide>{denominator}</barDivide>\n"
        "\t\t</Beat>\n"
        "\t\t<NoteTrack>\n"
        f"\t\t\t<Name>{escape(title or 'VocaloidTTS')}</Name>\n"
        "\t\t\t<Pan>0</Pan>\n"
        "\t\t\t<Gain>0</Gain>\n"
        "\t\t\t<IsMute>False</IsMute>\n"
        "\t\t\t<IsSolo>False</IsSolo>\n"
        "\t\t\t<Singer>神秘歌手</Singer>\n"
        "\t\t\t<LSD>神秘字典</LSD>\n"
        "\t\t\t<DefaultParameter>\n"
        "\t\t\t\t<dyn>128</dyn>\n"
        "\t\t\t\t<str>128</str>\n"
        "\t\t\t\t<bri>128</bri>\n"
        "\t\t\t\t<voc>255</voc>\n"
        "\t\t\t\t<bre>128</bre>\n"
        "\t\t\t\t<gen>128</gen>\n"
        "\t\t\t\t<gwl>0</gwl>\n"
        "\t\t\t\t<xsy>0</xsy>\n"
        "\t\t\t</DefaultParameter>\n"
        "\t\t\t<por>0.07</por>\n"
        f"{body}"
        "\t\t\t<Parameter/>\n"
        "\t\t</NoteTrack>\n"
        "\t</Project>\n"
        "</VSPX>\n"
    )


def write_vspx(song: Song, path: str) -> Path:
    """把 Song 写成 VocalSharp 的 .vspx。"""
    target = Path(path).with_suffix(".vspx")
    atomic_write_text(target, build_xml(song))
    return target


FORMAT = Format(
    key="vspx",
    label="VocalSharp 工程",
    short="VocalSharp",
    extension=".vspx",
    filetype=("VocalSharp 工程", "*.vspx"),
    prefix="VocaloidTTS_VocalSharp",
    writer=write_vspx,
)
