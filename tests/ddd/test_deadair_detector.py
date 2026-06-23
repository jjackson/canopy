"""Tests for the post-render dead-air QA detector (Layer 2).

Dead air = video FROZEN (no motion) AND no voiceover. The detector intersects
ffmpeg ``freezedetect`` spans with ``silencedetect`` spans and reports the
overlaps that last at least ``MIN_OVERLAP_SECONDS``.

The audio nuance: the music bed plays as a quiet ~-50 dB bed, so a
``silencedetect`` at -40 dB correctly flags a no-VO span as "silent" even with
the bed underneath — exactly what we want (frozen + no-VO, not frozen +
literally-zero-audio).

These tests exercise the PURE parse + intersection — no ffmpeg, no real mp4.
"""
from __future__ import annotations

from scripts.ddd import deadair


# --- ffmpeg log parsing ---------------------------------------------------


def test_parse_freeze_spans_pairs_start_end():
    log = (
        "lavfi.freezedetect.freeze_start: 8.38\n"
        "lavfi.freezedetect.freeze_duration: 0.72\n"
        "lavfi.freezedetect.freeze_end: 9.10\n"
        "lavfi.freezedetect.freeze_start: 60.00\n"
        "lavfi.freezedetect.freeze_end: 66.60\n"
    )
    spans = deadair.parse_freeze_spans(log)
    assert spans == [(8.38, 9.10), (60.00, 66.60)]


def test_parse_freeze_dedupes_doubled_metadata_prints():
    """freezedetect + metadata=print logs each value twice — dedupe to one span."""
    log = (
        "[Parsed_freezedetect_0] lavfi.freezedetect.freeze_start: 60.0\n"
        "[Parsed_metadata_1] lavfi.freezedetect.freeze_start=60.0\n"
        "[Parsed_freezedetect_0] lavfi.freezedetect.freeze_end: 66.6\n"
        "[Parsed_metadata_1] lavfi.freezedetect.freeze_end=66.6\n"
    )
    assert deadair.parse_freeze_spans(log) == [(60.0, 66.6)]


def test_parse_freeze_open_span_closes_at_total():
    """A freeze that starts but never ends runs to the clip's end."""
    log = "lavfi.freezedetect.freeze_start: 100.0\n"
    spans = deadair.parse_freeze_spans(log, total_seconds=107.0)
    assert spans == [(100.0, 107.0)]


def test_parse_silence_spans():
    log = (
        "silencedetect @ 0x1 silence_start: 40.5\n"
        "silencedetect @ 0x1 silence_end: 48.0 | silence_duration: 7.5\n"
        "silencedetect @ 0x1 silence_start: 95.0\n"
        "silencedetect @ 0x1 silence_end: 110.0 | silence_duration: 15.0\n"
    )
    spans = deadair.parse_silence_spans(log)
    assert spans == [(40.5, 48.0), (95.0, 110.0)]


def test_parse_silence_open_span_closes_at_total():
    log = "silencedetect @ 0x1 silence_start: 100.0\n"
    spans = deadair.parse_silence_spans(log, total_seconds=107.0)
    assert spans == [(100.0, 107.0)]


# --- intersection ---------------------------------------------------------


def test_intersect_keeps_only_overlaps_at_least_min():
    freeze = [(8.0, 9.0), (60.0, 67.0)]
    silence = [(40.0, 48.0), (61.0, 66.6)]
    # 8-9 freeze has no silence overlap. 60-67 ∩ 61-66.6 = 5.6s ≥ 1.0 → kept.
    spans = deadair.intersect_spans(freeze, silence, min_overlap=1.0)
    assert spans == [(61.0, 66.6)]


def test_intersect_drops_sub_min_overlap():
    freeze = [(60.0, 60.5)]
    silence = [(60.0, 60.5)]
    # 0.5s overlap < 1.0 → dropped.
    assert deadair.intersect_spans(freeze, silence, min_overlap=1.0) == []


def test_intersect_partial_overlap_clipped_to_intersection():
    freeze = [(10.0, 20.0)]
    silence = [(15.0, 30.0)]
    # intersection is [15, 20] = 5s.
    assert deadair.intersect_spans(freeze, silence, min_overlap=1.0) == [(15.0, 20.0)]


# --- report shape ---------------------------------------------------------


def test_build_report_flags_spans_over_threshold():
    spans = [(60.0, 66.6), (95.0, 96.5)]
    report = deadair.build_report(spans)
    assert report["span_count"] == 2
    assert report["total_seconds"] == round((66.6 - 60.0) + (96.5 - 95.0), 3)
    # 6.6s span exceeds the 3s product threshold; the 1.5s one does not.
    assert report["over_threshold"] == [{"start": 60.0, "end": 66.6, "seconds": 6.6}]
    assert report["has_dead_air"] is True


def test_build_report_clean_when_all_sub_threshold():
    report = deadair.build_report([(10.0, 11.5), (20.0, 22.0)])
    assert report["over_threshold"] == []
    assert report["has_dead_air"] is False


def test_drop_ignored_excises_designed_card_spans():
    """A frozen+silent span inside the outro card range is excised (it's an
    intentional held end card, not frozen footage)."""
    spans = [(60.0, 66.6), (108.6, 112.6)]
    # outro card occupies [108.0, 112.6] of the final video.
    kept = deadair._drop_ignored(spans, [(108.0, 112.6)])
    assert kept == [(60.0, 66.6)]


def test_drop_ignored_keeps_partial_overlap():
    """A span only PARTIALLY inside an ignored range is kept (it bleeds real
    footage dead air into a card boundary — surface it)."""
    spans = [(105.0, 112.6)]
    kept = deadair._drop_ignored(spans, [(108.0, 112.6)])
    assert kept == [(105.0, 112.6)]


def test_constants():
    assert deadair.DEAD_THRESHOLD_SECONDS == 3.0
    assert deadair.MIN_OVERLAP_SECONDS == 1.0
    assert deadair.FREEZE_NOISE_DB == -55
    assert deadair.SILENCE_NOISE_DB == -40
