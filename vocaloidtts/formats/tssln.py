"""VoiSona 工程（.tssln）：JUCE ValueTree 二进制。

外层是一个名为 ``TSSolution`` 的节点::

    TSSolution
      ├ attrs: VersionOfAppFileSaved
      ├ PlayControl      (Loop / LoopStart / LoopEnd / PlayPosition)
      ├ Tracks
      │   └ Track
      │       └ Track    ← 每条唱轨，注意有两层同名节点
      │           ├ attrs: Name / State / Volume / Pan / Type / PluginData
      │           └ PluginData 是一个 **二进制变体**，里面又是整棵 ValueTree
      └ GUIStatus        (ScaleX / ScaleY)

``PluginData`` 里那棵树叫 ``StateInformation``，再往下是 ``Song`` →
``Tempo`` / ``Beat`` / ``Score``，音符在 ``Score`` 里。

容器细节见 :mod:`vocaloidtts.formats.juce`。格式细节参考 LibreSVIP 的
``libresvip/plugins/tssln``（MIT，见 THIRD_PARTY_NOTICES.md）。

三处单位约定：

- **clock 是 tick 的两倍**（``TICK_RATE = 2.0``，一个四分音符 = 960 clock）；
- **音高拆成八度 + 音级**：``PitchOctave = MIDI // 12 - 1``、
  ``PitchStep = MIDI % 12``，不是直接写 MIDI；
- 拍号里 ``Beats`` 是分子、``BeatType`` 是分母。

简化：只写一条唱轨；不写音高参数（``Parameter`` / ``LogF0``）和音频轨。
"""
from __future__ import annotations

from pathlib import Path

from ..atomicio import atomic_write_bytes
from ..prosody import Song
from . import juce
from .base import Format, lyric_for

#: 一个 tick 对应多少个 clock。
CLOCK_PER_TICK = 2

#: 八度偏移：``PitchOctave = MIDI // 12 + OCTAVE_OFFSET``。
OCTAVE_OFFSET = -1

#: 写进工程的版本号。低于 1.8 会被 VoiSona 拒绝。
APP_VERSION = "1.8.0.17"

#: 唱轨类型。
TRACK_TYPE_SINGING = 0


def _clock(tick: float) -> int:
    return int(round(tick * CLOCK_PER_TICK))


def _note_node(note) -> bytes:
    midi = max(0, min(127, int(note.midi)))
    return juce.node("Note", attrs=(
        ("Clock", _clock(note.start)),
        ("Duration", max(1, _clock(note.dur))),
        ("PitchStep", midi % 12),
        ("PitchOctave", midi // 12 + OCTAVE_OFFSET),
        ("Lyric", note.lyric or lyric_for(note)),
        ("Syllabic", 0),
        ("Phoneme", note.phonemes or "a"),
    ))


def _state_information(song: Song, version: str = APP_VERSION) -> bytes:
    numerator = max(1, min(16, int(song.numerator)))
    denominator = int(song.denominator)
    if denominator not in (2, 4, 8, 16):
        denominator = 4

    tempo_node = juce.node("Tempo", children=(
        juce.node("Sound", attrs=(("Clock", 0),
                                  ("Tempo", max(1.0, float(song.bpm))))),
    ))
    beat_node = juce.node("Beat", children=(
        juce.node("Time", attrs=(("Clock", 0), ("Beats", numerator),
                                 ("BeatType", denominator))),
    ))
    score_node = juce.node("Score", children=tuple(
        _note_node(note) for note in song.notes if note.dur > 0))
    song_node = juce.node("Song", children=(tempo_node, beat_node, score_node))
    return juce.node("StateInformation", attrs=(
        ("TempoSync", False),
        ("VersionOfAppFileSaved", version),
    ), children=(song_node,))


def build_file(song: Song, title: str = "VocaloidTTS", *,
               root_name: str = "TSSolution", version: str = APP_VERSION,
               nested_track: bool = True, with_shell: bool = True) -> bytes:
    notes = [note for note in song.notes if note.dur > 0]
    if not notes:
        raise ValueError("没有可导出的音符")

    track_item = juce.node("Track", attrs=(
        ("Name", title or "VocaloidTTS"),
        ("State", 0),
        ("Volume", 0.0),
        ("Pan", 0.0),
        ("Type", TRACK_TYPE_SINGING),
        ("PluginData", _state_information(song, version)),
    ))
    play_control = juce.node("PlayControl", attrs=(
        ("Loop", False),
        ("LoopStart", 0.0),
        ("LoopEnd", 0.0),
        ("PlayPosition", 0.0),
    ))
    if nested_track:
        # 桌面版有两层同名 Track：外层是轨道容器，内层才是唱轨
        tracks = juce.node("Tracks", children=(juce.node("Track", children=(track_item,)),))
    else:
        tracks = juce.node("Tracks", children=(track_item,))
    gui_status = juce.node("GUIStatus", attrs=(("ScaleX", 100.0), ("ScaleY", 100.0)))

    children = [tracks]
    if with_shell:
        # PlayControl / GUIStatus 是桌面版独有的节点，手机版没有
        children = [play_control, tracks, gui_status]
    return juce.node(root_name, attrs=(
        ("VersionOfAppFileSaved", version),
    ), children=tuple(children))


def write_tssln(song: Song, path: str) -> Path:
    """把 Song 写成 VoiSona 的 .tssln。"""
    target = Path(path).with_suffix(".tssln")
    atomic_write_bytes(target, build_file(song))
    return target


FORMAT = Format(
    key="tssln",
    label="VoiSona 工程",
    short="VoiSona",
    extension=".tssln",
    filetype=("VoiSona 工程", "*.tssln"),
    prefix="VocaloidTTS_VoiSona",
    writer=write_tssln,
)
