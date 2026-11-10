"""VOCALOID2 序列（.vsq）：一个标准 MIDI 文件，里面装着文本格式的工程。

外层是 SMF（format 1，两条轨道）：

- 轨道 0 是「Master Track」，只有轨道名、速度、拍号和结束标记；
- 轨道 1 是一串 **文本事件**（meta 0x01），内容拼起来才是 VSQ 的正文。

正文是 ``[Common]`` / ``[Master]`` / ``[Mixer]`` / ``[EventList]`` /
``[ID#nnnn]`` 这样的 INI 风格段落。每段文本前面加 ``DM:nnnn:`` 前缀，按
127 字节切成多条文本事件——单条事件塞不下整份工程。

格式细节参考 LibreSVIP 的 ``libresvip/plugins/vsq``（MIT，见
THIRD_PARTY_NOTICES.md）。这里只保留**写**方向，简化之处：

- 只写一条唱轨；``[Master]`` / ``[Mixer]`` 按单轨写；
- 参数曲线只写 PIT / PBS / DYN / BRE / BRI 五条，不写 GenderFactor
  （那个通道的取值方向存疑，宁可不写也不写错）；
- 歌词写拼音、音素写 X-SAMPA，和 VSQX 的口径一致。

时间上加一个前导小节（``PreMeasure=1``，1920 tick），所以事件表里的 tick 是
音符位置加 1920。
"""
from __future__ import annotations

from pathlib import Path

from ..atomicio import atomic_write_bytes
from ..prosody import Song
from ..voicebank import Voicebank
from .base import Format, lyric_for
from .mid import chunk, meta_event, vlq

#: 和内部 tick 一致。
TICKS_PER_QUARTER = 480

#: 前导小节数。
PRE_MEASURE = 1

#: 前导小节的 tick 数（4/4 下）。
PREFIX_TICKS = PRE_MEASURE * TICKS_PER_QUARTER * 4

#: 单条文本事件最多装多少字节正文。
TEXT_CHUNK = 0x7F - len("DM:0000:")

#: 参数曲线：(Song.controls 的键, VSQ 段名)。
CURVES = (
    ("P", "PitchBendBPList"),
    ("S", "PitchBendSensBPList"),
    ("DYN", "DynamicsBPList"),
    ("BRE", "BreathinessBPList"),
    ("BRI", "BrightnessBPList"),
)


def _split_bytes(text: str, limit: int) -> list[str]:
    """按 UTF-8 字节数切分，保证每段编码后不超过 ``limit``。"""
    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for char in text:
        width = len(char.encode("utf-8"))
        if size + width > limit and current:
            pieces.append("".join(current))
            current, size = [], 0
        current.append(char)
        size += width
    if current:
        pieces.append("".join(current))
    return pieces


def _note_sections(notes) -> tuple[list[str], list[str]]:
    """返回 (音符段落, 歌词句柄段落)。"""
    note_lines: list[str] = []
    lyric_lines: list[str] = []
    for index, note in enumerate(notes, start=1):
        number = f"{index:04d}"
        note_lines.extend([
            f"[ID#{number}]",
            "Type=Anote",
            f"Length={max(1, int(note.dur))}",
            f"Note#={max(0, min(127, int(note.midi)))}",
            "Dynamics=64",
            "PMBendDepth=0",
            "PMBendLength=0",
            "PMbPortamentoUse=0",
            "DEMdecGainRate=0",
            "DEMaccent=0",
            f"LyricHandle=h#{number}",
        ])
        lyric_lines.extend([
            f"[h#{number}]",
            f"""L0="{note.lyric or lyric_for(note)}","{note.phonemes or 'a'}",0.000000,64,0,0""",
        ])
    return note_lines, lyric_lines


def _curve_sections(song: Song) -> list[str]:
    lines: list[str] = []
    for key, name in CURVES:
        points = [(t, v) for t, v in sorted(song.controls.get(key) or [],
                                            key=lambda pair: pair[0]) if t >= 0]
        if not points:
            continue
        lines.append(f"[{name}]")
        lines.extend(f"{int(t) + PREFIX_TICKS}={int(v)}" for t, v in points)
    return lines


def build_text(song: Song, voicebank: Voicebank, title: str = "VocaloidTTS") -> str:
    notes = [note for note in song.notes if note.dur > 0]
    if not notes:
        raise ValueError("没有可导出的音符")

    note_lines, lyric_lines = _note_sections(notes)
    result = [
        "[Common]",
        "Version=DSB301",
        f"Name={title or 'VocaloidTTS'}",
        "Color=181,162,123",
        "DynamicsMode=1",
        "PlayMode=1",
        "[Master]",
        f"PreMeasure={PRE_MEASURE}",
        "[Mixer]",
        "MasterFeder=0",
        "MasterPanpot=0",
        "MasterMute=0",
        "OutputMode=0",
        "Tracks=1",
        "Feder0=0",
        "Panpot0=0",
        "Mute0=0",
        "Solo0=0",
        "[EventList]",
        "0=ID#0000",
    ]
    result.extend(
        f"{int(note.start) + PREFIX_TICKS}=ID#{index:04d}"
        for index, note in enumerate(notes, start=1))
    result.append(f"{int(max(n.start + n.dur for n in notes)) + PREFIX_TICKS}=EOS")
    result.extend(["[ID#0000]", "Type=Singer", "IconHandle=h#0000"])
    result.extend(note_lines)
    result.extend([
        "[h#0000]",
        "IconID=$07010000",
        f"IDS={voicebank.name}",
        "Original=0",
        "Caption=",
        "Length=1",
        "Language=0",
        "Program=0",
    ])
    result.extend(lyric_lines)
    result.extend(_curve_sections(song))
    return "\n".join(result)


def build_file(song: Song, voicebank: Voicebank, title: str = "VocaloidTTS") -> bytes:
    text = build_text(song, voicebank, title=title)
    pieces = _split_bytes(text, TEXT_CHUNK)

    master = bytearray()
    master += vlq(0) + meta_event(0x03, b"Master Track")
    bpm = max(1.0, float(song.bpm))
    master += vlq(0) + meta_event(0x51, int(round(60_000_000 / bpm)).to_bytes(3, "big"))
    numerator = max(1, min(16, int(song.numerator)))
    denominator = int(song.denominator)
    if denominator not in (2, 4, 8, 16):
        denominator = 4
    denominator_power = {2: 1, 4: 2, 8: 3, 16: 4}[denominator]
    master += vlq(0) + meta_event(0x58, bytes([numerator, denominator_power, 24, 8]))
    master += vlq(0) + meta_event(0x2F, b"")

    voice = bytearray()
    for index, piece in enumerate(pieces):
        payload = f"DM:{index:04d}:".encode("ascii") + piece.encode("utf-8")
        voice += vlq(0) + meta_event(0x01, payload)
    voice += vlq(0) + meta_event(0x2F, b"")

    header = chunk(b"MThd", (1).to_bytes(2, "big") + (2).to_bytes(2, "big")
                   + TICKS_PER_QUARTER.to_bytes(2, "big"))
    return header + chunk(b"MTrk", bytes(master)) + chunk(b"MTrk", bytes(voice))


def write_vsq(song: Song, path: str, voicebank: Voicebank,
              title: str = "VocaloidTTS") -> Path:
    """把 Song 写成 VOCALOID2 的 .vsq。"""
    target = Path(path).with_suffix(".vsq")
    atomic_write_bytes(target, build_file(song, voicebank, title=title))
    return target


FORMAT = Format(
    key="vsq",
    label="VOCALOID2 序列",
    short="VSQ",
    extension=".vsq",
    filetype=("VOCALOID2 序列", "*.vsq"),
    prefix="VocaloidTTS_VSQ",
    writer=write_vsq,
    needs_voicebank=True,
)
