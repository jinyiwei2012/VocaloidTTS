"""Exporters for VTTS 1.1: X Studio 3 (.svip3), OpenUTAU (.ustx), OpenSVIP (.svip).

The writers are deliberately dependency-free: X Studio's protobuf wire format is
small enough to emit by hand, and both OpenUTAU and OpenSVIP documents are
text-based.  This keeps the frozen one-folder build lean and avoids shipping
protobuf/PyYAML just for export.
"""
from __future__ import annotations

import json
import math
import struct
from pathlib import Path
from typing import Iterable

from .prosody import Note, Song

# X Studio 3 does not expose a public 洛天依 UUID in the OpenSVIP singer table.
# The user explicitly chose to borrow a built-in female singer so the project
# opens with a usable voice; the track is still named 洛天依 and can be changed
# in X Studio's singer picker.
XSTUDIO_LUOTIANYI_ID = "c5ed53a0-9d84-4fa7-bef5-e99087b046f0"  # 陈水若 (temporary)
XSTUDIO_LUOTIANYI_NAME = "洛天依"

OPENUTAU_SINGER = "洛天依"
OPENUTAU_PHONEMIZER = "OpenUtau.Core.DefaultPhonemizer"

FORMATS = {
    "vsqx": {
        "label": "VOCALOID VSQX",
        "short": "VSQX",
        "extension": ".vsqx",
        "filetype": ("VOCALOID 序列", "*.vsqx"),
        "prefix": "VocaloidTTS",
    },
    "svip3": {
        "label": "X Studio 3 工程",
        "short": "X Studio 3",
        "extension": ".svip3",
        "filetype": ("X Studio 3 工程", "*.svip3"),
        "prefix": "VocaloidTTS_XStudio",
    },
    "ustx": {
        "label": "OpenUTAU 工程",
        "short": "OpenUTAU",
        "extension": ".ustx",
        "filetype": ("OpenUTAU 工程", "*.ustx"),
        "prefix": "VocaloidTTS_OpenUTAU",
    },
    "svip": {
        "label": "OpenSVIP 工程",
        "short": "OpenSVIP",
        "extension": ".svip",
        "filetype": ("OpenSVIP 工程", "*.svip"),
        "prefix": "VocaloidTTS_OpenSVIP",
    },
}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _has_han(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text or "")


def lyric_for(note: Note) -> str:
    """X Studio wants a Chinese lyric; pinyin input falls back to 啦."""
    text = getattr(note.syl, "text", "") or ""
    return text if _has_han(text) else "啦"


def pronunciation_for(note: Note) -> str:
    return note.lyric or getattr(note.syl, "phonemes", "") or "a"


def pit_cents(song: Song, note: Note) -> list[tuple[int, float]]:
    """Return note-relative pitch points as (tick, cents)."""
    raw = song.controls.get("P", [])
    pts: list[tuple[int, float]] = []
    for t, v in raw:
        if note.start <= t <= note.start + note.dur:
            semis = float(v) * 12.0 / 8192.0
            pts.append((int(t - note.start), semis * 100.0))
    if not pts:
        pts = [(0, 0.0), (max(1, note.dur), 0.0)]
    if pts[0][0] > 0:
        pts.insert(0, (0, pts[0][1]))
    if pts[-1][0] < note.dur:
        pts.append((max(1, note.dur), pts[-1][1]))
    return pts


def _curve_values(song: Song, cid: str) -> list[tuple[int, int]]:
    return sorted(song.controls.get(cid, []), key=lambda p: p[0])


def _db_value(vsqx: int) -> float:
    """VSQX DYN 0..127 -> a mild OpenUTAU dyn curve (dB-ish)."""
    return max(-24.0, min(24.0, (float(vsqx) - 64.0) * 0.2))


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
    # Keep pitch positions in the same tick space as Xs3Note.StartPosition.
    # OpenSVIP's converter subtracts FirstBarLength for its own project model,
    # but VTTS writes notes and pitch into one self-consistent pattern.
    for n in song.notes:
        for x, cents in pit_cents(song, n):
            points.append((max(0, n.start + x), cents / 100.0 + 0.5))
    if not points:
        points = [(0, 0.5)]
    points.sort()
    # A -1 value is X Studio's "break"; bracket the curve so no stale tail
    # is drawn outside the generated region.
    return [(points[0][0], -1.0)] + points + [(points[-1][0], -1.0)]


def write_svip3(song: Song, path: str, singer_id: str = XSTUDIO_LUOTIANYI_ID) -> str:
    """Write a minimal X Studio 3 protobuf project."""
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
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(project)
    return path


# ---------------------------------------------------------------------------
# OpenUTAU YAML (.ustx)
# ---------------------------------------------------------------------------

def _yaml_str(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _tick_ms(song: Song, ticks: float) -> float:
    """Convert project ticks to milliseconds at the song's tempo."""
    bpm = float(getattr(song, "bpm", 120) or 120)
    resolution = float(getattr(song, "resolution", 480) or 480)
    return float(ticks) * 60000.0 / (bpm * resolution)


def _ustx_pitch_points(song: Song, note: Note) -> list[tuple[int, float]]:
    """OpenUTAU pitch points: x = ms after note start, y = 0.1 semitone."""
    pts = []
    for tick, cents in pit_cents(song, note):
        x = int(round(_tick_ms(song, tick)))
        y = round(float(cents) / 10.0, 3)
        if pts and x <= pts[-1][0]:
            x = pts[-1][0] + 1
        pts.append((x, y))
    return pts


def _ustx_curve(song: Song, cid: str, end: int, scale) -> tuple[list[int], list[int]]:
    raw = [(int(t), scale(v)) for t, v in _curve_values(song, cid)]
    raw = [(t, int(round(v))) for t, v in raw if 0 <= t <= end]
    if not raw:
        return [], []
    if raw[0][0] > 0:
        raw.insert(0, (0, raw[0][1]))
    if raw[-1][0] < end:
        raw.append((end, raw[-1][1]))
    xs = [x for x, _ in raw]
    ys = [y for _, y in raw]
    return xs, ys


def write_ustx(song: Song, path: str) -> str:
    """Write an OpenUTAU 0.10 project.

    OpenUTAU fills its default expression descriptors on load, so the project
    only needs the standard selectors and part curves. Pitch points are in
    milliseconds after the note and 0.1-semitone units, matching
    OpenUtau.Core.Ustx.PitchPoint.
    """
    if not song.notes:
        raise ValueError("没有可导出的音符")
    end = max(n.start + n.dur for n in song.notes)
    notes = sorted(song.notes, key=lambda n: n.start)

    lines: list[str] = [
        "name: " + _yaml_str("VocaloidTTS") + "\n",
        "comment: " + _yaml_str("Generated by VocaloidTTS 1.1") + "\n",
        "outputDir: " + _yaml_str("VocaloidTTS_Output") + "\n",
        "cacheDir: " + _yaml_str("VocaloidTTS_Cache") + "\n",
        'ustxVersion: "0.10"\n',
        "expSelectors: [dyn, pitd, clr, eng, vel, vol, atk, dec, gen, bre]\n",
        "key: 0\n",
        "timeSignatures:\n",
        "  - barPosition: 0\n",
        f"    beatPerBar: {int(song.numerator)}\n",
        f"    beatUnit: {int(song.denominator)}\n",
        "tempos:\n",
        "  - position: 0\n",
        f"    bpm: {float(song.bpm):.3f}\n",
        "tracks:\n",
        "  - singer: " + _yaml_str(OPENUTAU_SINGER) + "\n",
        "    RendererSettings:\n",
        '      renderer: "CLASSIC"\n',
        "    TrackName: " + _yaml_str("洛天依") + "\n",
        '    TrackColor: "4f9d8a"\n',
        "    Mute: false\n",
        "    Solo: false\n",
        "    Volume: 0\n",
        "    Pan: 0\n",
        "    VoiceColorNames: []\n",
        "voiceParts:\n",
        "  - name: " + _yaml_str("VocaloidTTS") + "\n",
        "    comment: " + _yaml_str("VocaloidTTS speech-like vocal") + "\n",
        "    trackNo: 0\n",
        "    position: 0\n",
        f"    duration: {int(max(1, end))}\n",
        "    notes:\n",
    ]
    for n in notes:
        lines.append(f"      - position: {int(n.start)}\n")
        lines.append(f"        duration: {int(max(1, n.dur))}\n")
        lines.append(f"        tone: {int(n.midi)}\n")
        lyric = getattr(n.syl, "text", "") or ""
        if not _has_han(lyric):
            lyric = n.lyric or "a"
        lines.append(f"        lyric: {_yaml_str(lyric)}\n")
        lines.append("        pitch:\n          data:\n")
        for x, y in _ustx_pitch_points(song, n):
            lines.append(f"          - {{x: {int(x)}, y: {float(y):.3f}, shape: io}}\n")
        lines.append("          snap_first: false\n")
        lines.append("        vibrato: {length: 0, period: 175, depth: 25, in: 10, out: 10, shift: 0, drift: 0, vol_link: 0}\n")
        lines.append("        tuning: 0\n")
        lines.append("        phoneme_expressions: []\n")
        lines.append("        phoneme_overrides: []\n")
    lines.append("    curves:\n")
    for cid in ("DYN", "BRE", "GEN"):
        if cid == "DYN":
            scale = lambda v: max(-240.0, min(120.0, _db_value(v) * 10.0))
        elif cid == "BRE":
            scale = lambda v: max(0.0, min(100.0, float(v) * 100.0 / 127.0))
        else:
            scale = lambda v: max(-100.0, min(100.0, (float(v) - 64.0) * 100.0 / 63.0))
        xs, ys = _ustx_curve(song, cid, end, scale)
        if not xs:
            continue
        abbr = {"DYN": "dyn", "BRE": "bre", "GEN": "gen"}[cid]
        lines.append(f"      - abbr: {_yaml_str(abbr)}\n")
        lines.append("        xs: [" + ", ".join(str(x) for x in xs) + "]\n")
        lines.append("        ys: [" + ", ".join(str(y) for y in ys) + "]\n")
    lines.append("    maskedCurves: []\n")
    path = str(Path(path).with_suffix(".ustx"))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("".join(lines), encoding="utf-8", newline="\n")
    return path


# ---------------------------------------------------------------------------
# OpenSVIP JSON (.svip)
# ---------------------------------------------------------------------------

def _svip_note(n: Note) -> dict:
    return {
        "startPos": int(n.start),
        "length": int(max(1, n.dur)),
        "keyNumber": int(n.midi),
        "lyric": lyric_for(n),
        "pronunciation": pronunciation_for(n),
        "headTag": {"spLen": 0, "silLen": 0},
    }


def _svip_param(points: Iterable[tuple[int, float]], scale: float = 1.0) -> dict:
    pts = [[int(t), round(float(v) * scale, 3)] for t, v in points]
    if not pts:
        pts = [[0, 0]]
    return {"pointList": pts}


def write_svip(song: Song, path: str) -> str:
    """Write the OpenSVIP JSON interchange model.

    OpenSVIP's own converters live in C#/.NET; this JSON follows the public
    Project/SingingTrack model (camelCase properties) and is intentionally
    self-describing so it can also be inspected in any text editor.
    """
    if not song.notes:
        raise ValueError("没有可导出的音符")
    end = max(n.start + n.dur for n in song.notes)
    pitch = []
    for n in song.notes:
        for x, cents in pit_cents(song, n):
            pitch.append([int(n.start + x), round(cents, 3)])
    track = {
        "type": "singing",
        "name": "洛天依",
        "singer": XSTUDIO_LUOTIANYI_ID,
        "noteList": [_svip_note(n) for n in song.notes],
        "editedParams": {
            "pitch": _svip_param(pitch),
            "volume": _svip_param(((t, _db_value(v)) for t, v in _curve_values(song, "DYN"))),
            "breath": _svip_param(((t, v) for t, v in _curve_values(song, "BRE"))),
            "gender": _svip_param(((t, v) for t, v in _curve_values(song, "GEN"))),
        },
    }
    project = {
        "formatVersion": "1.0",
        "version": "1.0",
        "project": {
            "songTempoList": [{"position": 0, "bpm": float(song.bpm)}],
            "timeSignatureList": [{
                "barPosition": 0,
                "numerator": int(song.numerator),
                "denominator": int(song.denominator),
            }],
            "trackList": [track],
        },
        # Also expose the model at the top level: some OpenSVIP builds read the
        # Project object directly and ignore the envelope.
        "songTempoList": [{"position": 0, "bpm": float(song.bpm)}],
        "timeSignatureList": [{
            "barPosition": 0,
            "numerator": int(song.numerator),
            "denominator": int(song.denominator),
        }],
        "trackList": [track],
        "duration": int(max(1, end)),
    }
    path = str(Path(path).with_suffix(".svip"))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8", newline="\n")
    return path
