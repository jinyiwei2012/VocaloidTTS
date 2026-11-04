"""Compact job file shared by VocaloidTTS and the V4 Job Plugin."""
from __future__ import annotations

from pathlib import Path

from .paths import localappdata_dir
from .prosody import Song


def default_job_path() -> Path:
    return localappdata_dir() / "vocaloidtts_job.txt"


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
        lines.append(f"NOTE\t{n.start}\t{n.dur}\t{n.midi}\t{n.velocity}\t{accent}\t{n.lyric}\t{n.phonemes}")
    for cid in ("S", "P", "DYN", "BRE", "BRI", "CLE", "OPE", "GEN", "POR"):
        jid = {"S": "PBS", "P": "PIT"}.get(cid, cid)
        for t, v in sorted(song.controls.get(cid, []), key=lambda x: x[0]):
            lines.append(f"CC\t{jid}\t{int(t)}\t{int(v)}")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return path
