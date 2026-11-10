"""VoiSona 手机版工程（.tsmsln）：和 ``.tssln`` 同一套 JUCE ValueTree 容器。

和桌面版的差别只有三处：

- 根节点叫 ``MobileSongEditor``，不是 ``TSSolution``；
- 版本号默认 ``1.12.1.0``；
- 轨道少一层：``Tracks`` 直接挂唱轨，桌面版是 ``Tracks`` → ``Track`` → 唱轨；
  桌面版独有的 ``PlayControl`` / ``GUIStatus`` 也不写。

容器和音符的写法完全复用 :mod:`vocaloidtts.formats.tssln`。
"""
from __future__ import annotations

from pathlib import Path

from ..atomicio import atomic_write_bytes
from ..prosody import Song
from .base import Format
from .tssln import build_file as _build_voisona

#: 手机版的根节点名。
ROOT_NAME = "MobileSongEditor"

#: 手机版的版本号。
APP_VERSION = "1.12.1.0"


def build_file(song: Song, title: str = "VocaloidTTS") -> bytes:
    return _build_voisona(song, title, root_name=ROOT_NAME, version=APP_VERSION,
                          nested_track=False, with_shell=False)


def write_tsmsln(song: Song, path: str) -> Path:
    """把 Song 写成 VoiSona 手机版的 .tsmsln。"""
    target = Path(path).with_suffix(".tsmsln")
    atomic_write_bytes(target, build_file(song))
    return target


FORMAT = Format(
    key="tsmsln",
    label="VoiSona 手机版工程",
    short="VoiSona Mobile",
    extension=".tsmsln",
    filetype=("VoiSona 手机版工程", "*.tsmsln"),
    prefix="VocaloidTTS_VoiSonaMobile",
    writer=write_tsmsln,
)
