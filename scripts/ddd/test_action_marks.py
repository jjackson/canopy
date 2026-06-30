"""Tests for action↔word marks (onscreen_for_abs, _mark_words, build_action_marks).

Pure-logic, stdlib-only. Run: python3 -m pytest scripts/ddd/test_action_marks.py
or directly: python3 scripts/ddd/test_action_marks.py
"""

from scripts.ddd.snippets import _mark_words, build_action_marks, onscreen_for_abs


def test_onscreen_single_segment():
    segs = [(10.0, 20.0)]  # master [10,30] → on-screen [0,20]
    assert onscreen_for_abs(segs, 10.0) == 0.0
    assert onscreen_for_abs(segs, 15.0) == 5.0
    assert onscreen_for_abs(segs, 30.0) == 20.0
    assert onscreen_for_abs(segs, 5.0) == 0.0   # before start → clamp 0
    assert onscreen_for_abs(segs, 99.0) == 20.0  # past end → clamp total


def test_onscreen_multi_segment_with_excised_gap():
    # Two kept segments with master gap [25,40] excised (a collapsed load wait).
    segs = [(10.0, 15.0), (40.0, 10.0)]  # on-screen: seg1 [0,15], seg2 [15,25]
    assert onscreen_for_abs(segs, 20.0) == 10.0   # inside seg1
    assert onscreen_for_abs(segs, 25.0) == 15.0   # seg1 end
    assert onscreen_for_abs(segs, 32.0) == 15.0   # INSIDE the excised gap → jump-cut point
    assert onscreen_for_abs(segs, 45.0) == 20.0   # 5s into seg2 → 15+5
    assert onscreen_for_abs(segs, 50.0) == 25.0   # seg2 end


def test_mark_words_order_and_sources():
    # explicit word wins, then field-id tokens, then note tokens; deduped.
    a = {"target": "css:#id_contact_email", "note": "her contact", "word": "reach"}
    assert _mark_words(a) == ["reach", "contact", "email"]
    # no explicit; field id tokens then note (>=4 chars), 'id'/'css' dropped (len<=2 / not matched)
    b = {"target": "css:#id_description", "note": "survey description"}
    assert _mark_words(b) == ["description", "survey"]
    # short id tokens (<=2 chars) dropped
    c = {"target": "css:#id_is_public", "note": ""}
    assert _mark_words(c) == ["public"]


def test_build_action_marks_filters_and_maps():
    segs = [(0.0, 30.0)]  # on-screen == master here
    actions = [
        {"kind": "scroll_to", "target": "css:#id_description", "note": "", "start_seconds": 4.0, "scene_index": 3},
        {"kind": "fill", "target": "css:#id_description", "note": "", "start_seconds": 6.0, "scene_index": 3},
        {"kind": "wait_for", "target": "css:.spinner", "note": "", "start_seconds": 8.0, "scene_index": 3},  # not a field kind
        {"kind": "hold", "seconds": 2, "start_seconds": 9.0, "scene_index": 3},  # skipped
        {"kind": "select", "target": "css:#id_status", "value": "active", "note": "set Status to Active", "start_seconds": 12.0, "scene_index": 3},
        {"kind": "fill", "target": "css:#id_contact_email", "note": "her contact", "start_seconds": 20.0, "scene_index": 3},
        {"kind": "scroll_to", "target": "css:#id_x", "note": "", "start_seconds": 99.0, "scene_index": 3},  # no words (id_x → 'x' len<=2 dropped) → skipped
    ]
    marks = build_action_marks(actions, segs)
    kinds = [(m["kind"], m["on_seconds"], m["words"][0]) for m in marks]
    assert kinds == [
        ("scroll_to", 4.0, "description"),
        ("fill", 6.0, "description"),
        ("select", 12.0, "status"),
        ("fill", 20.0, "contact"),
    ]


def test_build_action_marks_skips_when_no_timestamp():
    segs = [(0.0, 10.0)]
    actions = [{"kind": "fill", "target": "css:#id_description", "scene_index": 1}]  # no start_seconds
    assert build_action_marks(actions, segs) == []


if __name__ == "__main__":
    import sys

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
