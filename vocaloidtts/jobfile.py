"""Compact job file shared by VocaloidTTS and the V4 Job Plugin."""
from __future__ import annotations

from pathlib import Path

from .atomicio import atomic_write_text
from .paths import localappdata_dir
from .prosody import Song


def default_job_path() -> Path:
    return localappdata_dir() / "vocaloidtts_job.txt"


def _field(value: str) -> str:
    """把会打乱列数的字符换成空格。

    NOTE 行是 TAB 分隔的，插件按 TAB 切分；歌词或音素里出现 TAB/换行会让
    列数错位，插件把后半截歌词当成音素（实测 "tab\there" 变成
    lyric="tab"、phonemes="here\ta"）。
    """
    return (str(value).replace("\t", " ").replace("\r", " ")
            .replace("\n", " "))


def write_job(song: Song, path: str | Path | None = None,
              title: str = "VocaloidTTS") -> Path:
    path = Path(path) if path else default_job_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# VocaloidTTS job v2",
        f"TITLE\t{title}",
        f"BASE\t{song.options.pitch}",
        f"PBS\t{song.options.pbs}",
        f"TOTAL\t{song.total_ticks}",
    ]
    for n in song.notes:
        accent = int(max(30, min(100, 38 + 42 * n.syl.stress * song.options.energy)))
        lines.append(f"NOTE\t{n.start}\t{n.dur}\t{n.midi}\t{n.velocity}"
                     f"\t{accent}\t{_field(n.lyric)}\t{_field(n.phonemes)}")
    for cid in ("S", "P", "DYN", "BRE", "BRI", "CLE", "OPE", "GEN", "POR"):
        jid = {"S": "PBS", "P": "PIT"}.get(cid, cid)
        for t, v in sorted(song.controls.get(cid, []), key=lambda x: x[0]):
            lines.append(f"CC\t{jid}\t{int(t)}\t{int(v)}")
    atomic_write_text(path, "\n".join(lines) + "\n")
    return path
