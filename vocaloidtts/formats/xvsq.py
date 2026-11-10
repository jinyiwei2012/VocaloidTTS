"""Cadencii 工程（.xvsq）：XML。

根节点 ``<VsqFileEx>``，子元素顺序固定::

    VsqFileEx
    ├ Track → VsqTrack…          第 0 条是空的「主控轨」，唱轨从第 1 条开始
    ├ TempoTable  → TempoTableEntry[Clock/Tempo/Time]
    ├ TimesigTable → TimeSigTableEntry[Clock/Numerator/Denominator/BarCount]
    ├ TotalClocks
    ├ Master(PreMeasure) / Mixer(Slave) / AttachedCurves / BgmFiles
    └ cacheDir / config

唱轨的结构::

    VsqTrack → MetaText
      ├ Common  (Version / Name / Color / DynamicsMode / PlayMode / LastPlayMode)
      ├ Events → Events → VsqEvent[InternalID, Clock, ID, UstEvent]
      ├ PIT / PBS / DYN / BRE / BRI / CLE
      ├ reso1..4FreqBPList / reso1..4BWBPList / reso1..4AmpBPList
      └ harmonics / fx2depth / GEN / POR / OPE

音符写在 ``VsqEvent/ID`` 里（元素名就叫 ``<ID>``）：``type`` / ``Note`` /
``Dynamics`` / … / ``LyricHandle`` / … / ``Length``。歌词再下两层到
``ID/LyricHandle/L0``（``Phrase`` 歌词、``PhoneticSymbol`` 音素），
``LyricHandle`` 还有 ``Index`` 和 ``Trailing``。每条曲线是 ``VsqBPList``：
``Data``（``x=y,x=y`` 串）+ ``Default`` / ``Name`` / ``Maximum`` / ``Minimum``。

``Track`` 里第 0 条 ``VsqTrack`` 是主控轨，读的时候会被跳过——所以只写一条唱轨
也必须先垫一个空的主控轨，否则整个工程会被当成「没有唱轨」。

格式细节参考 LibreSVIP 的 ``libresvip/plugins/xvsq``（MIT，见
THIRD_PARTY_NOTICES.md），元素顺序和默认值取自它的 xsdata/pydantic 模型。
这里只保留**写**方向，手拼 XML，不引 xsdata。

简化之处（都是「少写」而不是「写错」）：

- 只写一条唱轨，不写音频轨（``BgmFiles`` 留空）；
- ``PIT`` / ``PBS`` / ``DYN`` 等曲线只写元信息（``Default`` / ``Name`` /
  上下限），``Data`` 留空——Cadencii 的音高编辑有两套模式，写错比不写更糟，
  留给用户在编辑器里拉；
- 不写 ``VibratoHandle`` / ``NoteHeadHandle`` / ``IconDynamicsHandle``。

时间上加一个前导小节（``PreMeasure=1``，1920 tick），所以事件时钟是音符位置
加 1920。速度用 MIDI 的「每四分音符微秒」表示。
"""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from ..atomicio import atomic_write_text
from ..prosody import Song
from .base import Format, lyric_for, resample

#: 前导小节的 tick 数（4/4 下）。
PREFIX_TICKS = 1920

#: 写进 Common 的版本号。
VSQ_VERSION = "DSB301"

#: 默认轨道颜色。
DEFAULT_COLOR = "179,181,123"

#: 缩进单位。
TAB = "\t"

#: 占位歌手名。
DEFAULT_SINGER = "VocaloidTTS"

#: MetaText 里必须出现的参数曲线：(元素名, 内部名, 默认值, 上限, 下限)。
#: 顺序就是 XML 里的出现顺序，和 LibreSVIP 的 VsqMetaText 字段顺序一致。
BP_LISTS = (
    ("PIT", "pit", 0, 8191, -8192),
    ("PBS", "pbs", 2, 24, 0),
    ("DYN", "dyn", 64, 127, 0),
    ("BRE", "bre", 0, 127, 0),
    ("BRI", "bri", 0, 127, 0),
    ("CLE", "cle", 0, 127, 0),
    ("reso1FreqBPList", "reso1freq", 64, 127, 0),
    ("reso2FreqBPList", "reso2freq", 64, 127, 0),
    ("reso3FreqBPList", "reso3freq", 64, 127, 0),
    ("reso4FreqBPList", "reso4freq", 64, 127, 0),
    ("reso1BWBPList", "reso1bw", 64, 127, 0),
    ("reso2BWBPList", "reso2bw", 64, 127, 0),
    ("reso3BWBPList", "reso3bw", 64, 127, 0),
    ("reso4BWBPList", "reso4bw", 64, 127, 0),
    ("reso1AmpBPList", "reso1amp", 64, 127, 0),
    ("reso2AmpBPList", "reso2amp", 64, 127, 0),
    ("reso3AmpBPList", "reso3amp", 64, 127, 0),
    ("reso4AmpBPList", "reso4amp", 64, 127, 0),
    ("harmonics", "harmonics", 64, 127, 0),
    ("fx2depth", "fx2depth", 64, 127, 0),
    ("GEN", "gen", 64, 127, 0),
    ("POR", "por", 64, 127, 0),
    ("OPE", "ope", 127, 127, 0),
)


def _clock(tick: float) -> int:
    return int(round(tick)) + PREFIX_TICKS


def _tag(depth: int, name: str, text: object) -> str:
    return f"{TAB * depth}<{name}>{text}</{name}>\n"


def _event_xml(internal_id: int, clock: int, body: str) -> str:
    return (
        f"{TAB * 6}<VsqEvent>\n"
        + _tag(7, "InternalID", internal_id)
        + _tag(7, "Clock", clock)
        + body
        + f"{TAB * 6}</VsqEvent>\n"
    )


def _ust_event_xml() -> str:
    """``UstEvent`` 是 VsqEvent 的必填子元素，全用默认值。"""
    fields = (
        ("Index", 0),
        ("Note", -1),
        ("Intensity", 100),
        ("PBType", -1),
        ("Tempo", -1),
        ("PreUtterance", 0),
        ("VoiceOverlap", 0),
        ("Moduration", 100),
        ("StartPoint", 0),
        ("Length", 0),
    )
    return (f"{TAB * 7}<UstEvent>\n"
            + "".join(_tag(8, name, value) for name, value in fields)
            + f"{TAB * 7}</UstEvent>\n")


def _singer_event_xml() -> str:
    body = (
        f"{TAB * 7}<ID>\n"
        + _tag(8, "type", "Singer")
        + f"{TAB * 8}<IconHandle>\n"
        + _tag(9, "Caption", "")
        + _tag(9, "IconID", "$07010000")
        + _tag(9, "IDS", DEFAULT_SINGER)
        + _tag(9, "Index", 0)
        + _tag(9, "Length", 1)
        + _tag(9, "Original", 0)
        + _tag(9, "Program", 0)
        + _tag(9, "Language", 0)
        + f"{TAB * 8}</IconHandle>\n"
        + _tag(8, "Note", 0)
        + _tag(8, "Length", 0)
        + f"{TAB * 7}</ID>\n"
        + _ust_event_xml()
    )
    return _event_xml(0, 0, body)


def _note_event_xml(internal_id: int, note) -> str:
    midi = max(0, min(127, int(note.midi)))
    phrase = escape(note.lyric or lyric_for(note))
    phonetic = escape(note.phonemes or "")
    lyric_lines = [_tag(10, "Phrase", phrase)]
    if phonetic:
        # 顺序是 Phrase / UnknownFloat / PhoneticSymbolProtected /
        # ConsonantAdjustment / PhoneticSymbol——音素在最后，不是紧跟着歌词。
        lyric_lines += [
            _tag(10, "UnknownFloat", 1),
            _tag(10, "PhoneticSymbolProtected", "false"),
            _tag(10, "ConsonantAdjustment", 0),
            _tag(10, "PhoneticSymbol", phonetic),
        ]
    body = (
        f"{TAB * 7}<ID>\n"
        + _tag(8, "type", "Anote")
        + _tag(8, "Note", midi)
        + _tag(8, "Dynamics", 64)
        + _tag(8, "PMBendDepth", 8)
        + _tag(8, "PMBendLength", 0)
        + _tag(8, "PMbPortamentoUse", 3)
        + _tag(8, "DEMdecGainRate", 50)
        + _tag(8, "DEMaccent", 50)
        + f"{TAB * 8}<LyricHandle>\n"
        + f"{TAB * 9}<L0>\n"
        + "".join(lyric_lines)
        + f"{TAB * 9}</L0>\n"
        + _tag(9, "Index", 0)
        + f"{TAB * 9}<Trailing/>\n"
        + f"{TAB * 8}</LyricHandle>\n"
        + _tag(8, "VibratoDelay", 0)
        + _tag(8, "pMeanOnsetFirstNote", 10)
        + _tag(8, "vMeanNoteTransition", 12)
        + _tag(8, "d4mean", 24)
        + _tag(8, "pMeanEndingNote", 12)
        + _tag(8, "Length", max(1, int(note.dur)))
        + f"{TAB * 7}</ID>\n"
        + _ust_event_xml()
    )
    return _event_xml(internal_id, _clock(note.start), body)


def _bp_list_xml(name: str, bp_name: str, default: int,
                 maximum: int, minimum: int) -> str:
    return (
        f"{TAB * 4}<{name}>\n"
        f"{TAB * 5}<Data/>\n"
        + _tag(5, "Default", default)
        + _tag(5, "Name", bp_name)
        + _tag(5, "Maximum", maximum)
        + _tag(5, "Minimum", minimum)
        + f"{TAB * 4}</{name}>\n"
    )


def _meta_text_xml(name: str, events: str) -> str:
    curves = "".join(_bp_list_xml(*entry) for entry in BP_LISTS)
    return (
        f"{TAB * 2}<MetaText>\n"
        f"{TAB * 3}<Common>\n"
        + _tag(4, "Version", VSQ_VERSION)
        + _tag(4, "Name", escape(name))
        + _tag(4, "Color", DEFAULT_COLOR)
        + _tag(4, "DynamicsMode", 1)
        + _tag(4, "PlayMode", 1)
        + _tag(4, "LastPlayMode", 1)
        + f"{TAB * 3}</Common>\n"
        + f"{TAB * 3}<Events>\n"
        + f"{TAB * 4}<Events>\n"
        + events
        + f"{TAB * 4}</Events>\n"
        + f"{TAB * 3}</Events>\n"
        + curves
        + f"{TAB * 2}</MetaText>\n"
    )


def build_xml(song: Song, title: str = "VocaloidTTS") -> str:
    song = resample(song)
    notes = [note for note in song.notes if note.dur > 0]
    if not notes:
        raise ValueError("没有可导出的音符")

    numerator = max(1, min(16, int(song.numerator)))
    denominator = int(song.denominator)
    if denominator not in (2, 4, 8, 16):
        denominator = 4
    end = max(note.start + note.dur for note in notes)
    bpm = max(1.0, float(song.bpm))
    tempo = int(round(60_000_000 / bpm))
    name = title or "VocaloidTTS"

    events = _singer_event_xml() + "".join(
        _note_event_xml(index, note) for index, note in enumerate(notes, start=1))

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<VsqFileEx>\n"
        f"{TAB}<Track>\n"
        # 第 0 条是主控轨，读的时候会被跳过；不写它唱轨就会被当成主控轨
        f"{TAB * 2}<VsqTrack/>\n"
        f"{TAB * 2}<VsqTrack>\n"
        f"{_meta_text_xml(name, events)}"
        f"{TAB * 2}</VsqTrack>\n"
        f"{TAB}</Track>\n"
        f"{TAB}<TempoTable>\n"
        f"{TAB * 2}<TempoTableEntry>\n"
        + _tag(3, "Clock", 0)
        + _tag(3, "Tempo", tempo)
        + _tag(3, "Time", 0)
        + f"{TAB * 2}</TempoTableEntry>\n"
        f"{TAB}</TempoTable>\n"
        f"{TAB}<TimesigTable>\n"
        f"{TAB * 2}<TimeSigTableEntry>\n"
        + _tag(3, "Clock", 0)
        + _tag(3, "Numerator", numerator)
        + _tag(3, "Denominator", denominator)
        + _tag(3, "BarCount", 0)
        + f"{TAB * 2}</TimeSigTableEntry>\n"
        f"{TAB}</TimesigTable>\n"
        + _tag(1, "TotalClocks", _clock(end))
        + f"{TAB}<Master>\n"
        + _tag(2, "PreMeasure", 1)
        + f"{TAB}</Master>\n"
        + f"{TAB}<Mixer>\n"
        + _tag(2, "MasterFeder", 0)
        + _tag(2, "MasterPanpot", 0)
        + _tag(2, "MasterMute", 0)
        + _tag(2, "OutputMode", 0)
        + f"{TAB * 2}<Slave/>\n"
        + f"{TAB}</Mixer>\n"
        + f"{TAB}<AttachedCurves>\n"
        + f"{TAB * 2}<Curves/>\n"
        + f"{TAB}</AttachedCurves>\n"
        + f"{TAB}<BgmFiles/>\n"
        + f"{TAB}<cacheDir/>\n"
        + f"{TAB}<config>\n"
        + _tag(2, "SamplingRate", 44100)
        + _tag(2, "WaveFileOutputChannel", 2)
        + _tag(2, "WaveFileOutputFromMasterTrack", "false")
        + _tag(2, "StartMarker", 0)
        + _tag(2, "StartMarkerEnabled", "false")
        + _tag(2, "EndMarker", 0)
        + _tag(2, "EndMarkerEnabled", "false")
        + f"{TAB}</config>\n"
        "</VsqFileEx>\n"
    )


def write_xvsq(song: Song, path: str) -> Path:
    """把 Song 写成 Cadencii 的 .xvsq。"""
    target = Path(path).with_suffix(".xvsq")
    atomic_write_text(target, build_xml(song))
    return target


FORMAT = Format(
    key="xvsq",
    label="Cadencii 工程",
    short="Cadencii",
    extension=".xvsq",
    filetype=("Cadencii 工程", "*.xvsq"),
    prefix="VocaloidTTS_Cadencii",
    writer=write_xvsq,
)
