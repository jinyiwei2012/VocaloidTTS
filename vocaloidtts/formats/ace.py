"""ACE Virtual Singer（手机版）工程（.ace）。

一份 JSON。顶层是 ``version`` / ``debug_info`` / ``song_info`` / ``bgm_info`` /
``tracks``，时间全部用**秒**（浮点），不是 tick。

格式细节参考 LibreSVIP 的 ``libresvip/plugins/ace``（MIT，见
THIRD_PARTY_NOTICES.md）。这里只保留**写**方向，简化之处：

- 只写一条唱轨，不写音频轨（``bgm_info.tracks`` 留空）；
- 呼吸标记一律不写（我们生成的音符没有气口标记）；
- ``song_id`` 固定写 0。LibreSVIP 用 ``int(time.time() * 1000)``，同一份 Song
  每次导出都不一样，没法做可复现性测试。

两个容易踩的点：

- **音高字段加 12**：``pitch`` 写的是 MIDI + 12，不是 MIDI。
- **序列化后的键名是混合风格**：带别名的字段是驼峰（``pitchBends`` /
  ``AI_SVS_mode`` / ``operateScale`` / ``recordType``），没别名的保持下划线
  （``song_info`` / ``role_info`` / ``start_time``）。这不是笔误，是原模型就
  长这样。
"""
from __future__ import annotations

import json
from pathlib import Path

from ..atomicio import atomic_write_text
from ..prosody import Song
from .base import Format, lyric_for, pit_cents, seconds

#: 工程版本号。
PROJECT_VERSION = 2

#: 音高字段的偏移：pitch = MIDI + 12。
PITCH_OFFSET = 12

#: 音阶表，照抄 LibreSVIP（15 个音级）。
DEFAULT_SCALE = [84, 83, 81, 79, 77, 76, 74, 72, 71, 69, 67, 65, 64, 62, 60]

#: 默认角色。
DEFAULT_ROLE_NAME = "神秘歌手"


def _pitch_bends(song: Song, note) -> list[dict]:
    """音符内的音高偏移，单位半音（相对音符本身）。"""
    return [{"time": round(seconds(song, note.start + rel), 6),
             "pitch": round(cents / 100.0, 4)}
            for rel, cents in pit_cents(song, note)]


def _note(song: Song, note) -> dict:
    return {
        "start_time": round(seconds(song, note.start), 6),
        "end_time": round(seconds(song, note.start + note.dur), 6),
        "pitch": max(0, min(127, int(note.midi))) + PITCH_OFFSET,
        "word": lyric_for(note),
        # note.lyric 本来就是拼音
        "pinyin": note.lyric or lyric_for(note),
        "pitchBends": _pitch_bends(song, note),
        "br": False,
        "config": "",
        "key": "C",
        "scale": list(DEFAULT_SCALE),
    }


def build_project(song: Song, title: str = "VocaloidTTS") -> dict:
    notes = [note for note in song.notes if note.dur > 0]
    if not notes:
        raise ValueError("没有可导出的音符")

    numerator = max(1, min(16, int(song.numerator)))
    end = max(note.start + note.dur for note in notes)

    payload = [_note(song, note) for note in notes]
    track = {
        "AI_SVS_mode": True,
        "br_notes": [],
        "front": True,
        "lyric": "".join(item["word"] for item in payload),
        "unReadLyric": "",
        "mute": False,
        "notes": payload,
        "pan": 0.0,
        "role_info": {"name": DEFAULT_ROLE_NAME, "role_id": 0},
        "singer_volume": 1.0,
        "solo": False,
        "sound_effect": 0,
    }
    song_info = {
        "author": "",
        "beat_of_bar": numerator,
        "bpm": max(1.0, float(song.bpm)),
        "duration": round(seconds(song, end), 6),
        "first_beat_offset": 0.0,
        "key": "C",
        "name": title or "VocaloidTTS",
        "operateScale": list(DEFAULT_SCALE),
        "scale": list(DEFAULT_SCALE),
        "segment_of_beat": 4,
        "song_id": 0,
        "start": 0.0,
        "unReadLyric": "",
        "user_id": 0,
    }
    return {
        "version": PROJECT_VERSION,
        "debug_info": {
            "device": "",
            "os": "",
            "platform": "android",
            "recordType": "create",
            "version": "3.2.5",
        },
        "song_info": song_info,
        "bgm_info": {"tracks": [], "bgm_volume": 1.0, "mute": False, "solo": False},
        "tracks": [track],
    }


def write_ace(song: Song, path: str) -> Path:
    """把 Song 写成 ACE Virtual Singer 的 .ace。"""
    project = build_project(song)
    target = Path(path).with_suffix(".ace")
    atomic_write_text(target, json.dumps(project, ensure_ascii=False, indent=2))
    return target


FORMAT = Format(
    key="ace",
    label="ACE Virtual Singer 工程",
    short="ACE 手机版",
    extension=".ace",
    filetype=("ACE Virtual Singer 工程", "*.ace"),
    prefix="VocaloidTTS_ACEMobile",
    writer=write_ace,
)
