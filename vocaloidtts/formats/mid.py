"""标准 MIDI 文件（.mid）：只带音符、歌词和速度。

MIDI 不承载音素，也不适合表达逐音节的 PIT 曲线，所以这里刻意保持最小：
一个格式 0 的单轨文件，音符 + 歌词 + 速度/拍号。它存在的意义是「能丢进
任何 DAW」，而不是替代 VSQX。

歌词写拼音而不是汉字：MIDI 的 lyric 事件没有编码声明，很多 DAW 对 UTF-8
的支持不一致，ASCII 的拼音最保险。
"""
from __future__ import annotations

from pathlib import Path

from ..atomicio import atomic_write_bytes
from ..prosody import Song
from .base import Format, lyric_for, resample

#: MIDI 的固定时基：480 tick = 1 个四分音符。
DIVISION = 480


def vlq(value: int) -> bytes:
    """MIDI 的可变长度量（variable-length quantity）。"""
    value = max(0, int(value))
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))


def meta_event(kind: int, payload: bytes) -> bytes:
    return b"\xff" + bytes([kind]) + vlq(len(payload)) + payload


def chunk(tag: bytes, body: bytes) -> bytes:
    return tag + len(body).to_bytes(4, "big") + body


def _lyric_text(note) -> str:
    """歌词取拼音：MIDI 的 lyric 事件没有编码声明，ASCII 最稳。"""
    return (note.lyric or lyric_for(note) or "a").strip()


def write_mid(song: Song, path: str) -> Path:
    song = resample(song)
    if not song.notes:
        raise ValueError("没有可导出的音符")

    bpm = max(1.0, float(song.bpm))
    micros = int(round(60_000_000 / bpm))
    numerator = max(1, min(16, int(song.numerator)))
    denominator = int(song.denominator)
    if denominator not in (2, 4, 8, 16):
        denominator = 4
    den_pow = {2: 1, 4: 2, 8: 3, 16: 4}[denominator]

    # (绝对 tick, 同一 tick 内的顺序, 事件字节)
    # 顺序：note-off 先于 meta，meta 先于 note-on，避免同 tick 的音被截断。
    raw: list[tuple[int, int, bytes]] = [
        (0, 1, meta_event(0x51, micros.to_bytes(3, "big"))),
        (0, 1, meta_event(0x58, bytes([numerator, den_pow, 24, 8]))),
        (0, 1, meta_event(0x03, "VocaloidTTS".encode("utf-8"))),
    ]
    for note in song.notes:
        start = max(0, int(note.start))
        end = start + max(1, int(note.dur))
        text = _lyric_text(note).encode("ascii", "replace")
        raw.append((start, 1, meta_event(0x05, text)))
        raw.append((start, 2, bytes([0x90, max(0, min(127, int(note.midi))),
                                     max(1, min(127, int(note.velocity)))])))
        raw.append((end, 0, bytes([0x80, max(0, min(127, int(note.midi))), 0])))
    raw.sort(key=lambda item: (item[0], item[1]))

    body = bytearray()
    last = 0
    for tick, _order, data in raw:
        body += vlq(tick - last)
        body += data
        last = tick
    body += vlq(0) + meta_event(0x2F, b"")

    data = chunk(b"MThd", (0).to_bytes(2, "big") + (1).to_bytes(2, "big")
                  + DIVISION.to_bytes(2, "big")) + chunk(b"MTrk", bytes(body))
    target = Path(path).with_suffix(".mid")
    atomic_write_bytes(target, data)
    return target


FORMAT = Format(
    key="mid",
    label="标准 MIDI",
    short="MIDI",
    extension=".mid",
    filetype=("MIDI 文件", "*.mid"),
    prefix="VocaloidTTS_MIDI",
    writer=write_mid,
)
