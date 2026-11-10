"""Muta 工程（.mtp）：二进制，小端，字符串用 UTF-16LE。

布局（照 LibreSVIP 的 ``plugins/mtp/model.py``，MIT，见
THIRD_PARTY_NOTICES.md）::

    u32 文件版本
    <数组> 速度
    <数组> 拍号
    <数组> 轨道
    "\\n"

数组的写法是「``\\n`` + u32 元素个数」，之后每个元素前面再补一个 ``\\n``；
这一层在结构定义里叫 ``muta_prefixed_array``，容易漏掉。

三处容易写错：

- **字符串是 UTF-16LE**：轨道名 12 字节、歌手名 258 个 u16、音素 16 字节。
  用 ASCII 写会得到半个字宽的乱码。
- **音高轴是反的**：``key = 139 - MIDI``。
- **参数区的字段顺序和构造顺序不一样**。生成器里按
  unknown / pitch_range / pitch_data / volume_data 赋值，但结构体里
  volume_data 排在 pitch_data 前面——按关键字赋值时看不出来，按位置拼字节
  就会错位。

简化：只写唱轨；参数区只填 ``pitch_data``，其余留空数组。
"""
from __future__ import annotations

from pathlib import Path

from ..atomicio import atomic_write_bytes
from ..prosody import Song
from .base import Format, pitch_samples

#: 文件版本号。
FILE_VERSION = 101

#: 轨道类型：1 说话 / 2 唱歌 / 3 音频。
TRACK_TYPE_SONG = 2

#: 音高轴零点：key = 139 - MIDI。
KEY_ORIGIN = 139

#: 音高值的基准偏移（百分之一半音）。
PITCH_OFFSET = 1200

#: 参数区的八个数组，**顺序就是二进制顺序**。
PARAM_SLOTS = (
    "unknown_param",
    "pitch_range",
    "volume_data",
    "pitch_data",
    "vibrato_amplitude_range",
    "vibrato_amplitude_data",
    "vibrato_frequency_range",
    "vibrato_frequency_data",
)


def _u32(value: int) -> bytes:
    return int(value).to_bytes(4, "little")


def _i32(value: int) -> bytes:
    return int(value).to_bytes(4, "little", signed=True)


def _utf16(text: str, size: int) -> bytes:
    return text.encode("utf-16-le")[:size].ljust(size, b"\x00")


def _array(items: list[bytes]) -> bytes:
    out = bytearray(b"\n")
    out += _u32(len(items))
    for item in items:
        out += b"\n"
        out += item
    return bytes(out)


def _points(points: list[tuple[int, int]]) -> bytes:
    return _array([_i32(time) + _i32(value) for time, value in points])


def _pitch_points(song: Song) -> list[tuple[int, int]]:
    """PIT 控制点 -> Muta 的 (time, value)，value 是绝对音高减 1200。"""
    points: list[tuple[int, int]] = []
    for note in song.notes:
        for index, cents in enumerate(pitch_samples(song, note, count=64)):
            tick = note.start + note.dur * index / 64
            points.append((int(tick),
                           int(round(note.midi * 100 + cents - PITCH_OFFSET))))
    points.sort()
    return points


def _note(note) -> bytes:
    lyric = [ord(char) for char in (note.lyric or "")][:8]
    lyric += [0] * (8 - len(lyric))
    phoneme = note.lyric if (note.lyric or "").isascii() else ""
    return (_i32(note.start) + _u32(max(1, note.dur))
            + _u32(max(0, KEY_ORIGIN - int(note.midi)))
            + b"".join(value.to_bytes(2, "little") for value in lyric)
            + _utf16(phoneme[:8], 16)
            # 5 段音素时长表，全 0 表示按默认比例切分
            + b"\x00" * 40)


def _song_track(song: Song, title: str) -> bytes:
    notes = [note for note in song.notes if note.dur > 0]
    end = max(note.start + note.dur for note in notes)
    data = (b"\n" + _u32(0) + _u32(end)
            + _utf16("Muta", 516)      # 258 个 u16 的歌手名
            + _u32(0)
            + _array([_note(note) for note in notes]))
    values = {slot: [] for slot in PARAM_SLOTS}
    values["pitch_data"] = _pitch_points(song)
    data += b"".join(_points(values[slot]) for slot in PARAM_SLOTS)

    return (_u32(TRACK_TYPE_SONG) + _u32(1) + b"\n"
            + _u32(0) + _u32(0) + _u32(50) + _u32(50)
            # 轨道名只有 12 字节 = 6 个 UTF-16 字符，多出来的会被截掉
            + _utf16((title or "VocaloidTTS")[:6], 12)
            + b"\x00" * 52
            + data)


def build_file(song: Song, title: str = "VocaloidTTS") -> bytes:
    notes = [note for note in song.notes if note.dur > 0]
    if not notes:
        raise ValueError("没有可导出的音符")

    numerator = max(1, min(16, int(song.numerator)))
    denominator = int(song.denominator)
    if denominator not in (2, 4, 8, 16):
        denominator = 4

    tempos = _array([_i32(0) + _u32(int(round(max(1.0, float(song.bpm)) * 100)))])
    signatures = _array([_i32(0) + _u32(numerator) + _u32(denominator)])
    tracks = _array([_song_track(song, title)])
    return _u32(FILE_VERSION) + tempos + signatures + tracks + b"\n"


def write_mtp(song: Song, path: str) -> Path:
    """把 Song 写成 Muta 的 .mtp。"""
    target = Path(path).with_suffix(".mtp")
    atomic_write_bytes(target, build_file(song))
    return target


FORMAT = Format(
    key="mtp",
    label="Muta 工程",
    short="Muta",
    extension=".mtp",
    filetype=("Muta 工程", "*.mtp"),
    prefix="VocaloidTTS_Muta",
    writer=write_mtp,
)
