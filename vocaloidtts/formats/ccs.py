"""CeVIO Creative Studio 工程（.ccs）：XML。

骨架::

    <Scenario>
      <Generation>
        <SVSS><SoundSources><SoundSource .../></SoundSources></SVSS>
      </Generation>
      <Sequence>
        <Scene>
          <Units><Unit ...><Song><Tempo/><Beat/><Score><Note/>…</Score>
                                <Parameter/></Song></Unit></Units>
          <Groups><Group .../></Groups>
        </Scene>
      </Sequence>
    </Scenario>

音符、速度、拍号、分组**全部是属性**，只有容器节点是元素——这是这个格式最容易
写反的地方，写成子元素 CeVIO 会直接当空工程。

格式细节参考 LibreSVIP 的 ``libresvip/plugins/ccs``（MIT，见
THIRD_PARTY_NOTICES.md）。这里只保留**写**方向，手拼 XML，不引 xsdata。

三处单位约定：

- **clock 是 tick 的两倍**（``TICK_RATE = 2.0``，一个四分音符 = 960 clock）；
- **音高拆成八度 + 音级**：``PitchOctave = MIDI // 12 - 1``、``PitchStep = MIDI % 12``；
- 单元和分组都要写 ``Category="SingerSong"``，写错 CeVIO 会当成朗读轨。

简化：只写一条唱轨；不写音高参数（``Parameter`` 留空）；不写词典和 TTS。
"""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import quoteattr

from ..atomicio import atomic_write_text
from ..prosody import Song
from .base import Format, lyric_for, seconds, resample

#: 一个 tick 对应多少个 clock。
CLOCK_PER_TICK = 2

#: 八度偏移：``PitchOctave = MIDI // 12 + OCTAVE_OFFSET``。
OCTAVE_OFFSET = -1

#: 写进工程的版本号。
APP_VERSION = "6.0.0.0"

#: 单元 / 分组的类别。写错会被当成朗读轨。
CATEGORY = "SingerSong"

#: 默认音素（CeVIO 的占位符）。
DEFAULT_PHONEME = "r,a"

#: 默认语言。
LANGUAGE = "Japanese"

#: 占位歌手。
DEFAULT_SINGER_NAME = "VocaloidTTS"
DEFAULT_SINGER_ID = "VocaloidTTS"


def _clock(tick: float) -> int:
    return int(round(tick * CLOCK_PER_TICK))


def _xml_time(total: float) -> str:
    millis = int(round(max(0.0, total) * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def _note_xml(note) -> str:
    midi = max(0, min(127, int(note.midi)))
    return (
        "\t\t\t\t\t<Note"
        f" Clock={quoteattr(str(_clock(note.start)))}"
        f" PitchStep={quoteattr(str(midi % 12))}"
        f" PitchOctave={quoteattr(str(midi // 12 + OCTAVE_OFFSET))}"
        f" Duration={quoteattr(str(max(1, _clock(note.dur))))}"
        f" Lyric={quoteattr(note.lyric or lyric_for(note))}"
        f" Phonetic={quoteattr(note.phonemes or DEFAULT_PHONEME)}/>\n"
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
    name = title or "VocaloidTTS"

    body = "".join(_note_xml(note) for note in notes)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<Scenario Code="VocaloidTTS">\n'
        "\t<Generation>\n"
        f"\t\t<SVSS Version={quoteattr(APP_VERSION)}>\n"
        "\t\t\t<SoundSources>\n"
        f"\t\t\t\t<SoundSource Version={quoteattr(APP_VERSION)}"
        f" Id={quoteattr(DEFAULT_SINGER_ID)}"
        f" Name={quoteattr(DEFAULT_SINGER_NAME)}/>\n"
        "\t\t\t</SoundSources>\n"
        "\t\t</SVSS>\n"
        "\t</Generation>\n"
        f"\t<Sequence Id=\"sequence\">\n"
        "\t\t<Scene Id=\"scene\">\n"
        "\t\t\t<Units>\n"
        f"\t\t\t\t<Unit Version={quoteattr(APP_VERSION)} Id=\"unit\""
        f" Group=\"group\" StartTime=\"00:00:00.000\""
        f" Duration={quoteattr(_xml_time(seconds(song, end)))}"
        f" Category={quoteattr(CATEGORY)}"
        f" CastId={quoteattr(DEFAULT_SINGER_ID)}"
        f" Language={quoteattr(LANGUAGE)}>\n"
        f"\t\t\t\t\t<Song Version={quoteattr(APP_VERSION)} CommonKeys=\"False\">\n"
        "\t\t\t\t\t\t<Tempo>\n"
        f"\t\t\t\t\t\t\t<Sound Clock=\"0\" Tempo={quoteattr(str(max(1.0, float(song.bpm))))}/>\n"
        "\t\t\t\t\t\t</Tempo>\n"
        "\t\t\t\t\t\t<Beat>\n"
        f"\t\t\t\t\t\t\t<Time Clock=\"0\" Beats=\"{numerator}\" BeatType=\"{denominator}\"/>\n"
        "\t\t\t\t\t\t</Beat>\n"
        "\t\t\t\t\t\t<Score>\n"
        f"{body}"
        "\t\t\t\t\t\t</Score>\n"
        "\t\t\t\t\t\t<Parameter/>\n"
        "\t\t\t\t\t</Song>\n"
        "\t\t\t\t</Unit>\n"
        "\t\t\t</Units>\n"
        "\t\t\t<Groups ActiveGroup=\"group\">\n"
        f"\t\t\t\t<Group Version={quoteattr(APP_VERSION)} Id=\"group\""
        f" Category={quoteattr(CATEGORY)} Name={quoteattr(name)}"
        " Color=\"#7f7f7f\" Volume=\"1\" Pan=\"0\""
        " IsSolo=\"False\" IsMuted=\"False\""
        f" CastId={quoteattr(DEFAULT_SINGER_ID)}"
        f" Language={quoteattr(LANGUAGE)}/>\n"
        "\t\t\t</Groups>\n"
        "\t\t</Scene>\n"
        "\t</Sequence>\n"
        "</Scenario>\n"
    )


def write_ccs(song: Song, path: str) -> Path:
    """把 Song 写成 CeVIO Creative Studio 的 .ccs。"""
    target = Path(path).with_suffix(".ccs")
    atomic_write_text(target, build_xml(song))
    return target


FORMAT = Format(
    key="ccs",
    label="CeVIO 工程",
    short="CeVIO",
    extension=".ccs",
    filetype=("CeVIO Creative Studio 工程", "*.ccs"),
    prefix="VocaloidTTS_CeVIO",
    writer=write_ccs,
)
