import base64

from scripts.walkthrough._lib.results import RunReport
from scripts.walkthrough.manifest import build_manifest


def test_build_manifest_superset(tmp_path):
    snap = tmp_path / "snapshots"
    snap.mkdir()
    (snap / "scene_1.png").write_bytes(b"\x89PNG-1")
    (snap / "scene_1_page_text.json").write_text("{}")
    report = RunReport()
    report.record_scene_timing(scene_index=1, title="Opens", start_seconds=0.0, duration_seconds=5.0)
    report.record_scene_urls(scene_index=1, urls=["https://labs/x", "https://labs/audit/4317/bulk"])
    spec = {
        "name": "PAR",
        "narrative": "n",
        "base_url": "https://labs",
        "personas": {"amani": {"name": "Amani", "color": "#111"}},
        "scenes": [{"title": "Opens", "persona": "amani", "narrative": "Amani opens", "url": "https://labs/x"}],
    }
    m = build_manifest(
        spec=spec,
        report=report,
        snapshots_dir=snap,
        scenes_run=[1],
        scene_filter=None,
        substitution_vars={"wk4_url": "/labs/x"},
        generated_at="2026-06-14",
    )
    assert m["name"] == "PAR"
    assert m["substitution_vars"] == {"wk4_url": "/labs/x"}
    s = m["slides"][0]
    assert s["type"] == "scene" and s["scene_index"] == 1 and s["scene_total"] == 1
    assert s["url"] == "https://labs/x"
    assert "https://labs/audit/4317/bulk" in s["urls_visited"]
    assert s["screenshot_path"] == "snapshots/scene_1.png"
    assert s["mp4_start_offset"] == 0.0
    assert s["ai_evaluation"] is None
    assert base64.b64decode(s["screenshot_b64"]) == b"\x89PNG-1"
