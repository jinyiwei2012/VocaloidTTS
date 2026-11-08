import unittest
from dataclasses import replace

from vocaloidtts.edits import CharEdit
from vocaloidtts.progress import Cancelled, Reporter
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


    def test_control_points_are_thinned_for_long_projects(self):
        song = compose("ni3 hao3 shi4 jie4 " * 80, VoiceOptions(seed=1),
                       input_mode="pinyin")
        self.assertGreater(song.duration_s, 10)
        points_per_second = len(song.controls["P"]) / song.duration_s
        self.assertLess(points_per_second, 80)


    def test_punctuation_is_recorded_on_the_final_syllable(self):
        song = compose("你好吗？", VoiceOptions())
        self.assertEqual(song.notes[-1].syl.punct, "？")
        song = compose("ni3 hao3 ma5?", VoiceOptions(), input_mode="pinyin")
        self.assertEqual(song.notes[-1].syl.punct, "?")

    def test_tone4_overshoot_is_soft_limited_not_clamped(self):
        song = compose("大地上的人们都在看着这场戏剧，世界就在我们面前。",
                       VoiceOptions(style="read", seed=1))
        points = song.controls["P"]
        self.assertTrue(points)
        clamped = sum(1 for _, value in points if abs(value) >= 8192)
        self.assertEqual(clamped, 0)
        self.assertTrue(all(-8192 <= value <= 8191 for _, value in points))


class ComposeProgressTests(unittest.TestCase):
    def test_progress_covers_every_stage_and_ends_at_one(self):
        seen = []
        reporter = Reporter(lambda stage, frac: seen.append((stage, frac)),
                            interval=0.0)
        compose("大地上的人们都在看着这场戏剧，世界就在我们面前。" * 3,
                reporter=reporter)
        stages = [stage for stage, _ in seen]
        self.assertEqual(stages[0], "parse")
        self.assertEqual(stages[-1], "done")
        self.assertTrue({"parse", "timing", "notes", "pitch", "pit",
                         "curves", "done"}.issubset(set(stages)))
        fractions = [frac for _, frac in seen]
        self.assertEqual(fractions, sorted(fractions))
        self.assertAlmostEqual(fractions[-1], 1.0)

    def test_empty_text_still_finishes(self):
        seen = []
        reporter = Reporter(lambda stage, frac: seen.append((stage, frac)),
                            interval=0.0)
        song = compose("", reporter=reporter)
        self.assertEqual(song.notes, [])
        self.assertEqual(seen[-1][1], 1.0)

    def test_cancel_stops_before_any_curve_work(self):
        seen = []
        reporter = Reporter(lambda stage, frac: seen.append((stage, frac)),
                            should_cancel=lambda: True, interval=0.0)
        with self.assertRaises(Cancelled):
            compose("你好，世界！", reporter=reporter)
        self.assertNotIn("done", [stage for stage, _ in seen])

    def test_without_reporter_the_song_is_identical(self):
        plain = compose("你好，世界！", VoiceOptions(seed=7))
        quiet = compose("你好，世界！", VoiceOptions(seed=7),
                        reporter=Reporter())
        self.assertEqual(plain, quiet)


class LocalEditTests(unittest.TestCase):
    def test_duration_scale_lengthens_only_that_syllable(self):
        plain = compose("你好世界", VoiceOptions(seed=5))
        long = compose("你好世界", VoiceOptions(seed=5),
                       edits={1: CharEdit(char="好", dur_scale=1.8)})
        self.assertGreater(long.notes[1].dur, plain.notes[1].dur)
        untouched = [(i, n.dur) for i, n in enumerate(long.notes) if i != 1]
        expected = [(i, n.dur) for i, n in enumerate(plain.notes) if i != 1]
        self.assertEqual(untouched, expected)

    def test_exact_pause_is_not_scaled(self):
        tight = compose("你好世界", VoiceOptions(seed=5, pause_scale=0.4),
                        edits={1: CharEdit(char="好", pause_ms=300)})
        loose = compose("你好世界", VoiceOptions(seed=5, pause_scale=1.8),
                        edits={1: CharEdit(char="好", pause_ms=300)})

        def gap(song):
            first, second = song.notes[1], song.notes[2]
            return second.start - (first.start + first.dur)

        # 120 BPM / 480 PPQ 下 300 ms 正好 288 tick
        self.assertEqual(gap(tight), 288)
        self.assertEqual(gap(loose), 288)

    def test_stress_delta_lifts_the_velocity(self):
        plain = compose("你好世界", VoiceOptions(seed=5))
        loud = compose("你好世界", VoiceOptions(seed=5),
                       edits={0: CharEdit(char="你", stress=0.6)})
        self.assertGreater(loud.notes[0].velocity, plain.notes[0].velocity)

    def test_dictionary_reading_reaches_the_notes(self):
        song = compose("重明", dictionary={"重明": "chong2 ming2"})
        self.assertEqual([n.lyric for n in song.notes], ["chong", "ming"])

    def test_exact_pause_is_not_read_as_punctuation(self):
        # pause_ms=400 正好是「问句」那条旧启发式的阈值，不能被当成标点
        asked = compose("你好世界？", VoiceOptions(seed=5))
        paused = compose("你好世界", VoiceOptions(seed=5),
                         edits={1: CharEdit(char="好", pause_ms=400)})
        self.assertNotEqual(paused.controls["P"][-1],
                            asked.controls["P"][-1])

    def test_edits_do_not_touch_neighbours(self):
        plain = compose("大地上的人们", VoiceOptions(seed=5))
        edited = compose("大地上的人们", VoiceOptions(seed=5),
                         edits={3: CharEdit(char="人", pinyin="ren", tone=4)})
        self.assertEqual([n.midi for n in edited.notes[:3]],
                         [n.midi for n in plain.notes[:3]])


if __name__ == "__main__":
    unittest.main()
