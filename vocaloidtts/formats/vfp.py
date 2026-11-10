"""VOX Factory 工程（.vfp）：一个 zip 包，里面是 ``project.json`` 和
``resources/`` 音频目录。

结构是「键值表」式的：``trackBank`` / ``clipBank`` / ``noteBank`` 都是
``{key: 对象}``，另外用 ``*Order`` 数组记录顺序。所以同一个对象要在两处出现，
只写一处编辑器就看不到。

格式细节参考 LibreSVIP 的 ``libresvip/plugins/vfp``（MIT，见
THIRD_PARTY_NOTICES.md）。这里只保留**写**方向，简化之处：

- 只写一条唱轨，不写音频轨（``resources/`` 目录留空）；
- 不写音高曲线（``pitchBends`` 留空），交给 VOX Factory 自己算；
- 键名用固定的 ``vtts-`` 前缀，不用随机串——导出结果可复现，测试也好写。

时间有两种：``ticks`` / ``durationTicks`` 是 480 tick / 四分音符，
``time`` / ``duration`` 是秒。两种都要写，缺一个编辑器就没法对齐。
"""
from __future__ import annotations

import io
import json
import math
import zipfile
from pathlib import Path

from ..atomicio import atomic_write_bytes
from ..prosody import Song
from .base import Format, lyric_for, seconds, resample

#: 工程版本号。
PROJECT_VERSION = "0.12.0"

#: 键名前缀。LibreSVIP 用随机串，这里用固定值，保证同一份 Song 导出同样的字节。
PREFIX = "vtts"

#: 一个 clip 覆盖多少个四分音符。
CLIP_QUARTERS = 32

#: 音频视图的默认参数。
AUDIO_VIEW = {
    "view": "waveform",
    "colormap": "Heated Metal",
    "window": "Hann",
    "windowSize": 1024,
    "hopSize": 256,
    "fMin": 27.5,
    "fMax": None,
    "levelMin": None,
    "levelMax": None,
    "levelScale": "dB",
    "numBins": 230,
    "binsPerOctave": 24,
}


def _note(note, song: Song) -> dict:
    return {
        "time": round(seconds(song, note.start), 6),
        "midi": max(0, min(127, int(note.midi))),
        "name": lyric_for(note),
        # note.lyric 本来就是拼音
        "syllable": note.lyric or lyric_for(note),
        "ticks": max(0, int(note.start)),
        "durationTicks": max(1, int(note.dur)),
        "duration": round(seconds(song, note.dur), 6),
        "velocity": 1,
        "pitchBends": [],
    }


def build_project(song: Song, title: str = "VocaloidTTS") -> dict:
    song = resample(song)
    notes = [note for note in song.notes if note.dur > 0]
    if not notes:
        raise ValueError("没有可导出的音符")

    numerator = max(1, min(16, int(song.numerator)))
    denominator = int(song.denominator)
    if denominator not in (2, 4, 8, 16):
        denominator = 4

    note_bank = {f"{PREFIX}-no{index}": _note(note, song)
                 for index, note in enumerate(notes)}
    note_order = list(note_bank)

    max_quarter = max(note.start + note.dur for note in notes) / 480.0
    clip_count = max(1, math.ceil(max_quarter / CLIP_QUARTERS))
    clip_bank = {}
    for index in range(clip_count):
        clip_bank[f"{PREFIX}-cl{index}"] = {
            "type": "vocal",
            "lengthType": "quarter",
            "name": "",
            "startQuarter": CLIP_QUARTERS * index,
            "offsetQuarter": CLIP_QUARTERS * index,
            "length": CLIP_QUARTERS,
            "useSource": True,
            "audioDataKey": None,
            "audioDataOrder": [],
            "audioDataQuarter": 0,
            # LibreSVIP 的写法：每个 clip 都挂全量 noteBank
            "noteBank": note_bank,
            "noteOrder": note_order,
            "pitchPointBank": {},
            "pitchPointOrder": [],
            "nextNoteIndex": 0,
            "pinnedAudioDataOrder": [],
            "metadata": None,
            "sourceAudioDataKey": None,
            "processKey": None,
        }

    track = {
        "type": "vocal",
        "name": title or "VocaloidTTS",
        "instrument": None,
        "h": 3,
        "color": "#7878f1",
        "volume": 1.0,
        "pan": 0.0,
        "solo": False,
        "mute": False,
        "arm": False,
        "clipOrder": list(clip_bank),
        "deviceBank": {},
        "deviceOrder": [],
        "devicePreset": None,
        "audioViewProperty": dict(AUDIO_VIEW),
        "clipBank": clip_bank,
    }

    return {
        "version": PROJECT_VERSION,
        "tempo": max(1.0, float(song.bpm)),
        "timeSignature": [numerator, denominator],
        "loop": None,
        "projectName": title or "VocaloidTTS",
        "trackBank": {f"{PREFIX}-tr0": track},
        "trackOrder": [f"{PREFIX}-tr0"],
        "selectedTrackBank": [],
        "selectedClipBank": [],
        "selectedNoteBank": [],
        "audioDataBank": {},
    }


def write_vfp(song: Song, path: str) -> Path:
    """把 Song 写成 VOX Factory 的 .vfp。"""
    project = build_project(song)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("project.json",
                         json.dumps(project, ensure_ascii=False))
        # 没有音频轨，但 resources/ 目录仍然要存在
        archive.writestr("resources/", "")
    target = Path(path).with_suffix(".vfp")
    atomic_write_bytes(target, buffer.getvalue())
    return target


FORMAT = Format(
    key="vfp",
    label="VOX Factory 工程",
    short="VOX Factory",
    extension=".vfp",
    filetype=("VOX Factory 工程", "*.vfp"),
    prefix="VocaloidTTS_VOXFactory",
    writer=write_vfp,
)
