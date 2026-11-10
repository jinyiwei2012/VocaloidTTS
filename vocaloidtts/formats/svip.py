"""OpenSVIP 交换工程（.svip）：JSON，可继续交给 OpenSVIP 转换器。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from ..atomicio import atomic_write_text
from ..prosody import Note, Song
from .base import (Format, PitchIndex, curve_values, db_value, lyric_for,
                   pit_cents, pronunciation_for, resample)

def _svip_note(n: Note) -> dict:
    return {
        "startPos": int(n.start),
        "length": int(max(1, n.dur)),
        "keyNumber": int(n.midi),
        "lyric": lyric_for(n),
        "pronunciation": pronunciation_for(n),
        # OpenSVIP 的 HeadTag 是字符串，不是 svip3 那种 {spLen, silLen} 对象。
        # 写成对象会让 Newtonsoft 反序列化抛 JsonSerializationException，
        # 整份 .svip 打不开。
        "headTag": "",
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
    song = resample(song)
    if not song.notes:
        raise ValueError("没有可导出的音符")
    end = max(n.start + n.dur for n in song.notes)
    pitch = []
    pitch_index = PitchIndex(song.controls.get("P", []))
    for n in song.notes:
        for x, cents in pit_cents(song, n, pitch_index=pitch_index):
            pitch.append([int(n.start + x), round(cents, 3)])
    track = {
        # TrackJsonConverter 是大小写敏感的 switch，只认 "Singing"/"Instrumental"，
        # 小写会被 return null，整条轨道丢掉。
        "type": "Singing",
        "name": "洛天依",
        # OpenSVIP 用 AISingerName（歌手名）；UUID 是 X Studio 的字段，塞进来
        # 既不是它的字段，也会让歌手变成空。
        "AISingerName": "洛天依",
        "noteList": [_svip_note(n) for n in song.notes],
        "editedParams": {
            "pitch": _svip_param(pitch),
            "volume": _svip_param(((t, db_value(v)) for t, v in curve_values(song, "DYN"))),
            "breath": _svip_param(((t, v) for t, v in curve_values(song, "BRE"))),
            # VSQX 的 GEN 是 64=中性，OpenSVIP 的 Gender 是 -100..100（0=中性）；
            # 原值直写会让整首歌偏高 64。
            "gender": _svip_param(((t, (v - 64) * 100.0 / 63.0)
                                   for t, v in curve_values(song, "GEN"))),
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
    atomic_write_text(path, json.dumps(project, ensure_ascii=False, indent=2) + "\n")
    return path

FORMAT = Format(
    key="svip",
    label="OpenSVIP 工程",
    short="OpenSVIP",
    extension=".svip",
    filetype=("OpenSVIP 工程", "*.svip"),
    prefix="VocaloidTTS_OpenSVIP",
    writer=write_svip,
)
