"""_write_render_artifacts emits the manifest for ONLY the recorded scenes,
so a partial render (a failed scene aborts the spec) still yields a usable
manifest of what actually rendered.
"""
import argparse
import json
from pathlib import Path

from scripts.walkthrough.record_video import _write_render_artifacts
from scripts.walkthrough._lib.results import RunReport


class _Rec:
    def __init__(self, report):
        self.report = report


def test_partial_render_manifest_only_recorded_scenes(tmp_path):
    snap = tmp_path / "snapshots"
    snap.mkdir()
    # Spec declares 4 scenes; only 1 and 2 actually rendered (have snapshots + timings).
    for i in (1, 2):
        (snap / f"scene_{i}.png").write_bytes(b"\x89PNG")
    report = RunReport()
    report.record_scene_timing(scene_index=1, title="A", start_seconds=0.0, duration_seconds=2.0)
    report.record_scene_timing(scene_index=2, title="B", start_seconds=2.0, duration_seconds=3.0)
    spec = {"name": "PAR", "narrative": "n", "base_url": "https://labs",
            "personas": {"amani": {"name": "Amani"}},
            "scenes": [{"title": "A", "persona": "amani", "url": "https://labs/1"},
                       {"title": "B", "persona": "amani", "url": "https://labs/2"},
                       {"title": "C", "persona": "amani", "url": "https://labs/3"},
                       {"title": "D", "persona": "amani", "url": "https://labs/4"}]}
    args = argparse.Namespace(
        report=str(tmp_path / "run-report.json"),
        manifest=str(tmp_path / "walkthrough-run-data.json"),
        snapshots=str(snap),
    )
    _write_render_artifacts(args, spec, _Rec(report), {"variables": {"x": "/y"}}, total_seconds=5.0)

    assert Path(args.report).exists()
    m = json.load(open(args.manifest))
    # only the 2 recorded scenes, NOT all 4 spec scenes
    assert m["scenes_run"] == [1, 2]
    assert [s["scene_index"] for s in m["slides"]] == [1, 2]
    assert m["duration_seconds"] == 5.0
