"""Compare curve lookup with the former full-scan algorithm.

Run from the repository root: python tools/benchmark_generation.py
Both paths use the corrected exporter and must write identical bytes.
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vocaloidtts import exporters
from vocaloidtts.prosody import VoiceOptions, compose


def scan_pitch_span(song):
    values = [note.midi + value * song.options.pbs / 8192
              for note in song.notes
              for tick, value in song.controls.get("P", [])
              if note.start <= tick <= note.start + note.dur]
    return (min(values), max(values)) if values else (0.0, 0.0)


def scan_pit_cents(song, note, *, pitch_index=None):
    points = [(int(tick - note.start), value * song.options.pbs / 8192 * 100)
              for tick, value in song.controls.get("P", [])
              if note.start <= tick <= note.start + note.dur]
    if not points:
        points = [(0, 0.0), (max(1, note.dur), 0.0)]
    if points[0][0] > 0:
        points.insert(0, (0, points[0][1]))
    if points[-1][0] < note.dur:
        points.append((max(1, note.dur), points[-1][1]))
    return points


def measure(action, repeats):
    timings = []
    for _ in range(repeats):
        started = time.perf_counter()
        result = action()
        timings.append(time.perf_counter() - started)
    return statistics.median(timings), result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    results = []
    with tempfile.TemporaryDirectory(prefix="vocaloidtts-benchmark-") as directory:
        for count in (100, 500, 1000):
            text = ("ni3 hao3 shi4 jie4 " * (count // 4)).strip()
            compose_s, song = measure(
                lambda: compose(text, VoiceOptions(), input_mode="pinyin"), args.repeats)
            scan_s, scan_span = measure(lambda: scan_pitch_span(song), args.repeats)
            index_s, index_span = measure(lambda: song.pitch_span, args.repeats)
            assert scan_span == index_span, "Pitch range changed"
            old_path = Path(directory) / "scan.svip3"
            new_path = Path(directory) / "indexed.svip3"
            with patch.object(exporters, "pit_cents", scan_pit_cents):
                old_s, _ = measure(lambda: exporters.write_svip3(song, str(old_path)), args.repeats)
            new_s, _ = measure(lambda: exporters.write_svip3(song, str(new_path)), args.repeats)
            assert old_path.read_bytes() == new_path.read_bytes(), "Export changed"
            results.append({
                "syllables": len(song.notes), "pitch_points": len(song.controls["P"]),
                "compose_s": round(compose_s, 4),
                "span_scan_s": round(scan_s, 4), "span_index_s": round(index_s, 4),
                "svip3_scan_s": round(old_s, 4), "svip3_index_s": round(new_s, 4),
                "equivalent": True,
            })
    print(json.dumps({"python": platform.python_version(), "platform": platform.system(),
                      "repeats": args.repeats, "statistic": "median", "results": results}, indent=2))


if __name__ == "__main__":
    main()
