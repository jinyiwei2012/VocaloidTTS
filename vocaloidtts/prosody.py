"""Rule-based Mandarin prosody -> VOCALOID note + controller plan.

The model is deliberately transparent and editable: each syllable gets a
Mandarin tone contour on top of a sentence-level declination line, then the
result is rendered as dense PIT breakpoints (PBS = 12 semitones).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Iterable

from .pinyin import Syllable, pinyin_text_to_syllables, text_to_syllables


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------

STYLE_PRESETS = {
    "read":   dict(rate=1.00, tone=1.35, breath=12, vibrato=16, energy=1.25, pitch=67, tone2=66, tone3=64, tone4=65, tone5=64, label="自然朗读"),
    "news":   dict(rate=1.08, tone=1.10, breath=4,  vibrato=6,  energy=1.45, pitch=67, tone2=66, tone3=64, tone4=65, tone5=64, label="新闻播报"),
    "sweet":  dict(rate=0.92, tone=1.45, breath=22, vibrato=24, energy=1.15, pitch=69, tone2=68, tone3=66, tone4=67, tone5=66, label="甜系撒娇"),
    "soft":   dict(rate=0.88, tone=1.05, breath=42, vibrato=6,  energy=0.85, pitch=65, tone2=64, tone3=62, tone4=63, tone5=62, label="气声耳语"),
    "story":  dict(rate=0.95, tone=1.50, breath=15, vibrato=18, energy=1.20, pitch=67, tone2=66, tone3=64, tone4=65, tone5=64, label="故事旁白"),
    "drama":  dict(rate=0.94, tone=1.80, breath=8,  vibrato=24, energy=1.65, pitch=67, tone2=66, tone3=63, tone4=65, tone5=63, label="戏剧朗读"),
    "robot":  dict(rate=1.02, tone=0.35, breath=0,  vibrato=0,  energy=1.00, pitch=67, tone2=66, tone3=64, tone4=65, tone5=64, label="机械念白"),
}


@dataclass
class VoiceOptions:
    style: str = "read"
    pitch: int = 67              # 第一声基准，MIDI note；G3 = 67 (V4 C3=60)
    tone2_pitch: int = 66        # 第二声基准
    tone3_pitch: int = 64        # 第三声基准
    tone4_pitch: int = 65        # 第四声基准
    tone5_pitch: int = 64        # 轻声基准
    rate: float = 1.0            # 0.7 .. 1.4
    tone_strength: float = 1.35  # 0.4 .. 2.0, phrase movement / accent
    pause_scale: float = 1.0     # 0.4 .. 1.8
    breath: int = 12             # 0 .. 100
    vibrato: int = 16            # 0 .. 100
    gender: int = 0              # -100 .. 100, 0 = neutral
    energy: float = 1.25         # 0.4 .. 1.8, dynamics / velocity
    seed: int = 20261025
    flat_notes: bool = True      # speech-like: one pitch + PIT contour
    pbs: int = 12                # semitones of pitch-bend range

    def apply_style(self) -> "VoiceOptions":
        p = STYLE_PRESETS.get(self.style)
        if p:
            self.rate = p["rate"]
            self.tone_strength = p["tone"]
            self.breath = p["breath"]
            self.vibrato = p["vibrato"]
            self.energy = p["energy"]
            self.pitch = p["pitch"]
            self.tone2_pitch = p["tone2"]
            self.tone3_pitch = p["tone3"]
            self.tone4_pitch = p["tone4"]
            self.tone5_pitch = p["tone5"]
        return self


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Note:
    start: int
    dur: int
    midi: int
    lyric: str
    phonemes: str
    syl: Syllable
    velocity: int = 64


@dataclass
class Song:
    notes: list[Note]
    controls: dict[str, list[tuple[int, int]]]
    total_ticks: int
    part_start: int
    syllables: list[Syllable]
    options: VoiceOptions
    duration_s: float
    bpm: float = 120.0
    resolution: int = 480
    numerator: int = 4
    denominator: int = 4

    @property
    def pitch_span(self) -> tuple[float, float]:
        if not self.notes:
            return (0.0, 0.0)
        pp = self.controls.get("P", [])
        vals: list[float] = []
        for n in self.notes:
            se = [v * self.options.pbs / 8192 for t, v in pp
                  if n.start <= t <= n.start + n.dur]
            if se:
                vals.extend(n.midi + x for x in se)
        if not vals:
            return (0.0, 0.0)
        return (min(vals), max(vals))


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------

_TONE_LEN = {1: 1.00, 2: 1.06, 3: 1.24, 4: 0.92, 5: 0.58}


def _assign_timing(syls: list[Syllable], opts: VoiceOptions, tpm: float) -> None:
    rng = random.Random(opts.seed)
    cursor = 0.0
    for s in syls:
        base = 232.0 * _TONE_LEN.get(s.tone, 1.0) / max(0.55, opts.rate)
        accent = max(0.0, s.stress - 0.35)
        base *= 1.0 + 0.18 * accent * opts.tone_strength + rng.uniform(-0.06, 0.06)
        if s.final:
            base *= 1.26
        if s.pause_after_ms:
            base *= 1.05
        s.dur_ms = max(95.0, min(680.0, base))
        s.start_ms = cursor
        cursor += s.dur_ms + s.pause_after_ms * opts.pause_scale
    # quantise to ticks, keeping gaps
    cursor_t = 0
    for s in syls:
        dur = max(20, int(round(s.dur_ms * tpm)))
        pause = int(round(s.pause_after_ms * opts.pause_scale * tpm))
        s._start_tick = cursor_t  # type: ignore[attr-defined]
        s._dur_tick = dur          # type: ignore[attr-defined]
        s._pause_tick = pause      # type: ignore[attr-defined]
        cursor_t += dur + pause


def ms_to_ticks(ms: float, bpm: float, resolution: int) -> float:
    return ms * resolution * bpm / 60000.0


# ---------------------------------------------------------------------------
# Pitch
# ---------------------------------------------------------------------------

# Mandarin tone shapes relative to each tone's own anchor.
# Values are (position 0..1, semitone offset).
_TONE_CONTOURS = {
    1: [(0.00, 0.00), (0.30, 0.14), (0.72, 0.11), (1.00, 0.00)],
    2: [(0.00, -2.10), (0.15, -4.80), (0.45, -3.00), (0.75, 0.90), (1.00, 3.45)],
    3: [(0.00, -0.60), (0.32, -2.55), (0.62, -2.85), (1.00, -0.90)],
    4: [(0.00, 1.05), (0.18, 2.55), (0.35, 1.05), (0.70, -4.95), (1.00, -11.55)],
    5: [(0.00, -0.20), (0.40, -0.40), (1.00, -0.60)],
}


def _pitch_curve(syls: list[Syllable], opts: VoiceOptions,
                 tpm: float) -> list[tuple[int, float]]:
    """Continuous pitch track in ticks, with smooth transitions over gaps."""
    rng = random.Random(opts.seed + 7)
    if not syls:
        return []
    phrases: dict[int, list[Syllable]] = {}
    for s in syls:
        phrases.setdefault(s.phrase, []).append(s)

    anchors: dict[int, list[tuple[float, float]]] = {}
    for pi, group in phrases.items():
        n = len(group)
        final = group[-1]
        punct = final.pause_after_ms
        is_q = punct == 400
        is_excl = punct == 380
        ts = opts.tone_strength
        anchors_pitch = {
            1: opts.pitch,
            2: opts.tone2_pitch,
            3: opts.tone3_pitch,
            4: opts.tone4_pitch,
            5: opts.tone5_pitch,
        }
        decl_start = 0.12 * ts
        decl_end = -0.42 * ts
        if is_q:
            decl_end = 0.55 * ts
        elif is_excl:
            decl_start += 0.22 * ts
        for k, s in enumerate(group):
            p = k / max(1, n - 1)
            base = decl_start + (decl_end - decl_start) * p
            # a small phrase arc, not enough to move tone 1 off its anchor
            base += 0.16 * ts * math.sin(math.pi * p)
            if n == 1:
                base = 0.05 * ts
            base += (s.stress - 0.45) * 0.55 * ts
            if s.final and not is_q:
                base -= 0.22 * ts
            if s.final and is_q:
                base += 0.38 * ts
            base += anchors_pitch.get(s.tone, opts.tone3_pitch) - opts.pitch
            if s.tone == 3:
                # 上声要低；即使“好/很”等焦点重音也不要把三声顶到
                # 一声附近，否则四声的对比会消失。
                base = min(base, anchors_pitch[3] - opts.pitch)
            shape = _TONE_CONTOURS.get(s.tone, _TONE_CONTOURS[5])
            # absolute contours relative to the first-tone anchor
            shape_scale = 1.0 if s.tone == 5 else 0.85 + 0.15 * ts
            accent = max(0.0, s.stress - 0.55) * 0.45 * ts
            pts: list[tuple[float, float]] = []
            for pos, off in shape:
                # stress accent: a local onset lift that settles into the tone
                lift = accent * max(0.0, 1.0 - pos / 0.34)
                cents = base + off * shape_scale + lift
                if s.final and pos > 0.7:
                    cents -= 0.12 * ts
                cents += rng.uniform(-0.05, 0.05) * ts
                pts.append((pos, cents))
            anchors[s.index] = pts

    def contour_at(s: Syllable, frac: float) -> float:
        pts = anchors.get(s.index, [(0.0, 0.0), (1.0, 0.0)])
        frac = max(0.0, min(1.0, frac))
        for i in range(len(pts) - 1):
            p0, v0 = pts[i]
            p1, v1 = pts[i + 1]
            if p0 <= frac <= p1:
                q = (frac - p0) / max(1e-9, p1 - p0)
                q = q * q * (3 - 2 * q)
                return v0 + (v1 - v0) * q
        return pts[-1][1]

    total_ticks = max((s._start_tick + s._dur_tick) for s in syls)  # type: ignore[attr-defined]
    step = max(2, int(round(5.0 * tpm)))  # 5 ms PIT analysis grid
    note_starts = [s._start_tick for s in syls]  # type: ignore[attr-defined]
    samples: list[tuple[int, float]] = []
    ptr = 0
    t = 0
    while t <= total_ticks:
        while ptr + 1 < len(syls) and t >= note_starts[ptr + 1]:
            ptr += 1
        s = syls[ptr]
        st = s._start_tick  # type: ignore[attr-defined]
        dur = max(1, s._dur_tick)  # type: ignore[attr-defined]
        if st <= t < st + dur:
            val = contour_at(s, (t - st) / dur)
            dur_ms = dur / max(1e-6, tpm)
            tt_ms = (t - st) / max(1e-6, tpm)
            depth = (opts.vibrato / 100.0) * 0.24
            if depth > 0 and dur_ms > 320 and tt_ms > dur_ms * 0.34:
                fade = min(1.0, (tt_ms - dur_ms * 0.34) / max(1.0, dur_ms * 0.30))
                val += math.sin(2 * math.pi * 5.4 * tt_ms / 1000.0) * depth * fade
        else:
            prev = s
            prev_end = st + dur
            nxt = syls[ptr + 1] if ptr + 1 < len(syls) else None
            if st > t:
                nxt = s
                prev = syls[ptr - 1] if ptr > 0 else None
                prev_end = (prev._start_tick + prev._dur_tick) if prev else 0  # type: ignore[attr-defined]
            if prev and nxt:
                gap = max(1, nxt._start_tick - prev_end)  # type: ignore[attr-defined]
                glide = min(gap, max(12, int(90 * tpm)))
                g0 = nxt._start_tick - glide  # type: ignore[attr-defined]
                v0 = contour_at(prev, 1.0)
                v1 = contour_at(nxt, 0.0)
                if t >= g0:
                    q = (t - g0) / max(1, glide)
                    q = q * q * (3 - 2 * q)
                    val = v0 + (v1 - v0) * q
                else:
                    val = v0
            elif prev:
                val = contour_at(prev, 1.0)
            elif nxt:
                val = contour_at(nxt, 0.0)
            else:
                val = 0.0
        samples.append((int(t), val))
        t += step

    # 1.10 timing stays untouched.  The PIT curve is now sampled at 5 ms,
    # then smoothed over ~40 ms: more visual detail, but no sharp zig-zags.
    win = max(1, int(round(8.0)))
    out: list[tuple[int, float]] = []
    for i, (tt, v) in enumerate(samples):
        lo = max(0, i - win)
        hi = min(len(samples), i + win + 1)
        # triangular weights
        num = 0.0
        den = 0.0
        for j in range(lo, hi):
            w = 1.0 - abs(j - i) / (win + 1)
            num += samples[j][1] * w
            den += w
        out.append((tt, num / max(1e-9, den)))
    return out



# ---------------------------------------------------------------------------
# Controllers
# ---------------------------------------------------------------------------

def _pitch_to_pit(samples: Iterable[tuple[int, float]],
                  notes: list[Note], opts: VoiceOptions) -> list[tuple[int, float]]:
    """Convert absolute-ish pitch samples to PIT offsets for per-tone notes.

    The pitch curve is relative to the first-tone note; each note now sits on
    its own tone anchor, so subtract that note's anchor at each sample.
    """
    spans = [(n.start, n.start + max(1, n.dur), n.midi - opts.pitch) for n in notes]
    out: list[tuple[int, float]] = []
    j = 0
    for t, st in samples:
        while j + 1 < len(spans) and t >= spans[j][1]:
            j += 1
        offset = spans[j][2] if spans else 0
        out.append((t, st - offset))
    return out


def _ctrl_points(samples: Iterable[tuple[int, float]], pbs: int,
                 step: int = 14) -> list[tuple[int, int]]:
    pts: list[tuple[int, int]] = []
    last_t = -10**9
    last_v = None
    for t, st in samples:
        v = int(round(st * 8192.0 / pbs))
        v = max(-8192, min(8191, v))
        if t - last_t >= step or (last_v is not None and abs(v - last_v) >= 60):
            pts.append((t, v))
            last_t = t
            last_v = v
    if pts and pts[0][0] > 0:
        pts.insert(0, (0, pts[0][1]))
    return pts


def _dyn_curve(song_notes: list[Note], total_ticks: int,
               opts: VoiceOptions) -> list[tuple[int, int]]:
    pts: list[tuple[int, int]] = []
    e = opts.energy
    for n in song_notes:
        t0, dur = n.start, n.dur
        stress = n.syl.stress
        base = 55.0 + 36.0 * (stress - 0.42) * e
        base = max(24.0, min(104.0, base))
        peak = base + 10.0 * e + (9.0 * e if stress > 0.95 else 0.0)
        peak = min(122.0, peak)
        end_level = base * (0.48 if n.syl.final else 0.58)
        env = [
            (0.000, base * 0.30),
            (0.030, peak * 1.02),
            (0.110, peak),
            (0.360, base * 1.03),
            (0.700, base * 0.97),
            (1.000, end_level),
        ]
        pts.append((max(0, t0 - 8), 24))
        for f, v in env:
            pts.append((t0 + int(dur * f), max(0, min(127, int(round(v))))))
        pts.append((t0 + dur + 10, 22))
    # dedupe / sort
    d: dict[int, int] = {}
    for t, v in pts:
        d[t] = v
    return sorted(d.items())


def _style_curve(song_notes: list[Note], total_ticks: int, opts: VoiceOptions,
                 which: str) -> list[tuple[int, int]]:
    if not song_notes:
        return []
    if which == "BRE":
        base = int(3 + opts.breath * 0.55)
    elif which == "BRI":
        base = int(60 + opts.energy * 11)
    elif which == "CLE":
        base = int(72 - opts.breath * 0.30)
    elif which == "OPE":
        base = int(112 - opts.breath * 0.20)
    elif which == "GEN":
        # VSQX GEN is 0..127 with 64 neutral; the UI exposes -100..100.
        base = int(round(64 + opts.gender * 63.0 / 100.0))
    elif which == "POR":
        base = 6 if opts.flat_notes else 24
    else:
        base = 64
    base = max(0, min(127, base))
    pts: list[tuple[int, int]] = [(0, base)]
    for n in song_notes:
        # brightness rises with accent and falls on soft/breathy notes
        v = base
        if which == "BRI":
            v += int(n.syl.stress * 14 - 4)
        elif which == "DYN":
            v = base
        v = max(0, min(127, v))
        pts.append((max(0, n.start - 8), v))
        pts.append((n.start + n.dur, v))
    pts.append((total_ticks + 480, base))
    d: dict[int, int] = {}
    for t, v in pts:
        d[t] = v
    return sorted(d.items())


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def compose(text: str, options: VoiceOptions | None = None,
            bpm: float = 120.0, resolution: int = 480,
            numerator: int = 4, denominator: int = 4,
            input_mode: str = "chinese") -> Song:
    opts = options or VoiceOptions()
    bpm = max(30.0, min(300.0, float(bpm)))
    resolution = max(96, min(1920, int(resolution)))
    numerator = max(1, min(16, int(numerator)))
    denominator = int(denominator)
    if denominator not in (2, 4, 8, 16):
        denominator = 4
    for attr in ("pitch", "tone2_pitch", "tone3_pitch", "tone4_pitch", "tone5_pitch"):
        setattr(opts, attr, max(36, min(84, int(getattr(opts, attr)))))
    opts.rate = max(0.6, min(1.6, float(opts.rate)))
    opts.tone_strength = max(0.3, min(2.0, float(opts.tone_strength)))
    opts.pause_scale = max(0.3, min(1.8, float(opts.pause_scale)))
    opts.breath = max(0, min(100, int(opts.breath)))
    opts.vibrato = max(0, min(100, int(opts.vibrato)))
    opts.gender = max(-100, min(100, int(opts.gender)))
    opts.energy = max(0.4, min(1.8, float(opts.energy)))
    opts.pbs = max(1, min(12, int(opts.pbs)))

    print_measure = max(1, int(round(resolution * 4 * numerator / denominator)))
    part_start = print_measure * 4

    if input_mode == "pinyin":
        syls = pinyin_text_to_syllables(text)
    else:
        syls = text_to_syllables(text)
    if not syls:
        return Song([], {}, 0, part_start, [], opts, 0.0,
                    bpm, resolution, numerator, denominator)

    tpm = ms_to_ticks(1.0, bpm, resolution)
    _assign_timing(syls, opts, tpm)
    total_ticks = 0
    notes: list[Note] = []
    tone_anchor = {
        1: opts.pitch,
        2: opts.tone2_pitch,
        3: opts.tone3_pitch,
        4: opts.tone4_pitch,
        5: opts.tone5_pitch,
    }
    for s in syls:
        t0 = s._start_tick  # type: ignore[attr-defined]
        dur = s._dur_tick   # type: ignore[attr-defined]
        # Each tone gets its own note pitch, so V4's piano roll shows the
        # four-tone shape instead of a single flat row.
        midi = int(tone_anchor.get(s.tone, opts.tone3_pitch))
        vel = int(round(48 + 44 * min(1.45, s.stress) * opts.energy))
        vel = max(24, min(118, vel))
        notes.append(Note(t0, dur, midi, s.pinyin, s.phonemes, s, velocity=vel))
        total_ticks = max(total_ticks, t0 + dur)

    pitch = _pitch_curve(syls, opts, tpm)
    controls: dict[str, list[tuple[int, int]]] = {}
    controls["S"] = [(0, opts.pbs)]
    # 5 ms PIT control spacing: finer than 1.10 (10 ms), but the 40 ms
    # smoothing keeps the legato feel of the 1.10 timing model.
    controls["P"] = _ctrl_points(_pitch_to_pit(pitch, notes, opts), opts.pbs,
                                 step=max(2, int(round(5.0 * tpm))))
    if not controls["P"]:
        controls["P"] = [(0, 0)]
    controls["DYN"] = _dyn_curve(notes, total_ticks, opts)
    controls["BRE"] = _style_curve(notes, total_ticks, opts, "BRE")
    controls["BRI"] = _style_curve(notes, total_ticks, opts, "BRI")
    controls["CLE"] = _style_curve(notes, total_ticks, opts, "CLE")
    controls["OPE"] = _style_curve(notes, total_ticks, opts, "OPE")
    controls["GEN"] = _style_curve(notes, total_ticks, opts, "GEN")
    controls["POR"] = _style_curve(notes, total_ticks, opts, "POR")
    duration_s = total_ticks / resolution / bpm * 60.0
    return Song(notes, controls, total_ticks, part_start, syls, opts, duration_s,
                bpm, resolution, numerator, denominator)
