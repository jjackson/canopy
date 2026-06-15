from scripts.walkthrough._lib import orchestrator
from scripts.walkthrough._lib.orchestrator import Recorder
from scripts.walkthrough._lib.results import ActionResult, RunReport


def test_report_records_scene_urls():
    r = RunReport()
    r.record_scene_timing(scene_index=2, title="t", start_seconds=1.0, duration_seconds=3.0)
    r.record_scene_urls(scene_index=2, urls=["https://x/a", "https://x/a", "https://x/b"])
    timing = r.scene_timing_for(2)
    assert timing["start_seconds"] == 1.0
    assert timing["urls_visited"] == ["https://x/a", "https://x/b"]  # deduped, order-preserved


class FakePage:
    """Minimal Page surface for ``run_scene``; ``.url`` is a mutable attr."""

    def __init__(self, url="https://x/a"):
        self.url = url

    def wait_for_timeout(self, ms):
        pass

    def wait_for_load_state(self, *a, **k):
        pass

    def goto(self, url, *, wait_until=None, timeout=None):
        self.url = url

    def screenshot(self, **kwargs):
        pass

    def evaluate(self, script, *args):
        return ""


def test_orchestrator_records_urls_when_click_navigates(monkeypatch):
    """A click that flips ``page.url`` lands both URLs in ``urls_visited``."""
    page = FakePage(url="https://x/a")

    def fake_execute_action(pg, action, *, base_url="", config=None):
        if action.get("kind") == "click":
            pg.url = "https://x/b"  # the click redirected
        return ActionResult(kind=action.get("kind", "?"), ok=True)

    monkeypatch.setattr(orchestrator, "execute_action", fake_execute_action)

    rec = Recorder()
    rec.run_scene(page, {"title": "s", "scene_index": 1, "actions": [{"kind": "click", "target": "x"}]})

    timing = rec.report.scene_timing_for(1)
    assert timing["urls_visited"] == ["https://x/a", "https://x/b"]
