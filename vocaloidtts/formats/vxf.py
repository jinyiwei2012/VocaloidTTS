"""VX-β 工程（.vxf）：MIDI 2.0 UMP 包的二进制流。

文件结构::

    "SMF2CLIP" + PPQN(4) + 轨道

    轨道 = 轨道名包 + 开始标记 + 事件 + 结束标记

事件都是 UMP（Universal MIDI Packet）：一个 4 字节的 delta tick 头，后面跟
16 或 8 字节的包体。包体里的数值不是裸值，而是加了固定偏移的「魔术数」——
比如音符号要写成 ``1 + (note << 8) + (0x4090 << 16)``。这些偏移量来自
MIDI 2.0 的 UMP 分组约定，照抄 LibreSVIP 的 ``plugins/vxf/model.py``（MIT，
见 THIRD_PARTY_NOTICES.md）。

三处需要注意：

- **delta tick 是增量**，不是绝对时间。事件按绝对时间排序后再逐条差分。
- 歌词和元数据都按 **12 字节一段**切开，用 ``seq_stat`` 标记「单段 / 首段 /
  中段 / 末段」，不切的话长字符串会被截断。
- 歌词必须是 ASCII：中文歌词走 ``note.lyric``（拼音），不走汉字。

简化之处：只写一条唱轨；音高数据按 PIT 控制点采样，不做 200 Hz 插值
（我们的 PIT 本来就够密）。
"""
from __future__ import annotations

import json
from pathlib import Path

from ..atomicio import atomic_write_bytes
from ..prosody import Song
from .base import Format, pitch_samples, seconds

#: 文件里的 tick 分辨率（每四分音符）。
TICKS_PER_BEAT = 480

#: UMP 分组偏移量，照抄 MIDI 2.0 的约定。
BASE_DCTPQ = 0x30
BASE_DELTA_TICKS = 0x40
BASE_START_PITCH = 0x4090
BASE_END_PITCH = 0x4080

#: 元数据里音高的基准：6900 = MIDI 69（A4）的百分之一半音。
PITCH_BASE = 6900

#: 音高帧周期（秒）。只影响写进 JSON 的元信息。
PITCH_FRAME_SECONDS = 0.005

MAGIC = b"SMF2CLIP"


def _u32(value: int) -> bytes:
    return int(value).to_bytes(4, "big")


def _ppqn(value: int) -> bytes:
    return _u32(value + (BASE_DCTPQ << 16))


def _delta(value: int) -> bytes:
    return _u32(max(0, value) + (BASE_DELTA_TICKS << 16))


def _start_pitch(note: int) -> bytes:
    return _u32(1 + (note << 8) + (BASE_START_PITCH << 16))


def _end_pitch(note: int) -> bytes:
    return _u32(1 + (note << 8) + (BASE_END_PITCH << 16))


def _padded(text: str, size: int, encoding: str) -> bytes:
    data = text.encode(encoding, "replace")[:size]
    return data.ljust(size, b"\x00")


def _tempo(bpm: float) -> bytes:
    # 反比存法：120 BPM -> 14208605
    value = int(1705032600 / max(1.0, bpm))
    return b"\xd0\x10\x00\x00" + _u32(value) + b"\x00" * 8


def _time_signature(numerator: int, denominator: int) -> bytes:
    return (b"\xd0\x10\x00\x01" + bytes([numerator, denominator.bit_length() - 1])
            + b"\x08" + b"\x00" * 9)


def _lyric(seq_stat: int, seq_num: int | None, text: str) -> bytes:
    out = bytearray(b"\xd0")
    out.append(seq_stat)
    out += b"\x01\x50"
    if (seq_stat - 16) // 64 <= 1:
        out += int(seq_num or 0).to_bytes(2, "big")
        out += _padded(text, 10, "ascii")
    else:
        out += _padded(text, 12, "ascii")
    return bytes(out)


def _metadata(seq_stat: int, text: str) -> bytes:
    return b"\xd0" + bytes([seq_stat]) + b"\x01\x51" + _padded(text, 12, "utf-8")


def _note_on(note: int, seq: int) -> bytes:
    return _start_pitch(note) + b"\x7f\x00" + int(seq).to_bytes(2, "big")


def _note_off(note: int) -> bytes:
    return _end_pitch(note) + b"\x00\x00" + b"\x00\x00"


def _chunks(text: str, size: int = 12) -> list[tuple[int, str]]:
    """把长字符串切成若干段，返回 [(seq_stat, 片段)]。"""
    pieces = [text[index:index + size] for index in range(0, len(text), size)]
    if not pieces:
        pieces = [""]
    if len(pieces) == 1:
        return [(0x10, pieces[0])]
    result = [(0x50, pieces[0])]
    result.extend((0x90, piece) for piece in pieces[1:-1])
    result.append((0xD0, pieces[-1]))
    return result


def _title_parts(title: str) -> bytes:
    encoded = title.encode("utf-8")[:12 * 8]
    out = bytearray()
    for seq_stat, piece in _chunks(encoded.decode("utf-8", "ignore")):
        out += b"\xd0" + bytes([seq_stat]) + b"\x01\x03" + _padded(piece, 12, "utf-8")
    return bytes(out)


def _pitch_metadata(song: Song) -> str:
    """把 PIT 控制点转成 VX-β 的音高序列 JSON。"""
    points: list[dict] = []
    for note in song.notes:
        samples = pitch_samples(song, note, count=max(2, int(note.dur / 12)))
        for index, cents in enumerate(samples):
            tick = note.start + note.dur * index / len(samples)
            points.append({
                "position": int(seconds(song, tick) / PITCH_FRAME_SECONDS),
                "pitch": round(note.midi * 100 + cents - PITCH_BASE, 4),
                "applicable": True,
            })
    points.sort(key=lambda item: item["position"])
    payload = {
        "TimeBasedPitchSequence": {
            "timeFramePeriodSeconds": PITCH_FRAME_SECONDS,
            "numFramesOverallSequence": points[-1]["position"] if points else 0,
            "pitchSequence": points,
        },
    }
    return json.dumps(payload, separators=(",", ":"))


def build_file(song: Song, title: str = "VocaloidTTS") -> bytes:
    notes = [note for note in song.notes if note.dur > 0]
    if not notes:
        raise ValueError("没有可导出的音符")

    numerator = max(1, min(16, int(song.numerator)))
    denominator = int(song.denominator)
    if denominator not in (2, 4, 8, 16):
        denominator = 4

    # (绝对 tick, 包体)。包体不含 4 字节的时间头，写出去时再补。
    events: list[tuple[int, bytes]] = []
    for index, note in enumerate(notes):
        lyric = note.lyric if note.lyric.isascii() else "l-aa"
        for seq_stat, piece in _chunks(lyric, size=10):
            events.append((0, _lyric(seq_stat, index if seq_stat in (0x10, 0x50) else None,
                                     piece)))
        start = int(note.start)
        end = int(note.start + note.dur)
        events.append((start, _note_on(int(note.midi), index)))
        events.append((end, _note_off(int(note.midi))))

    for seq_stat, piece in _chunks(_pitch_metadata(song)):
        events.append((0, _metadata(seq_stat, piece)))

    events.append((0, _tempo(float(song.bpm))))
    events.append((0, _time_signature(numerator, denominator)))

    events.sort(key=lambda item: item[0])
    body = bytearray()
    previous = 0
    for tick, payload in events:
        body += _delta(tick - previous)
        body += payload
        previous = tick

    return (MAGIC + _ppqn(TICKS_PER_BEAT) + _title_parts(title or "VocaloidTTS")
            + b"\xf0\x20\x00\x00" + b"\x00" * 12
            + bytes(body)
            + b"\xf0\x21\x00\x00" + b"\x00" * 12)


def write_vxf(song: Song, path: str) -> Path:
    """把 Song 写成 VX-β 的 .vxf。"""
    target = Path(path).with_suffix(".vxf")
    atomic_write_bytes(target, build_file(song))
    return target


FORMAT = Format(
    key="vxf",
    label="VX-β 工程",
    short="VX-β",
    extension=".vxf",
    filetype=("VX-β 工程", "*.vxf"),
    prefix="VocaloidTTS_VXBeta",
    writer=write_vxf,
)
