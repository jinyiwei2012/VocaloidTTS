"""Exported pitch must preserve musical values as well as file structure."""
from __future__ import annotations

import json
from pathlib import Path
import re
import struct
import tempfile
import unittest

from vocaloidtts.exporters import pit_cents, write_svip, write_svip3, write_ustx
from vocaloidtts.pinyin import Syllable
from vocaloidtts.prosody import Note, Song, VoiceOptions


def make_song(note_specs, points, *, pbs=12, bpm=120):
    notes = [
        Note(start, duration, midi, "a", "a", Syllable("啊", "a", 1, "a"))
        for start, duration, midi in note_specs
    ]
    end = max((note.start + note.dur for note in notes), default=0)
    return Song(notes, {"P": points}, end, 7680, [n.syl for n in notes],
                VoiceOptions(pbs=pbs), end * 60 / (bpm * 480), bpm=bpm)


def decode_protobuf(data):
    """Read protobuf wire fields without using any production encoding helpers."""
    offset = 0

    def varint():
        nonlocal offset
        value = 0
        for shift in range(0, 70, 7):
            byte = data[offset]
            offset += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value
        raise ValueError("Invalid protobuf varint")

    fields = {}
    while offset < len(data):
        tag = varint()
        field, wire = tag >> 3, tag & 7
        if wire == 0:
            value = varint()
        elif wire == 2:
            size = varint()
            value = data[offset:offset + size]
            offset += size
        elif wire == 5:
            value = struct.unpack_from("<f", data, offset)[0]
            offset += 4
        else:
            raise ValueError(f"Unsupported protobuf wire type: {wire}")
        fields.setdefault(field, []).append(value)
    if offset != len(data):
        raise ValueError("Truncated protobuf field")
    return fields


def read_svip3(path):
    project = decode_protobuf(Path(path).read_bytes())
    container = decode_protobuf(project[6][0])
    track = decode_protobuf(container[2][0])
    pattern = decode_protobuf(track[8][0])
    notes = []
    for raw in pattern[8]:
        note = decode_protobuf(raw)
        notes.append((note[1][0], note[2][0], note[3][0]))
    pitch = []
    for raw in pattern[9]:
        point = decode_protobuf(raw)
        zigzag = point[1][0]
        tick = (zigzag >> 1) ^ -(zigzag & 1)
        value = point[2][0]
        # SVIP3 encodes absolute MIDI pitch + 0.5; -1 is a curve break.
        pitch.append((tick, None if value == -1 else value * 100 - 50))
    return notes, pitch


def reference_pit_cents(song, note):
    """Original full scan, with the configured PBS applied to its values."""
    points = [(int(t - note.start), float(v) * song.options.pbs / 8192 * 100)
              for t, v in song.controls.get("P", [])
              if note.start <= t <= note.start + note.dur]
    if not points:
        points = [(0, 0.0), (max(1, note.dur), 0.0)]
    if points[0][0] > 0:
        points.insert(0, (0, points[0][1]))
    if points[-1][0] < note.dur:
        points.append((max(1, note.dur), points[-1][1]))
    return points


class ExporterTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.output = Path(self.tempdir.name) / "nested" / "song"

    def test_svip3_zero_bend_retains_midi_67(self):
        song = make_song([(0, 480, 67)], [(0, 0), (480, 0)])
        notes, pitch = read_svip3(write_svip3(song, self.output))
        self.assertEqual(notes, [(0, 480, 67)])
        self.assertEqual(pitch, [(0, None), (0, 6700), (480, 6700), (480, None)])

    def test_svip3_multiple_notes_use_each_base_pitch_and_configured_pbs(self):
        song = make_song([(120, 240, 67), (600, 120, 64)],
                         [(120, 4096), (240, 0), (360, -4096),
                          (600, -2048), (720, 2048)], pbs=6)
        notes, pitch = read_svip3(write_svip3(song, self.output))
        self.assertEqual(notes, [(120, 240, 67), (600, 120, 64)])
        self.assertEqual(pitch, [(120, None), (120, 7000), (240, 6700),
                                 (360, 6400), (600, 6250), (720, 6550),
                                 (720, None)])

    def test_svip3_empty_curve_retains_flat_note_pitches(self):
        song = make_song([(120, 240, 67), (600, 120, 64)], [])
        _, pitch = read_svip3(write_svip3(song, self.output))
        self.assertEqual(pitch, [(120, None), (120, 6700), (360, 6700),
                                 (600, 6400), (720, 6400), (720, None)])

    def test_note_curve_matches_scan_at_boundaries_and_without_points(self):
        cases = [
            [],
            [(99, 4096), (201, -4096)],
            [(125, 4096), (175, -4096)],
            [(99, 8191), (100, 4096), (150, 0), (200, -4096), (201, -8192)],
            [(100, 0), (100, 4096), (200, -4096), (200, 0)],
            [(175, -4096), (125, 4096), (99, 0), (150, 0)],
        ]
        for pbs in (2, 6, 12):
            for points in cases:
                with self.subTest(pbs=pbs, points=points):
                    song = make_song([(100, 100, 67)], points, pbs=pbs)
                    self.assertEqual(pit_cents(song, song.notes[0]),
                                     reference_pit_cents(song, song.notes[0]))

    def test_adjacent_notes_both_include_shared_endpoint(self):
        song = make_song([(0, 100, 67), (100, 100, 64)], [(100, 4096)], pbs=2)
        self.assertEqual(pit_cents(song, song.notes[0]), [(0, 100), (100, 100)])
        self.assertEqual(pit_cents(song, song.notes[1]), [(0, 100), (100, 100)])

    def test_ustx_file_uses_relative_tenths_of_semitones_and_milliseconds(self):
        song = make_song([(100, 480, 67)], [(100, 4096), (340, 0), (580, -4096)],
                         pbs=6, bpm=90)
        content = Path(write_ustx(song, self.output)).read_text(encoding="utf-8")
        points = [(int(x), float(y)) for x, y in re.findall(
            r"\{x: (-?\d+), y: (-?[\d.]+), shape: io\}", content)]
        self.assertEqual(points, [(0, 30), (333, 0), (667, -30)])
        self.assertIn("tone: 67\n", content)

    def test_svip_json_keeps_existing_relative_pitch_model(self):
        song = make_song([(100, 100, 67)], [(100, 4096), (200, -4096)], pbs=6)
        project = json.loads(Path(write_svip(song, self.output)).read_text(encoding="utf-8"))
        track = project["trackList"][0]
        self.assertEqual(track["noteList"][0]["keyNumber"], 67)
        self.assertEqual(track["editedParams"]["pitch"]["pointList"],
                         [[100, 300], [200, -300]])

    def test_exported_curve_matches_scan_for_reordered_overlapping_notes(self):
        song = make_song([(200, 100, 64), (0, 100, 67), (50, 100, 65), (400, 50, 60)],
                         [(250, -1000), (0, 1000), (100, 0), (50, 2048),
                          (100, -2048), (300, 1)])
        expected = [[note.start + tick, round(cents, 3)]
                    for note in song.notes
                    for tick, cents in reference_pit_cents(song, note)]
        project = json.loads(Path(write_svip(song, self.output)).read_text(encoding="utf-8"))
        self.assertEqual(project["trackList"][0]["editedParams"]["pitch"]["pointList"],
                         expected)

    def test_export_rebuilds_index_after_control_changes(self):
        song = make_song([(0, 480, 67)], [(0, 0), (480, 0)])
        write_svip3(song, self.output)
        song.controls["P"][:] = [(0, 4096), (480, 4096)]
        _, pitch = read_svip3(write_svip3(song, self.output))
        self.assertEqual(pitch, [(0, None), (0, 7300), (480, 7300), (480, None)])

    def test_exporters_do_not_rescan_entire_curve_per_note(self):
        class CountedPoints(list):
            scans = 0

            def __iter__(self):
                self.scans += 1
                return super().__iter__()

        for writer in (write_svip3, write_ustx, write_svip):
            with self.subTest(writer=writer.__name__):
                points = CountedPoints((tick, 0) for tick in range(0, 3001, 10))
                song = make_song([(start, 100, 67) for start in range(0, 3000, 100)], points)
                writer(song, self.output)
                self.assertLessEqual(points.scans, 2)

    def test_exporters_reject_empty_song(self):
        for writer in (write_svip3, write_ustx, write_svip):
            with self.subTest(writer=writer.__name__):
                with self.assertRaises(ValueError):
                    writer(make_song([], []), self.output)


if __name__ == "__main__":
    unittest.main()
