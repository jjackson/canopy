"""Unit tests for the pre-warm pass (``record_video`` prewarm contract).

The pass exists because cold-cache waits — a 15s first-hit page render, a
7.5s remote-image cold fetch — only need to be PAID once, but without prewarm
they get paid ON CAMERA as frozen frames (program-admin-report iter1/iter2:
~45s of dead space in a 209s film). The legacy hand-built recorder had
``defer_record=True``; this is canopy's equivalent.

Contract pinned here:
  - ``resolve_prewarm``: CLI wins; default = the spec's ``prewarm:`` value;
    absent → off.
  - ``collect_prewarm_urls``: unique resolved scene URLs in spec order —
    ``${var}``-substituted + absolutized (the scenes ``build_scenes_from_spec``
    emits ARE the warmed set), continuation scenes (``url: None``) skipped,
    duplicates visited once.
  - ``run_prewarm``: best-effort — a failing page is logged + recorded in
    provenance and the pass continues; nothing raises.
  - Provenance shape ``{pages, duration_seconds, failures}``; rides on the
    RunReport only when the pass ran (key omitted otherwise, mirroring
    ``setup``).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.narrative.substitution import substitute_scenes  # noqa: E402
from scripts.walkthrough.record_video import (  # noqa: E402
    build_scenes_from_spec,
    collect_prewarm_urls,
    resolve_prewarm,
    run_prewarm,
)
from scripts.walkthrough._lib.results import RunReport  # noqa: E402


# ---------------------------------------------------------------------------
# resolve_prewarm — CLI wins; spec is the default; absent → off
# ---------------------------------------------------------------------------


def test_resolve_prewarm_defaults_off():
    assert resolve_prewarm(None, None) is False


def test_resolve_prewarm_spec_value_is_default():
    assert resolve_prewarm(None, True) is True
    assert resolve_prewarm(None, False) is False


def test_resolve_prewarm_cli_wins_over_spec():
    assert resolve_prewarm(False, True) is False  # --no-prewarm beats prewarm: true
    assert resolve_prewarm(True, False) is True  # --prewarm beats prewarm: false
    assert resolve_prewarm(True, None) is True  # --prewarm with no spec value


# ---------------------------------------------------------------------------
# collect_prewarm_urls — unique resolved URLs in spec order
# ---------------------------------------------------------------------------


def _scenes(spec_scenes: list[dict], *, base_url: str = "https://app.example.com") -> list[dict]:
    return build_scenes_from_spec({"scenes": spec_scenes}, base_url, run_data=None)


def test_collect_unique_urls_in_spec_order():
    scenes = _scenes(
        [
            {"title": "a", "url": "/dash/"},
            {"title": "b", "url": "/runs/7/"},
            {"title": "c", "url": "/dash/"},  # duplicate — visited once
        ]
    )
    assert collect_prewarm_urls(scenes) == [
        "https://app.example.com/dash/",
        "https://app.example.com/runs/7/",
    ]


def test_collect_skips_continuation_scenes():
    """Scenes without a URL stay on the previous scene's page — nothing to warm."""
    scenes = _scenes(
        [
            {"title": "entry", "url": "/dash/"},
            {"title": "continue", "actions": [{"kind": "press", "value": "Enter"}]},
        ]
    )
    assert collect_prewarm_urls(scenes) == ["https://app.example.com/dash/"]


def test_collect_uses_substituted_vars():
    """What gets warmed is what gets filmed: ${var} placeholders resolved first."""
    raw = [{"title": "run page", "url": "/workflow/runs/${run_id}/", "actions": []}]
    resolved = substitute_scenes(raw, {"run_id": 3721})
    scenes = _scenes(resolved)
    assert collect_prewarm_urls(scenes) == ["https://app.example.com/workflow/runs/3721/"]


def test_collect_handles_first_goto_resolved_urls():
    """Scene URLs derived from a leading goto action are warmed too."""
    scenes = _scenes(
        [{"title": "goto-entry", "actions": [{"kind": "goto", "target": "/reports/"}]}]
    )
    assert collect_prewarm_urls(scenes) == ["https://app.example.com/reports/"]


def test_collect_empty_when_no_urls():
    assert collect_prewarm_urls(_scenes([{"title": "narrative-only"}])) == []


def test_collect_skips_capture_bound_urls():
    """A URL whose ${var} is minted on camera (capture-bound) can't be resolved
    pre-render — pre-warm must skip it, not visit a literal placeholder URL."""
    # Simulate post-up-front-substitution state: run_id resolved, sol_id still
    # a placeholder (it's captured on camera by a later scene's capture action).
    scenes = _scenes(
        [
            {"title": "create", "url": "/sol/new/"},
            {"title": "view", "url": "/sol/${sol_id}/"},  # capture-bound, unresolved
        ]
    )
    assert collect_prewarm_urls(scenes) == ["https://app.example.com/sol/new/"]


# ---------------------------------------------------------------------------
# run_prewarm — best-effort visits + provenance
# ---------------------------------------------------------------------------


class FakePage:
    def __init__(self, *, fail_urls: set[str] | None = None, idle_raises: bool = False):
        self.fail_urls = fail_urls or set()
        self.idle_raises = idle_raises
        self.gotos: list[str] = []
        self.load_states: list[tuple] = []

    def goto(self, url, *, wait_until=None, timeout=None):
        self.gotos.append(url)
        if url in self.fail_urls:
            raise RuntimeError(f"net::ERR_TIMED_OUT at {url}")

    def wait_for_load_state(self, state, *, timeout=None):
        self.load_states.append((state, timeout))
        if self.idle_raises:
            raise TimeoutError("networkidle never reached (long-poll)")


class FakeContext:
    def __init__(self, page: FakePage):
        self._page = page

    def new_page(self):
        return self._page


def test_run_prewarm_visits_every_url():
    page = FakePage()
    prov = run_prewarm(FakeContext(page), ["https://a/x", "https://a/y"])
    assert page.gotos == ["https://a/x", "https://a/y"]
    assert prov["pages"] == 2
    assert prov["failures"] == []
    assert isinstance(prov["duration_seconds"], float)


def test_run_prewarm_failure_is_recorded_not_raised():
    """Best-effort: a failing page never aborts the pass — later URLs still warm."""
    page = FakePage(fail_urls={"https://a/x"})
    prov = run_prewarm(FakeContext(page), ["https://a/x", "https://a/y"])
    assert page.gotos == ["https://a/x", "https://a/y"]
    assert len(prov["failures"]) == 1
    assert prov["failures"][0]["url"] == "https://a/x"
    assert "ERR_TIMED_OUT" in prov["failures"][0]["error"]


def test_run_prewarm_settle_is_bounded_and_swallowed():
    """The post-goto settle waits for networkidle with a bounded budget; apps
    that never go idle (long-poll) cost at most the budget, never an error."""
    page = FakePage(idle_raises=True)
    prov = run_prewarm(FakeContext(page), ["https://a/x"], settle_ms=4000, page_timeout_ms=15000)
    assert page.load_states, "settle (networkidle wait) was never attempted"
    state, timeout = page.load_states[0]
    assert state == "networkidle"
    assert 0 < timeout <= 4000
    assert prov["failures"] == []  # idle timeout is NOT a failure


def test_run_prewarm_auth_url_visited_first():
    """URL-based auth replays in the prewarm context so authed pages render
    (a login redirect would warm the login page, not the scene)."""
    page = FakePage()
    run_prewarm(FakeContext(page), ["https://a/x"], auth_url="https://a/auth?t=1")
    assert page.gotos[0] == "https://a/auth?t=1"
    assert page.gotos[1:] == ["https://a/x"]


# ---------------------------------------------------------------------------
# RunReport — prewarm provenance rides the report only when the pass ran
# ---------------------------------------------------------------------------


def test_report_omits_prewarm_key_when_off():
    assert "prewarm" not in RunReport().as_dict()


def test_report_carries_prewarm_provenance_when_on():
    report = RunReport()
    report.prewarm = {"pages": 3, "duration_seconds": 11.2, "failures": []}
    d = report.as_dict()
    assert d["prewarm"] == {"pages": 3, "duration_seconds": 11.2, "failures": []}
