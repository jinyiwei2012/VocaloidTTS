"""ASS 字幕（.ass，Advanced SubStation Alpha）：每句歌词一条 Dialogue。

切行规则和 .lrc / .srt 相同（见 :func:`vocaloidtts.formats.base.lyric_lines`）。
时间戳是 ``H:MM:SS.cc``，百分秒两位——这是 ASS 的规定，和 SubRip 的毫秒不同。

样式只写一条 ``Default``：居中、白字、黑边。字幕组常用的花哨样式不在这个
工具的职责范围内，用户在 Aegisub 里改就是了。
"""
from __future__ import annotations

from pathlib import Path

from ..atomicio import atomic_write_text
from ..prosody import Song
from .base import Format, lyric_lines, lyric_text, seconds

HEADER = """[Script Info]
Title: VocaloidTTS
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,64,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,3,1,2,40,40,48,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _stamp(total: float) -> str:
    centis = int(round(max(0.0, total) * 100))
    hours, centis = divmod(centis, 360_000)
    minutes, centis = divmod(centis, 6_000)
    secs, centis = divmod(centis, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def write_ass(song: Song, path: str) -> Path:
    """把 Song 写成 .ass。"""
    lines = lyric_lines(song)
    if not lines:
        raise ValueError("没有可导出的音符")

    body: list[str] = []
    for group in lines:
        start = seconds(song, group[0].start)
        end = seconds(song, group[-1].start + group[-1].dur)
        if end <= start:
            end = start + 0.2
        text = lyric_text(group).replace("\n", " ")
        body.append(
            f"Dialogue: 0,{_stamp(start)},{_stamp(end)},Default,,0,0,0,,{text}")

    target = Path(path).with_suffix(".ass")
    atomic_write_text(target, HEADER + "\n".join(body) + "\n")
    return target


FORMAT = Format(
    key="ass",
    label="ASS 字幕",
    short="ASS",
    extension=".ass",
    filetype=("ASS 字幕", "*.ass"),
    prefix="VocaloidTTS_ASS",
    writer=write_ass,
)
