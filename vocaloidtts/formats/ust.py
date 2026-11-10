"""UTAU 序列（.ust）：INI 风格的纯文本。

结构很直白::

    [#VERSION]
    UST Version=1.0
    Charset=UTF-8
    [#SETTING]
    Tempo=120.00
    Tracks=1
    Project=...
    [#0000]
    Length=266
    Lyric=ni
    NoteNum=66
    ...
    [#TRACKEND]

``[#nnnn]`` 是每个音符的小节名，``Length`` 用 480 tick / 四分音符（和我们的
内部 tick 一致，不需要换算），``NoteNum`` 是 MIDI 音符号。

格式细节参考 LibreSVIP 的 ``libresvip/plugins/ust``（MIT，见
THIRD_PARTY_NOTICES.md）。这里只保留**写**方向，并且**只写音符层**：

- 不写音高包络（``PBS`` / ``PBY`` / ``PBM``）——UTAU 的音高编辑有 mode1/mode2
  两套算法，写错比不写更糟，留给用户在 UTAU 里拉；
- 不写颤音（``VBR``）和包络（``Envelope``）；
- 歌词写拼音。UTAU 的中文声库认拼音，日文声库认罗马字，拼音两边都不算离谱。

编码用 UTF-8 并显式写 ``Charset=UTF-8``；老 UTAU 默认 Shift-JIS，现代版本和
OpenUtau 都读 UTF-8。
"""
from __future__ import annotations

from pathlib import Path

from ..atomicio import atomic_write_text
from ..prosody import Song
from .base import Format, lyric_for

#: UST 的时间单位：480 tick = 一个四分音符。
TICKS_PER_QUARTER = 480

#: 写进 [#VERSION] 的版本号。
UST_VERSION = "1.0"


def build_text(song: Song, title: str = "VocaloidTTS") -> str:
    notes = [note for note in song.notes if note.dur > 0]
    if not notes:
        raise ValueError("没有可导出的音符")

    lines = [
        "[#VERSION]",
        f"UST Version={UST_VERSION}",
        "Charset=UTF-8",
        "[#SETTING]",
        f"Tempo={max(1.0, float(song.bpm)):.2f}",
        "Tracks=1",
        f"Project={title or 'VocaloidTTS'}",
    ]
    for index, note in enumerate(notes):
        lines.extend([
            f"[#{index:04d}]",
            f"Length={max(1, int(note.dur))}",
            f"Lyric={note.lyric or lyric_for(note)}",
            f"NoteNum={max(0, min(127, int(note.midi)))}",
        ])
    lines.append("[#TRACKEND]")
    return "\n".join(lines) + "\n"


def write_ust(song: Song, path: str) -> Path:
    """把 Song 写成 UTAU 的 .ust。"""
    target = Path(path).with_suffix(".ust")
    atomic_write_text(target, build_text(song))
    return target


FORMAT = Format(
    key="ust",
    label="UTAU 序列",
    short="UST",
    extension=".ust",
    filetype=("UTAU 序列", "*.ust"),
    prefix="VocaloidTTS_UTAU",
    writer=write_ust,
)
