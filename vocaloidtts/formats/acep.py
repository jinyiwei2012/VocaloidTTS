"""ACE Studio 工程（.acep）。

ACE Studio 的工程文件不是裸 JSON，而是一层容器：

    {"compressMethod": "zstd", "version": 1000, "content": "<base64>"}

``content`` 是 zstd 压缩后的工程 JSON。``version`` 取 1000 表示未加密；
1000 以下（1 / 2）还要按 salt 做 AES 解密，我们只写不读，不涉及那条路径。

格式细节参考 LibreSVIP 的 ``libresvip/plugins/acep``（MIT，见
THIRD_PARTY_NOTICES.md），这里只保留**写**方向，并做了四处简化：

- 单轨单 pattern，不做「音符间距超过阈值就切段」的分割；
- 不写参数曲线（``pitchDelta`` / ``energy`` / ``tension`` …）。ACE 会按音符
  自己算；而且 ``pitchDelta`` 存的是「相对基础音高的偏移」，要复现得先算一条
  基础音高曲线，收益不抵成本；
- 声库固定用默认歌手，不做歌手名 → id 的映射表（那张表跟着 ACE 版本变）；
- 不写 uuid，交给编辑器自己生成。

歌词写**汉字**，这一点和其他几种格式相反：ACE 的中文歌词栏本来就收汉字，
发音由编辑器自己查表，写拼音它反而认不出。

时间单位：ACE 的 tick 固定 480 / 四分音符，和我们的内部 tick 一致；只有当
``song.resolution`` 不是 480 时才需要按比例换算。
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

from ..atomicio import atomic_write_bytes
from ..prosody import Song
from .base import Format, lyric_for, zstd_store

#: ACE 的 tick 分辨率：480 tick = 1 个四分音符。
TICKS_PER_QUARTER = 480

#: 工程 JSON 的版本号。9 是 LibreSVIP 写出的值。
PROJECT_VERSION = 9

#: 容器版本。>= 1000 表示 content 未加密。
CONTAINER_VERSION = 1000

#: 工程时长在最后一个音符之后留的余量，和 LibreSVIP 一致。
TAIL_TICKS = 115_200

#: 默认歌手：然糊糊（id 26，seed 23）。
DEFAULT_SINGER_NAME = "然糊糊"
DEFAULT_SINGER_ID = 26
DEFAULT_SEED = 23


def _ticks(song: Song, value: float) -> int:
    """把内部 tick 换算成 ACE 的 tick（480 / 四分音符）。"""
    resolution = int(getattr(song, "resolution", TICKS_PER_QUARTER)
                     or TICKS_PER_QUARTER)
    if resolution == TICKS_PER_QUARTER:
        return int(round(value))
    return int(round(value * TICKS_PER_QUARTER / resolution))


def _note(note, offset: int, song: Song) -> dict:
    start = _ticks(song, note.start)
    return {
        "pos": max(0, start - offset),
        "dur": max(1, _ticks(song, note.dur)),
        "pitch": max(0, min(127, int(note.midi))),
        "uuid": None,
        "language": "CHN",
        # ACE 的中文歌词栏收汉字，发音由编辑器自己查表
        "lyric": lyric_for(note),
        "pronunciation": None,
        "freezedDefaultSyllable": None,
        "newLine": False,
        "consonantLen": None,
        "headConsonants": [],
        "tailConsonants": [],
        "syllable": "",
        "brLen": 0.0,
        "vibrato": None,
        "extraInfo": {},
    }


def _empty_curves() -> dict:
    """参数曲线全部留空，让 ACE 按音符自己算。"""
    return {
        "pitchDelta": [],
        "energy": [],
        "breathiness": [],
        "tension": [],
        "falsetto": [],
        "gender": [],
        "realEnergy": [],
        "realBreathiness": [],
        "realTension": [],
        "realFalsetto": [],
        "vuv": [],
    }


def _singer() -> dict:
    return {
        "composition": [{"code": DEFAULT_SEED, "lock": True,
                         "style": 1.0, "timbre": 1.0}],
        "state": "Unmixed",
        "name": DEFAULT_SINGER_NAME,
        "id": DEFAULT_SINGER_ID,
        "head": -1,
        "router": 1,
        "group": "",
    }


def build_project(song: Song) -> dict:
    """把 Song 转成 ACE Studio 的工程字典（不含容器包装）。"""
    notes = [n for n in song.notes if n.dur > 0]
    if not notes:
        raise ValueError("没有可导出的音符")

    starts = [_ticks(song, n.start) for n in notes]
    ends = [s + max(1, _ticks(song, n.dur)) for s, n in zip(starts, notes)]
    # 和 LibreSVIP 一样，pattern 起点比第一个音符早 240 tick（半个四分音符），
    # 给起音留出位置。
    pattern_pos = max(0, min(starts) - 240)
    pattern_end = max(ends)
    pattern_dur = max(1, pattern_end - pattern_pos)

    numerator = max(1, min(16, int(song.numerator)))
    denominator = int(song.denominator)
    if denominator not in (2, 4, 8, 16):
        denominator = 4

    pattern = {
        "name": "VocaloidTTS",
        "pos": pattern_pos,
        "dur": pattern_dur,
        "uuid": None,
        "clipPos": 0,
        "clipDur": pattern_dur,
        "enabled": True,
        "color": None,
        "extraInfo": {},
        "language": "CHN",
        "extendLyrics": "",
        "notes": [_note(n, pattern_pos, song) for n in notes],
        "timeUnit": "tick",
        "parameters": _empty_curves(),
        "fadeIn": None,
        "fadeOut": None,
        "vocalControls": None,
    }

    track = {
        "type": "sing",
        "name": "VocaloidTTS",
        "color": "#91bcdc",
        "pan": 0.0,
        "gain": 0.0,
        "mute": False,
        "solo": False,
        "record": False,
        "channel": 0,
        "listen": False,
        "uuid": None,
        "extraInfo": {},
        "builtInFx": {},
        "inputSource": None,
        "externalFxChain": [],
        "language": "CHN",
        "patterns": [pattern],
        "choirInfo": {},
        "choirConfig": {},
        "roomEffect": None,
        "singers": [{"singer": _singer(), "gain": 0.0,
                     "mute": False, "randomSeed": 0}],
        "recordMode": None,
        "soundSourceMetadata": None,
    }

    return {
        "version": PROJECT_VERSION,
        "versionRevision": 0,
        "beatsPerBar": numerator * 4 // denominator,
        "colorIndex": 0,
        "patternIndividualColorIndex": 0,
        "debugInfo": {},
        "duration": pattern_pos + pattern_dur + TAIL_TICKS,
        "extraInfo": {},
        "master": {"gain": 0.0, "externalFxChain": []},
        "pianoCells": 2147483646,
        "tempoBrushOn": False,
        "tempos": [{"bpm": max(1.0, float(song.bpm)), "position": 0,
                    "isLerp": False}],
        "maxBpm": None,
        "minBpm": None,
        "trackCells": 2147483646,
        "tracks": [track],
        "loop": False,
        "loopStart": 0,
        "loopEnd": 7680,
        "mergedPatternIndex": 0,
        "recordPatternIndex": 0,
        "singerLibraryId": "1200593006",
        "timeSignatures": [{"barPos": 0, "numerator": numerator,
                            "denominator": denominator}],
        "trackControlPanelW": 0,
        "svcResults": [],
        "videoTracks": [],
        "markerTracks": [],
    }


def write_acep(song: Song, path: str) -> Path:
    """把 Song 写成 ACE Studio 的 .acep。"""
    project = build_project(song)
    payload = json.dumps(project, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    wrapper = {
        "compressMethod": "zstd",
        "debugInfo": {"os": "windows", "platform": "pc", "version": "10"},
        "salt": "",
        "version": CONTAINER_VERSION,
        "content": base64.b64encode(zstd_store(payload)).decode("ascii"),
    }
    target = Path(path).with_suffix(".acep")
    atomic_write_bytes(target, json.dumps(wrapper).encode("utf-8"))
    return target


FORMAT = Format(
    key="acep",
    label="ACE Studio 工程",
    short="ACE Studio",
    extension=".acep",
    filetype=("ACE Studio 工程", "*.acep"),
    prefix="VocaloidTTS_ACE",
    writer=write_acep,
)
