"""X Studio 3 工程（.svip3）：手写 protobuf，无额外依赖。"""
from __future__ import annotations

import struct
from pathlib import Path

from ..atomicio import atomic_write_bytes
from ..prosody import Note, Song
from .base import (Format, PitchIndex, curve_values, lyric_for, pit_cents,
                   pronunciation_for, resample)

XSTUDIO_LUOTIANYI_ID = "c5ed53a0-9d84-4fa7-bef5-e99087b046f0"  # 陈水若 (temporary)
XSTUDIO_LUOTIANYI_NAME = "洛天依"

# ---------------------------------------------------------------------------
# X Studio 3 protobuf (.svip3)
# ---------------------------------------------------------------------------

def _varint(value: int) -> bytes:
    value = int(value)
    if value < 0:
        value &= (1 << 64) - 1
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _tag(field: int, wire: int) -> bytes:
    return _varint((field << 3) | wire)


def _pb_int(field: int, value: int) -> bytes:
    return _tag(field, 0) + _varint(value)


def _pb_sint(field: int, value: int) -> bytes:
    value = int(value)
    zig = (value << 1) ^ (value >> 31)
    return _tag(field, 0) + _varint(zig)


def _pb_bool(field: int, value: bool) -> bytes:
    return _tag(field, 0) + _varint(1 if value else 0)


def _pb_float(field: int, value: float) -> bytes:
    return _tag(field, 5) + struct.pack("<f", float(value))


def _pb_str(field: int, value: str) -> bytes:
    data = (value or "").encode("utf-8")
    return _tag(field, 2) + _varint(len(data)) + data


def _pb_msg(field: int, data: bytes) -> bytes:
    return _tag(field, 2) + _varint(len(data)) + data


def _xs3_point(position: int, value: float) -> bytes:
    # Xs3ParamPoint: 1 Position (sint32, ZigZag), 2 Value (float)
    return _pb_sint(1, position) + _pb_float(2, value)


def _xs3_note(n: Note) -> bytes:
    data = b"".join([
        _pb_int(1, n.start),
        _pb_int(2, max(1, n.dur)),
        _pb_int(3, n.midi),
        _pb_str(4, lyric_for(n)),
        _pb_str(5, pronunciation_for(n)),
        _pb_int(6, 0),
        _pb_bool(7, False),
        _pb_int(9, 0),
        _pb_int(10, 0),
    ])
    return data


def _xs3_pitch_points(song: Song, numerator: int = 4, denominator: int = 4) -> list[tuple[int, float]]:
    points: list[tuple[int, float]] = []
    pitch_index = PitchIndex(song.controls.get("P", []))
    # Keep pitch positions in the same tick space as Xs3Note.StartPosition.
    # OpenSVIP's converter subtracts FirstBarLength for its own project model,
    # but VTTS writes notes and pitch into one self-consistent pattern.
    for n in song.notes:
        for x, cents in pit_cents(song, n, pitch_index=pitch_index):
            # X Studio stores absolute MIDI pitch, with a half-semitone offset.
            points.append((max(0, n.start + x), n.midi + cents / 100.0 + 0.5))
    if not points:
        points = [(0, 0.5)]
    points.sort()
    # A -1 value is X Studio's "break"; bracket the curve so no stale tail
    # is drawn outside the generated region.
    return [(points[0][0], -1.0)] + points + [(points[-1][0], -1.0)]


def write_svip3(song: Song, path: str, singer_id: str = XSTUDIO_LUOTIANYI_ID) -> str:
    """Write a minimal X Studio 3 protobuf project."""
    song = resample(song)
    if not song.notes:
        raise ValueError("没有可导出的音符")

    end = max(n.start + n.dur for n in song.notes)
    pattern = b"".join([
        _pb_str(1, XSTUDIO_LUOTIANYI_NAME),
        _pb_int(3, 0),
        _pb_int(4, end + 19200),
        _pb_int(5, 0),
        _pb_int(6, end + 1920),
        _pb_bool(7, False),
        b"".join(_pb_msg(8, _xs3_note(n)) for n in song.notes),
        b"".join(_pb_msg(9, _xs3_point(pos, val))
                 for pos, val in _xs3_pitch_points(song, song.numerator, song.denominator)),
    ])
    track = b"".join([
        _pb_float(1, 0.0),
        _pb_float(2, 0.0),
        _pb_bool(3, False),
        _pb_str(4, XSTUDIO_LUOTIANYI_NAME),
        _pb_bool(5, False),
        _pb_str(6, "#24936E"),
        _pb_msg(8, pattern),
        _pb_str(9, singer_id),
    ])
    any_track = b"".join([
        _pb_str(1, "type.googleapis.com/xstudio.proto.SingingTrack"),
        _pb_msg(2, track),
    ])
    tempo = _pb_int(2, int(round(float(song.bpm) * 100.0)))
    time_sig_content = _pb_int(1, int(song.numerator)) + _pb_int(2, int(song.denominator))
    time_sig = _pb_msg(2, time_sig_content)
    master = _pb_float(1, 0.0)
    project = b"".join([
        _pb_str(2, "3.0"),
        _pb_int(3, max(192000, end + 19200)),
        _pb_msg(4, tempo),
        _pb_msg(5, time_sig),
        _pb_msg(6, any_track),
        _pb_msg(7, master),
        _pb_str(8, "C大调"),
        _pb_int(9, 16),
        _pb_int(10, 0),
        _pb_int(11, max(1920, end + 1920)),
        _pb_bool(12, True),
    ])
    path = str(Path(path).with_suffix(".svip3"))
    atomic_write_bytes(path, project)
    return path


# ---------------------------------------------------------------------------
# OpenUTAU YAML (.ustx)
# ---------------------------------------------------------------------------


FORMAT = Format(
    key="svip3",
    label="X Studio 3 工程",
    short="X Studio 3",
    extension=".svip3",
    filetype=("X Studio 3 工程", "*.svip3"),
    prefix="VocaloidTTS_XStudio",
    writer=write_svip3,
)
