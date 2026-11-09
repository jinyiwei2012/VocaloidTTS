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


def comp_id(bank: "Voicebank") -> str:
    """VOCALOID 只认 16 字符的 compID。

    长度不对时编辑器不会报错，而是静默回退到默认歌手——用户会以为选错了库。
    与其导出一个找不到声库的文件，不如在这里说清楚。VSQX 和 VPR 都要过这一关。
    """
    bid = (bank.id or "").strip()
    if len(bid) != 16 or not bid.isascii():
        raise ValueError(
            f"声库「{bank.display}」的 compID 不是 16 位"
            f"（实际 {len(bid)} 位：{bid!r}）。"
            "导出的工程会找不到这个声库，请到声库面板重新扫描。")
    return bid


def seconds(song: Song, tick: float) -> float:
    """tick -> 秒。Song 只有一条速度线，所以不需要积分。"""
    resolution = int(getattr(song, "resolution", 480) or 480)
    bpm = max(1.0, float(song.bpm))
    return float(tick) * 60.0 / (bpm * resolution)


#: 切歌词行时认定的「停顿」长度：1/8 个四分音符。
#: 我们生成的音符之间要么紧挨着（0 tick），要么是标点带来的 200+ tick 停顿，
#: 所以这个阈值不会把词切开。
LINE_GAP = 60


def lyric_lines(song: Song, *, min_gap: int = LINE_GAP) -> list[list[Note]]:
    """把音符按停顿切成歌词行，供 .lrc / .srt / .ass 这类时间轴文件使用。"""
    notes = [note for note in song.notes if note.dur > 0]
    lines: list[list[Note]] = []
    current: list[Note] = []
    for index, note in enumerate(notes):
        current.append(note)
        last = index + 1 == len(notes)
        gap = 0 if last else notes[index + 1].start - (note.start + note.dur)
        if last or gap >= min_gap:
            lines.append(current)
            current = []
    return lines


def lyric_text(group: Iterable[Note]) -> str:
    """把一行的音符拼成可读文本：中文直接连写，拉丁字母之间补空格。"""
    parts: list[str] = []
    for note in group:
        text = lyric_for(note)
        parts.append(text)
        tail = text[-1:] or ""
        if tail.isascii() and tail.isalpha():
            parts.append(" ")
    return "".join(parts).strip()


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
