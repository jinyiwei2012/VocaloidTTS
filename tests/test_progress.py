"""进度上报要限流，取消要能在检查点真的停下来。"""
from __future__ import annotations

import unittest

from vocaloidtts.progress import Cancelled, Reporter


def _sink(seen: list[tuple[str, float]]):
    """收集回调参数的进度回调。"""
    def on_progress(stage: str, fraction: float) -> None:
        seen.append((stage, fraction))
    return on_progress


class ReporterTests(unittest.TestCase):
    def test_without_callback_nothing_happens(self) -> None:
        rep = Reporter()
        rep.report("parse", 0.5)
        rep.stage("notes", 0.6)
        rep.tick("notes", 3, 10)
        rep.check()  # 没有 should_cancel，不抛

    def test_check_raises_when_cancelled(self) -> None:
        rep = Reporter(should_cancel=lambda: True)
        with self.assertRaises(Cancelled):
            rep.check()

    def test_check_passes_when_not_cancelled(self) -> None:
        rep = Reporter(should_cancel=lambda: False)
        rep.check()

    def test_stage_change_reports_even_with_same_percent(self) -> None:
        seen: list[tuple[str, float]] = []
        rep = Reporter(_sink(seen), interval=0.0)
        rep.report("parse", 0.5)
        rep.report("notes", 0.5)
        self.assertEqual([s for s, _ in seen], ["parse", "notes"])

    def test_same_stage_same_percent_is_skipped(self) -> None:
        seen: list[tuple[str, float]] = []
        rep = Reporter(_sink(seen), interval=0.0)
        rep.report("parse", 0.50)
        rep.report("parse", 0.501)
        rep.report("parse", 0.509)
        self.assertEqual(len(seen), 1)

    def test_force_always_reports(self) -> None:
        seen: list[tuple[str, float]] = []
        rep = Reporter(_sink(seen), interval=60.0)
        rep.report("parse", 0.5)
        rep.report("parse", 0.5, force=True)
        self.assertEqual(len(seen), 2)

    def test_interval_throttles_same_stage(self) -> None:
        seen: list[tuple[str, float]] = []
        rep = Reporter(_sink(seen), interval=60.0)
        rep.report("parse", 0.1)
        rep.report("parse", 0.9)
        self.assertEqual(len(seen), 1)

    def test_fraction_is_clamped(self) -> None:
        seen: list[tuple[str, float]] = []
        rep = Reporter(_sink(seen), interval=0.0)
        rep.report("parse", -3.0)
        rep.report("notes", 7.0)
        self.assertEqual([f for _, f in seen], [0.0, 1.0])

    def test_tick_maps_into_span(self) -> None:
        seen: list[tuple[str, float]] = []
        rep = Reporter(_sink(seen), interval=0.0)
        rep.tick("notes", 1, 4, start=0.4, end=0.8)
        rep.tick("notes", 3, 4, start=0.4, end=0.8)
        self.assertEqual([s for s, _ in seen], ["notes", "notes"])
        self.assertAlmostEqual(seen[0][1], 0.5)
        self.assertAlmostEqual(seen[1][1], 0.7)

    def test_tick_with_zero_total_lands_at_end(self) -> None:
        seen: list[tuple[str, float]] = []
        rep = Reporter(_sink(seen), interval=0.0)
        rep.tick("notes", 0, 0, start=0.4, end=0.8)
        self.assertEqual([f for _, f in seen], [0.8])

    def test_child_maps_its_own_range_into_parent(self) -> None:
        seen: list[tuple[str, float]] = []
        rep = Reporter(_sink(seen), interval=0.0)
        child = rep.child(0.2, 0.6)
        child.report("parse", 0.5)
        self.assertEqual([s for s, _ in seen], ["parse"])
        self.assertAlmostEqual(seen[0][1], 0.4)

    def test_child_clamps_before_mapping(self) -> None:
        seen: list[tuple[str, float]] = []
        rep = Reporter(_sink(seen), interval=0.0)
        child = rep.child(0.5, 1.0)
        child.report("parse", -9.0)
        child.report("parse", 9.0)
        self.assertEqual([f for _, f in seen], [0.5, 1.0])

    def test_child_check_delegates_to_parent(self) -> None:
        rep = Reporter(should_cancel=lambda: True)
        child = rep.child(0.0, 0.5)
        with self.assertRaises(Cancelled):
            child.check()


if __name__ == "__main__":
    unittest.main()
