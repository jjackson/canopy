"""generate_presentation must render directly from the manifest superset.

The render engine now emits walkthrough-run-data.json (the manifest superset
built by scripts.walkthrough.manifest.build_manifest). The deck builder must
consume that shape as-is — no spec-rebuild step. This is a regression guard
that build_presentation_html tolerates a manifest that carries ONLY scene
slides (no synthetic title/summary slide) and fully-resolved URLs.
"""
from scripts.walkthrough._lib.results import RunReport
from scripts.walkthrough.manifest import build_manifest
from scripts.walkthrough.generate_presentation import build_presentation_html


def test_build_presentation_html_renders_from_manifest(tmp_path):
    snap = tmp_path / "snapshots"
    snap.mkdir()
    (snap / "scene_1.png").write_bytes(b"\x89PNG-1")
    report = RunReport()
    report.record_scene_timing(scene_index=1, title="Opens", start_seconds=0.0, duration_seconds=5.0)
    report.record_scene_urls(scene_index=1, urls=["https://labs/x"])
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
        substitution_vars={},
        generated_at="2026-06-14",
        duration_seconds=5.0,
    )

    html_out = build_presentation_html(m)

    assert "Opens" in html_out
    assert "https://labs/x" in html_out
    assert "${" not in html_out
