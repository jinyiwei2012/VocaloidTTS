"""SubRip 字幕（.srt）：每句歌词一条字幕。

切行规则和 .lrc 相同（见 :func:`vocaloidtts.formats.base.lyric_lines`）。
时间戳是 ``HH:MM:SS,mmm``，逗号是 SubRip 的规定，不能写成点。
"""
from __future__ import annotations

from pathlib import Path

from ..atomicio import atomic_write_text
from ..prosody import Song
from .base import Format, lyric_lines, lyric_text, seconds


def _stamp(total: float) -> str:
    millis = int(round(max(0.0, total) * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(song: Song, path: str) -> Path:
    """把 Song 写成 .srt。"""
    lines = lyric_lines(song)
    if not lines:
        raise ValueError("没有可导出的音符")

    blocks: list[str] = []
    for index, group in enumerate(lines, start=1):
        start = seconds(song, group[0].start)
        end = seconds(song, group[-1].start + group[-1].dur)
        if end <= start:
            end = start + 0.2
        blocks.append(
            f"{index}\n{_stamp(start)} --> {_stamp(end)}\n{lyric_text(group)}\n")

    target = Path(path).with_suffix(".srt")
    atomic_write_text(target, "\n".join(blocks))
    return target


FORMAT = Format(
    key="srt",
    label="SRT 字幕",
    short="SRT",
    extension=".srt",
    filetype=("SubRip 字幕", "*.srt"),
    prefix="VocaloidTTS_SRT",
    writer=write_srt,
)
