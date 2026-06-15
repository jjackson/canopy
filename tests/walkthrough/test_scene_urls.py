from scripts.walkthrough._lib.results import RunReport


def test_report_records_scene_urls():
    r = RunReport()
    r.record_scene_timing(scene_index=2, title="t", start_seconds=1.0, duration_seconds=3.0)
    r.record_scene_urls(scene_index=2, urls=["https://x/a", "https://x/a", "https://x/b"])
    timing = r.scene_timing_for(2)
    assert timing["start_seconds"] == 1.0
    assert timing["urls_visited"] == ["https://x/a", "https://x/b"]  # deduped, order-preserved
