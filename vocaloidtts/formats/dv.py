"""DeepVocal 工程（.dv）：二进制，小端，字符串是「u32 长度 + UTF-8」。

文件骨架::

    "SHARPKEY" + u32 版本 + u32 内层长度 + 内层

内层依次是：

    特性标记 "ext1".."ext7"
    速度数组 / 拍号数组 / 轨道数组

数组的写法分两种，容易混：

- ``tempos`` / ``time_signatures`` / ``segments`` / ``notes`` 是
  **「u32 字节长度 + u32 元素个数 + 元素」**——外层长度用来跳读；
- ``tracks`` 只有 **「u32 元素个数 + 元素」**，没有外层长度。

音高轴是反的：``key = 115 - MIDI``。

格式细节参考 LibreSVIP 的 ``libresvip/plugins/dv``（MIT，见
THIRD_PARTY_NOTICES.md）。这里只保留**写**方向，简化之处：

- 只写一条唱轨，不写音频轨；
- 音高曲线只写两个端点（``-1`` 和 ``307201``），不铺满整段；
- 每个音符的 ``unknown`` 数据块写**空数组**（元素个数 0）。LibreSVIP 会塞
  一整块浮点常量进去，用途不明，照抄一串 512 个魔数没有意义——空数组在结构上
  是合法的，但如果 DeepVocal 依赖那块数据，这里就是缺口。
"""
from __future__ import annotations

import struct
from pathlib import Path

from ..atomicio import atomic_write_bytes
from ..prosody import Song
from .base import Format, lyric_for, resample

#: 文件魔数。
MAGIC = b"SHARPKEY"

#: 工程版本号。
FILE_VERSION = 5

#: 特性标记，写全七种，和 LibreSVIP 一致。
FEATURES = b"ext1ext2ext3ext4ext5ext6ext7"

#: 音高轴零点：key = 115 - MIDI。
NOTE_KEY_SUM = 115

#: 轨道音量。
DEFAULT_VOLUME = 30

#: 轨道类型：0 唱轨 / 1 音频轨。
TRACK_TYPE_SINGING = 0

#: 参数曲线的两个端点。
PARAM_START = -1
PARAM_END = 307201


def _u32(value: int) -> bytes:
    return int(value).to_bytes(4, "little")


def _i32(value: int) -> bytes:
    return int(value).to_bytes(4, "little", signed=True)


def _str(text: str) -> bytes:
    data = text.encode("utf-8")
    return _u32(len(data)) + data


def _prefixed_array(items: list[bytes]) -> bytes:
    """u32 字节长度 + u32 元素个数 + 元素。"""
    body = _u32(len(items)) + b"".join(items)
    return _u32(len(body)) + body


def _array(items: list[bytes]) -> bytes:
    """只有 u32 元素个数，没有外层长度。"""
    return _u32(len(items)) + b"".join(items)


def _points(points: list[tuple[int, int]]) -> bytes:
    return _prefixed_array([_i32(x) + _i32(y) for x, y in points])


def _note(note) -> bytes:
    return b"".join((
        _i32(note.start),
        _u32(max(1, note.dur)),
        _u32(max(0, NOTE_KEY_SUM - int(note.midi))),
        _u32(50),                                    # vibrato
        _str(note.lyric or lyric_for(note)),         # phoneme
        _str(lyric_for(note)),                       # word
        b"\x00",                                     # padding_1
        _prefixed_array([                            # note_vibrato_data
            _points([(-1, 0), (100001, 0)]),
            _points([(-1, 0), (100001, 0)]),
            _points([(0, 0), (1124, 0)]),
        ]),
        _prefixed_array([]),                         # unknown：留空
        # phonemes：int8 + float + int8 + 3×float
        struct.pack("<bfbfff", 0, 1.0, 0, 1.0, 1.0, 1.0),
        _u32(0), _u32(0), _u32(0), _u32(0),          # ben_depth / ben_length / por_tail / por_head
        _i32(-1),                                    # timbre
        _str(""),                                    # cross_lyric
        _i32(-1),                                    # cross_timbre
    ))


def _segment(song: Song, title: str) -> bytes:
    notes = [note for note in song.notes if note.dur > 0]
    end = max(note.start + note.dur for note in notes)
    flat = [(PARAM_START, 128), (PARAM_END, 128)]
    pitch = [(PARAM_START, -1), (PARAM_END, -1)]
    return b"".join((
        _u32(0),                                     # start
        _u32(max(1, end)),                           # length
        _str(title or "VocaloidTTS"),
        _str("VocaloidTTS"),                         # singer_name
        _prefixed_array([_note(note) for note in notes]),
        _points(flat),                               # volume_data
        _points(pitch),                              # pitch_data
        _points(flat),                               # breath_data
        _points(flat),                               # ext3_data
        _points(flat),                               # ext5_data
        _points(flat),                               # ext6_data
        _points(flat),                               # ext7_data
    ))


def build_file(song: Song, title: str = "VocaloidTTS") -> bytes:
    song = resample(song)
    notes = [note for note in song.notes if note.dur > 0]
    if not notes:
        raise ValueError("没有可导出的音符")

    numerator = max(1, min(16, int(song.numerator)))
    denominator = int(song.denominator)
    if denominator not in (2, 4, 8, 16):
        denominator = 4
    bpm = int(round(max(1.0, float(song.bpm)) * 100))

    track = b"".join((
        _u32(TRACK_TYPE_SINGING),
        _str(title or "VocaloidTTS"),                # 轨道名
        b"\x00\x00",                                 # mute / solo
        _u32(DEFAULT_VOLUME),
        _u32(0),                                     # balance
        _prefixed_array([_segment(song, title)]),
    ))

    inner = b"".join((
        FEATURES,
        _prefixed_array([_i32(0) + _u32(bpm)]),
        _prefixed_array([_i32(0) + _u32(numerator) + _u32(denominator)]),
        _array([track]),
    ))
    return MAGIC + _u32(FILE_VERSION) + _u32(len(inner)) + inner


def write_dv(song: Song, path: str) -> Path:
    """把 Song 写成 DeepVocal 的 .dv。"""
    target = Path(path).with_suffix(".dv")
    atomic_write_bytes(target, build_file(song))
    return target


FORMAT = Format(
    key="dv",
    label="DeepVocal 工程",
    short="DeepVocal",
    extension=".dv",
    filetype=("DeepVocal 工程", "*.dv"),
    prefix="VocaloidTTS_DeepVocal",
    writer=write_dv,
)
