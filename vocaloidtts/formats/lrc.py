"""LRC 歌词文件（.lrc）：带时间轴的纯文本歌词。

和工程文件不同，这里不关心音高和参数，只要「什么时候唱哪句」。切行的规则
在 :func:`vocaloidtts.formats.base.lyric_lines`：我们生成的音符之间要么紧挨着，
要么是标点带来的停顿，所以按停顿切行等于按标点切句。

时间戳用 ``[mm:ss.xx]``，分钟不截断到 59——超过一小时的长篇按 LRC 的约定
继续往上加（播放器普遍能读）。
"""
from __future__ import annotations

from pathlib import Path

from ..atomicio import atomic_write_text
from ..prosody import Song
from .base import Format, lyric_lines, lyric_text, seconds


def _stamp(song: Song, tick: float) -> str:
    total = max(0.0, seconds(song, tick))
    minutes = int(total // 60)
    rest = total - minutes * 60
    return f"{minutes:02d}:{rest:05.2f}"


def write_lrc(song: Song, path: str, title: str = "VocaloidTTS") -> Path:
    """把 Song 写成 .lrc。"""
    lines = lyric_lines(song)
    if not lines:
        raise ValueError("没有可导出的音符")

    out: list[str] = []
    if title:
        out.append(f"[ti:{title}]")
    out.append("[by:VocaloidTTS]")
    for group in lines:
        out.append(f"[{_stamp(song, group[0].start)}]{lyric_text(group)}")

    target = Path(path).with_suffix(".lrc")
    atomic_write_text(target, "\n".join(out) + "\n")
    return target


FORMAT = Format(
    key="lrc",
    label="LRC 歌词",
    short="LRC",
    extension=".lrc",
    filetype=("LRC 歌词", "*.lrc"),
    prefix="VocaloidTTS_LRC",
    writer=write_lrc,
)
