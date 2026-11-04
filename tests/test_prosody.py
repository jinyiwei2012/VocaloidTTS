import unittest
from dataclasses import replace

from vocaloidtts.prosody import STYLE_PRESETS, VoiceOptions, compose


class ProsodyTests(unittest.TestCase):
    def test_fixed_seed_reproduces_notes_and_curves(self):
        first = compose("你好，世界！今天想聊点什么呢？", VoiceOptions(seed=42))
        second = compose("你好，世界！今天想聊点什么呢？", VoiceOptions(seed=42))
        self.assertTrue(first.notes)
        self.assertEqual(first, second)

    def test_styles_and_tempos_keep_valid_notes_and_controls(self):
        for style in STYLE_PRESETS:
            for bpm, numerator, denominator in [(40, 3, 4), (120, 4, 4), (240, 6, 8)]:
                with self.subTest(style=style, bpm=bpm):
                    song = compose(
                        "ma1 ma2 ma3 ma4 ma5, ni3 hao3!",
                        VoiceOptions(style=style).apply_style(), bpm=bpm,
                        numerator=numerator, denominator=denominator,
                        input_mode="pinyin",
                    )
                    self.assertEqual(len(song.notes), 7)
                    self.assertTrue(all(n.dur > 0 and 0 <= n.midi <= 127 for n in song.notes))
                    self.assertTrue(all(a.start + a.dur <= b.start
                                        for a, b in zip(song.notes, song.notes[1:])))
                    self.assertEqual(song.part_start, 4 * round(480 * 4 * numerator / denominator))
                    self.assertGreater(song.duration_s, 0)
                    for name, points in song.controls.items():
                        self.assertEqual(points, sorted(points))
                        minimum, maximum = (-8192, 8191) if name == "P" else (0, 127)
                        self.assertTrue(all(minimum <= value <= maximum for _, value in points))

    def test_pitch_span_includes_endpoints_and_respects_pbs(self):
        song = compose("ma1 ma2", VoiceOptions(pbs=6), input_mode="pinyin")
        first = replace(song.notes[0], start=0, dur=100, midi=60)
        second = replace(song.notes[1], start=100, dur=100, midi=67)
        song.notes = [first, second]
        # Unsorted points and the shared endpoint must still be considered.
        song.controls["P"] = [(201, 8191), (100, -4096), (0, 4096), (-1, -8192)]
        self.assertEqual(song.pitch_span, (57.0, 64.0))

    def test_pitch_span_matches_reference_scan(self):
        for pbs in (2, 6, 12):
            with self.subTest(pbs=pbs):
                song = compose("ni3 hao3, shi4 jie4! " * 8,
                               VoiceOptions(pbs=pbs), input_mode="pinyin")
                pitches = [note.midi + value * pbs / 8192
                           for note in song.notes
                           for tick, value in song.controls["P"]
                           if note.start <= tick <= note.start + note.dur]
                self.assertEqual(song.pitch_span, (min(pitches), max(pitches)))

    def test_pitch_span_does_not_cache_mutable_controls(self):
        song = compose("ma1", input_mode="pinyin")
        song.controls["P"] = [(0, 0)]
        self.assertEqual(song.pitch_span, (67.0, 67.0))
        song.controls["P"][0] = (0, 4096)
        self.assertEqual(song.pitch_span, (73.0, 73.0))
        song.controls["P"] = []
        self.assertEqual(song.pitch_span, (0.0, 0.0))
        song.controls["P"] = [(song.total_ticks + 1, 4096)]
        self.assertEqual(song.pitch_span, (0.0, 0.0))
        song.notes = []
        self.assertEqual(song.pitch_span, (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
