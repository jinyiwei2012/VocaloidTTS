"""各导出格式共享的工具与格式描述。

``Format`` 是「一个导出格式」的完整描述：标签、扩展名、写出函数。
加一个格式 = 在 ``formats/`` 下加一个模块、导出一个 ``FORMAT``，
再在 ``formats/__init__.py`` 的注册表里加一行——不再有 if/elif 调度。
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable

from ..prosody import Note, Song

if TYPE_CHECKING:  # pragma: no cover - 只为类型检查，运行时不需要
    from ..voicebank import Voicebank


def has_han(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text or "")


def lyric_for(note: Note) -> str:
    """One lyric decision shared by every exporter.

    Chinese input keeps the original character; pinyin input (no Han) keeps the
    pinyin syllable, so a pinyin project does not turn every note into 啦.
    """
    text = getattr(note.syl, "text", "") or ""
    if has_han(text):
        return text
    return note.lyric or text or "啦"


def pronunciation_for(note: Note) -> str:
    return note.lyric or getattr(note.syl, "phonemes", "") or "a"


class PitchIndex:
    """A per-export time index, preserving the source order within each note."""

    def __init__(self, points: Iterable[tuple[int, int]]):
        self.points = list(points)
        self.order = sorted(range(len(self.points)),
                            key=lambda i: self.points[i][0])
        self.ticks = [self.points[i][0] for i in self.order]

    def between(self, start: int, end: int) -> Iterable[tuple[int, int]]:
        left = bisect_left(self.ticks, start)
        right = bisect_right(self.ticks, end)
        # 按 tick 升序返回。以前这里按「原始下标」排序，等于还原成源顺序；
        # 一旦 controls["P"] 不是升序（测试和手工构造都会这样），下游的
        # SVIP pointList 和 USTX 曲线就会拿到回退的 x，y 绑到错误的时刻。
        return (self.points[self.order[i]] for i in range(left, right))


def pit_cents(song: Song, note: Note, *,
              pitch_index: PitchIndex | None = None) -> list[tuple[int, float]]:
    """Return note-relative pitch points as (tick, cents)."""
    if pitch_index is None:
        pitch_index = PitchIndex(song.controls.get("P", []))
    pts: list[tuple[int, float]] = []
    for t, v in pitch_index.between(note.start, note.start + note.dur):
        semis = float(v) * song.options.pbs / 8192.0
        pts.append((int(t - note.start), semis * 100.0))
    if not pts:
        pts = [(0, 0.0), (max(1, note.dur), 0.0)]
    if pts[0][0] > 0:
        pts.insert(0, (0, pts[0][1]))
    if pts[-1][0] < note.dur:
        pts.append((max(1, note.dur), pts[-1][1]))
    return pts


def curve_values(song: Song, cid: str) -> list[tuple[int, int]]:
    return sorted(song.controls.get(cid, []), key=lambda p: p[0])


def db_value(vsqx: int) -> float:
    """VSQX DYN 0..127 -> a mild OpenUTAU dyn curve (dB-ish)."""
    return max(-24.0, min(24.0, (float(vsqx) - 64.0) * 0.2))


@dataclass(frozen=True)
class Format:
    """一个导出格式的完整描述。

    ``writer`` 的签名分两种：需要声库的格式收 ``voicebank`` 和 ``title``，
    其余的只收 ``(song, path)``。由 :meth:`write` 统一分发，调用方不需要
    知道每种格式的参数差异。
    """

    key: str
    label: str
    short: str
    extension: str
    filetype: tuple[str, str]
    prefix: str
    writer: Callable[..., Path]
    needs_voicebank: bool = False

    def write(self, song: Song, path: str | Path, *,
              voicebank: "Voicebank | None" = None,
              title: str = "VocaloidTTS") -> Path:
        if self.needs_voicebank:
            if voicebank is None:
                raise ValueError(f"{self.label} 需要先选一个声库")
            return self.writer(song, path, voicebank=voicebank, title=title)
        return self.writer(song, path)

    def __getitem__(self, name: str):
        """兼容旧的 ``meta["short"]`` 写法，让调用点不必一次性全改。"""
        return getattr(self, name)
