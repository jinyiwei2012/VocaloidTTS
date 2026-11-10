"""各导出格式共享的工具与格式描述。

``Format`` 是「一个导出格式」的完整描述：标签、扩展名、写出函数。
加一个格式 = 在 ``formats/`` 下加一个模块、导出一个 ``FORMAT``，
再在 ``formats/__init__.py`` 的注册表里加一行——不再有 if/elif 调度。
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, replace
from pathlib import Path
import struct
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


def pitch_samples(song: Song, note: Note, count: int = 500) -> list[float]:
    """把音符内的 PIT 曲线等距采样成 ``count`` 个点，单位是音分。

    Y77 和 AISingers 都把整条音高曲线塞进音符里（固定点数采样），一个用半音、
    一个用十分之一半音，所以这里统一吐音分，让各格式自己换算。
    """
    points = [(float(t), float(c)) for t, c in pit_cents(song, note)]
    if not points:
        return [0.0] * count
    ticks = [point[0] for point in points]
    duration = max(1.0, float(note.dur))
    samples: list[float] = []
    for index in range(count):
        target = duration * index / count
        position = bisect_right(ticks, target) - 1
        if position < 0:
            samples.append(points[0][1])
            continue
        if position >= len(points) - 1:
            samples.append(points[-1][1])
            continue
        left_tick, left_value = points[position]
        right_tick, right_value = points[position + 1]
        span = right_tick - left_tick
        if span <= 0:
            samples.append(right_value)
            continue
        ratio = (target - left_tick) / span
        samples.append(left_value + (right_value - left_value) * ratio)
    return samples


def db_value(vsqx: int) -> float:
    """VSQX DYN 0..127 -> a mild OpenUTAU dyn curve (dB-ish)."""
    return max(-24.0, min(24.0, (float(vsqx) - 64.0) * 0.2))


#: zstd 单个 block 的最大原始字节数。
ZSTD_BLOCK_MAX = 1 << 17


def zstd_store(data: bytes) -> bytes:
    """把 ``data`` 包成一个 zstd 帧，块类型全部用 Raw（即不压缩）。

    zstd 的帧格式允许 Raw 块，任何符合规范的解码器都读得出来——Python 3.14
    的 ``compression.zstd`` 自己压缩 5 个字节时也是这么干的。这样导出就完全
    不依赖 ``zstandard`` / ``pyzstd`` 这类二进制扩展，代价是文件不压缩。

    ACE Studio（.acep）和 DiffScope（.dspx）都用 zstd 装工程，所以放在这里。

    帧结构（RFC 8878）：
        magic ``28 b5 2f fd`` + 帧头描述符 + 4 字节内容长度 + 若干块
    帧头描述符 ``0xa0``：FCS 字段 4 字节（bit7-6 = 10）、Single_Segment
    （bit5 = 1），因此没有 Window_Descriptor，窗口大小等于内容长度。
    """
    out = bytearray(b"\x28\xb5\x2f\xfd")
    out.append(0xA0)
    out += len(data).to_bytes(4, "little")
    pos = 0
    while pos < len(data):
        chunk = data[pos:pos + ZSTD_BLOCK_MAX]
        pos += len(chunk)
        last = 1 if pos >= len(data) else 0
        # 块头 3 字节小端：bit0 = 最后一块，bit1-2 = 块类型（0 = Raw），
        # bit3-23 = 块长度。
        out += ((len(chunk) << 3) | last).to_bytes(3, "little")
        out += chunk
    if not data:
        out += (1).to_bytes(3, "little")  # 空内容也要有一个「最后一块」
    return bytes(out)


def _cbor_head(major: int, value: int) -> bytes:
    if value < 24:
        return bytes([(major << 5) | value])
    if value < 0x100:
        return bytes([(major << 5) | 24, value])
    if value < 0x10000:
        return bytes([(major << 5) | 25]) + value.to_bytes(2, "big")
    if value < 0x100000000:
        return bytes([(major << 5) | 26]) + value.to_bytes(4, "big")
    return bytes([(major << 5) | 27]) + value.to_bytes(8, "big")


def cbor_dumps(value: object) -> bytes:
    """最小 CBOR 编码器（RFC 8949），只覆盖 JSON 能表达的那几种类型。

    TuneLab 的新工程格式（.tlpx）是 CBOR 而不是 JSON。为了不引 ``cbor2``
    这个二进制依赖，这里自己编——只需要 map / array / text / int / float /
    bool / null，一律用定长编码，不追求紧凑。

    ``bool`` 必须在 ``int`` 之前判断，因为 Python 里 ``True`` 是 ``int`` 的子类。
    """
    if value is None:
        return b"\xf6"
    if value is True:
        return b"\xf5"
    if value is False:
        return b"\xf4"
    if isinstance(value, int):
        return _cbor_head(0, value) if value >= 0 else _cbor_head(1, -1 - value)
    if isinstance(value, float):
        return b"\xfb" + struct.pack(">d", value)
    if isinstance(value, str):
        data = value.encode("utf-8")
        return _cbor_head(3, len(data)) + data
    if isinstance(value, (bytes, bytearray)):
        return _cbor_head(2, len(value)) + bytes(value)
    if isinstance(value, (list, tuple)):
        return _cbor_head(4, len(value)) + b"".join(cbor_dumps(item) for item in value)
    if isinstance(value, dict):
        out = bytearray(_cbor_head(5, len(value)))
        for key, item in value.items():
            out += cbor_dumps(key)
            out += cbor_dumps(item)
        return bytes(out)
    raise TypeError(f"CBOR 编码器不认识这个类型：{type(value).__name__}")


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


#: 绝大多数工程格式假定的固定时基：480 tick = 一个四分音符。
TARGET_TICKS_PER_QUARTER = 480


def resample(song: Song, per_quarter: int = TARGET_TICKS_PER_QUARTER) -> Song:
    """把 Song 的时间轴换算到目标时基（默认 480 tick / 四分音符）。

    ``compose(resolution=...)`` 允许内部 tick 用 96..1920 之间的别的分辨率。
    凡是「文件里不写分辨率、位置一律按固定 480 tick 解释」的格式，写之前都要
    过这一层——否则 ``resolution=960`` 导出的时间轴会整体翻倍，而且像 VFP 这种
    同时写 tick 和秒的格式，两套字段会互相矛盾。

    ``seconds()`` 也读 ``Song.resolution``，所以这里连 resolution 一起改成目标
    值，保证 tick 与秒两种字段自洽。``duration_s`` 本来就是秒，不换算。

    已经是目标分辨率时原样返回，不做任何拷贝——正常路径零开销。
    """
    source = int(getattr(song, "resolution", per_quarter) or per_quarter)
    if source == per_quarter:
        return song
    ratio = per_quarter / source

    def scale(value: float) -> int:
        return int(round(value * ratio))

    return replace(
        song,
        notes=[replace(note,
                       start=scale(note.start),
                       dur=max(1, scale(note.dur)))
               for note in song.notes],
        controls={name: [(scale(t), value) for t, value in points]
                  for name, points in song.controls.items()},
        total_ticks=scale(song.total_ticks),
        part_start=scale(song.part_start),
        resolution=per_quarter,
    )


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
