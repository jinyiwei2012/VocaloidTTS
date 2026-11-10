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

UST 是**顺序**格式：它只写每个音符的 ``Length``，不写 ``start``。所以音符之间
的停顿必须显式写成 ``Lyric=R`` 的休止音符，否则整首歌会被压缩成连唱——标点带来
的那一拍停顿会凭空消失，后面的音全部提前。

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

#: 休止音符的歌词。UTAU 用 ``R`` 表示不发声的一拍。
REST_LYRIC = "R"

#: 休止音符的音高。UST 里必须给一个 NoteNum，惯例用中央 C。
REST_MIDI = 60


def _entries(notes) -> list[tuple[int, str, int]]:
    """把音符序列展开成 UST 的连续条目，空隙用休止音符补上。

    UST 没有 ``start`` 字段，时间轴由各条目的 ``Length`` 首尾相接累加而成，
    所以这里必须自己把停顿补成 ``R``。返回 ``(length, lyric, midi)``。
    """
    out: list[tuple[int, str, int]] = []
    cursor = 0
    for note in notes:
        start = max(0, int(note.start))
        if start > cursor:
            out.append((start - cursor, REST_LYRIC, REST_MIDI))
            cursor = start
        length = max(1, int(note.dur))
        out.append((length,
                    note.lyric or lyric_for(note),
                    max(0, min(127, int(note.midi)))))
        cursor = max(cursor, start + length)
    return out


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
    for index, (length, lyric, midi) in enumerate(_entries(notes)):
        lines.extend([
            f"[#{index:04d}]",
            f"Length={length}",
            f"Lyric={lyric}",
            f"NoteNum={midi}",
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
