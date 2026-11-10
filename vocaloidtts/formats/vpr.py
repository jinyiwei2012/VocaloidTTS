"""VOCALOID 5/6 工程（.vpr）。

``.vpr`` 是个 zip 包，里面只有一份 ``Project/sequence.json``（带音频轨时
还会有 ``Project/Audio/<name>``）。所以要写的其实是 JSON，外加一层 zipfile
包装——真正重的是 JSON 里的字段，不是容器。

格式细节参考 LibreSVIP 的 ``libresvip/plugins/vpr``（MIT，见
THIRD_PARTY_NOTICES.md），这里只保留**写**方向，并做了四处简化：

- 只写标准轨（``type`` 0），不写 AI 轨；V6 打开标准轨没问题；
- 不写 ``aiExp`` / ``directPitches`` / ``dvqm``，这些是 V6 的可选块；
- 控制器只映射 VSQX 里同名的六个（PIT / PBS / DYN / BRE / BRI / GEN）。
  注意 vpr 里 gender 的字段名是 ``character``，不是 ``gender``；
- zip 用不压缩（stored）写，和 LibreSVIP 一致——省下的那点体积不值得
  多一个「压缩方式会不会被挑剔的读取器拒绝」的变量。

歌词写**汉字**、音素写 X-SAMPA，两者都写：LibreSVIP 的 vpr 解析器把
``lyric`` 原样收进中间模型，再由 vsqx 生成器把汉字转成拼音，说明 vpr 里的
``lyric`` 本来就是汉字。音素直接取 ``Note.phonemes``（``pinyin.py`` 生成的
VOCALOID X-SAMPA），和 VSQX 的 ``<p>`` 是同一套符号，不需要退化成 ``l a``。

时间单位：tick，480 / 四分音符（内部 tick 由 ``base.resample`` 换算）；BPM 以 1/100 为单位存
（120 BPM -> 12000）。
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from ..atomicio import atomic_write_bytes
from ..pinyin import pinyin_to_phonemes
from ..prosody import Song
from ..voicebank import Voicebank
from .base import Format, comp_id, lyric_for, resample

#: 简体中文的 langID。VOCALOID 的枚举：0 日 / 1 英 / 2 韩 / 3 西 / 4 简中。
LANG_SIMPLIFIED_CHINESE = 4

#: BPM 的存储倍率：120 BPM 存成 12000。
BPM_RATE = 100

#: 标准轨。1 是音频轨，2 是 AI 轨。
TRACK_TYPE_STANDARD = 0

#: 兜底音素，只在 Note.phonemes 和拼音都拿不到时用。
DEFAULT_CHINESE_PHONEME = "l a"

#: (Song.controls 的键, vpr 的控制器名, 下限, 上限)
CONTROLLERS = (
    ("P", "pitchBend", -8192, 8191),
    ("S", "pitchBendSens", 1, 24),
    ("DYN", "dynamics", 0, 127),
    ("BRE", "breathiness", 0, 127),
    ("BRI", "brightness", 0, 127),
    ("GEN", "character", 0, 127),
)


def _phoneme(note) -> str:
    """取 VOCALOID X-SAMPA 音素串。"""
    phonemes = (getattr(note, "phonemes", "") or "").strip()
    if phonemes:
        return phonemes
    return pinyin_to_phonemes(note.lyric or "") or DEFAULT_CHINESE_PHONEME


def _point(tick: int, value: int) -> dict:
    return {"pos": int(tick), "value": int(value)}


def _automation(events: list[dict]) -> dict:
    return {"isFolded": True, "height": 0, "events": events}


def _note(note) -> dict:
    return {
        "langID": LANG_SIMPLIFIED_CHINESE,
        "pos": max(0, int(note.start)),
        "duration": max(1, int(note.dur)),
        # exp 里只写 opening，其余（accent / decay / 弯音）留空用编辑器默认
        "exp": {"opening": 127},
        "isProtected": False,
        "isAiVibratoEnabled": False,
        "lyric": lyric_for(note),
        "number": max(0, min(127, int(note.midi))),
        "phoneme": _phoneme(note),
        "singingSkill": {"duration": 158, "weight": {"pre": 64, "post": 64}},
        "velocity": max(1, min(127, int(note.velocity))),
        "vibrato": {"type": 0, "duration": 0, "depths": [], "rates": []},
    }


def _controllers(song: Song) -> list[dict]:
    out: list[dict] = []
    for key, name, low, high in CONTROLLERS:
        events = [
            _point(t, max(low, min(high, int(v))))
            for t, v in sorted(song.controls.get(key) or [], key=lambda p: p[0])
            if t >= 0
        ]
        if events:
            out.append({"name": name, "events": events})
    return out


def build_project(song: Song, voicebank: Voicebank,
                  title: str = "VocaloidTTS") -> dict:
    """把 Song 转成 sequence.json 的字典。"""
    song = resample(song)
    notes = [n for n in song.notes if n.dur > 0]
    if not notes:
        raise ValueError("没有可导出的音符")

    comp = comp_id(voicebank)
    end_tick = max(int(n.start) + int(n.dur) for n in notes)
    bpm_value = int(round(max(1.0, float(song.bpm)) * BPM_RATE))

    numerator = max(1, min(16, int(song.numerator)))
    denominator = int(song.denominator)
    if denominator not in (2, 4, 8, 16):
        denominator = 4

    part = {
        "pos": 0,
        "name": "",
        "audioEffects": [],
        "duration": end_tick,
        "midiEffects": [],
        "notes": [_note(n) for n in notes],
        "styleName": "No Effect",
        "voice": {"compID": comp, "langID": LANG_SIMPLIFIED_CHINESE},
        "controllers": _controllers(song),
    }

    track = {
        "isFolded": True,
        "busNo": 0,
        "color": 0,
        "height": 0,
        "isMuted": False,
        "isSoloMode": False,
        "name": title or "VocaloidTTS",
        "panpot": _automation([_point(0, 0)]),
        "volume": _automation([]),
        "audioEffects": [],
        "parts": [part],
        "type": TRACK_TYPE_STANDARD,
    }

    return {
        "masterTrack": {
            "loop": {"isEnabled": True, "begin": 0, "end": end_tick},
            "samplingRate": 44100,
            "tempo": {
                "isFolded": True,
                "events": [_point(0, bpm_value)],
                "global": {"isEnabled": True, "value": bpm_value},
                "height": 0,
            },
            "timeSig": {
                "isFolded": True,
                "events": [{"bar": 0, "numer": numerator,
                            "denom": denominator}],
            },
            "volume": _automation([_point(0, 0)]),
            "mainTuning": 440,
        },
        "title": title or "",
        "tracks": [track],
        "vender": "Yamaha Corporation",
        "version": {"major": 5, "minor": 0, "revision": 0},
        "voices": [{"compID": comp, "name": voicebank.name}],
    }


def write_vpr(song: Song, path: str, voicebank: Voicebank,
              title: str = "VocaloidTTS") -> Path:
    """把 Song 写成 VOCALOID 5/6 的 .vpr。"""
    project = build_project(song, voicebank, title=title)
    payload = json.dumps(project, ensure_ascii=False).encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Project/sequence.json", payload)
    target = Path(path).with_suffix(".vpr")
    atomic_write_bytes(target, buffer.getvalue())
    return target


FORMAT = Format(
    key="vpr",
    label="VOCALOID 5/6 工程",
    short="VPR",
    extension=".vpr",
    filetype=("VOCALOID 5/6 工程", "*.vpr"),
    prefix="VocaloidTTS_V5",
    writer=write_vpr,
    needs_voicebank=True,
)
