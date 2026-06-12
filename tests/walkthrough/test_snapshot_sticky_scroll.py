"""Tests for the sticky-header capture guard in ``Recorder.take_snapshot``.

Background: Chromium's beyond-viewport capture (Playwright ``full_page=True``)
paints ``position: sticky``/``fixed`` elements at the LIVE scroll offset. A
scene that ends scrolled down gets its navbar stamped mid-image and a
bar-less, clipped document top (seen on program-admin-report iter1: navbar
mid-viewport in ~8 of 14 captures; judges read it as a broken render).

Contract:
  - full_page capture on a scrolled page → scroll to (0, 0) BEFORE the
    screenshot, restore the original scrollY AFTER it.
  - full_page capture already at the top (scrollY == 0) → no scroll calls.
  - ``full_page: false`` (viewport capture) → no scroll correction at all;
    the viewport IS the artifact.
  - Scroll evaluation failing → capture proceeds uncorrected (best-effort).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.walkthrough._lib.orchestrator import Recorder  # noqa: E402


class ScrolledPage:
    """Page-shaped stub that reports a scroll offset and records the order of
    scroll evaluations vs screenshot calls."""

    def __init__(self, *, scroll_y: int = 1200, scroll_eval_raises: bool = False):
        self.url = "https://example.com/audit/3832/"
        self._scroll_y = scroll_y
        self.scroll_eval_raises = scroll_eval_raises
        self.calls: list[str] = []  # interleaved event log

    def wait_for_timeout(self, ms):
        self.calls.append(f"wait:{int(ms)}")

    def screenshot(self, *, path: str, full_page: bool = False, timeout: int | None = None):
        self.calls.append(f"screenshot:full_page={full_page}")
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\n")

    def evaluate(self, script, *args):
        if "window.scrollY" in script:
            if self.scroll_eval_raises:
                raise RuntimeError("execution context destroyed (mock)")
            self.calls.append("read-scrollY")
            return self._scroll_y
        if "scrollTo" in script:
            self.calls.append(f"eval:{script.split('=>')[-1].strip()}")
            return None
        if "innerText" in script:
            return "page text"
        return None


def _scene(*, full_page=None) -> dict:
    scene = {"title": "Audit drill", "actions": [{"kind": "press", "value": "Enter"}]}
    if full_page is not None:
        scene["full_page"] = full_page
    return scene


def test_full_page_capture_scrolls_to_top_and_restores(tmp_path):
    page = ScrolledPage(scroll_y=1200)
    rec = Recorder(snapshot_dir=tmp_path)
    rec.take_snapshot(page, _scene(), 3)

    shot = page.calls.index("screenshot:full_page=True")
    to_top = next(i for i, c in enumerate(page.calls) if "scrollTo(0, 0)" in c)
    restore = next(i for i, c in enumerate(page.calls) if "scrollTo(0, 1200)" in c)
    assert to_top < shot < restore, page.calls
    assert (tmp_path / "scene_3.png").exists()


def test_full_page_capture_at_top_skips_scroll_calls(tmp_path):
    page = ScrolledPage(scroll_y=0)
    rec = Recorder(snapshot_dir=tmp_path)
    rec.take_snapshot(page, _scene(), 4)

    assert not any("scrollTo" in c for c in page.calls), page.calls
    assert (tmp_path / "scene_4.png").exists()


def test_viewport_capture_never_scrolls(tmp_path):
    page = ScrolledPage(scroll_y=1200)
    rec = Recorder(snapshot_dir=tmp_path)
    rec.take_snapshot(page, _scene(full_page=False), 5)

    assert not any("scrollTo" in c or c == "read-scrollY" for c in page.calls), page.calls
    assert (tmp_path / "scene_5.png").exists()


def test_scroll_eval_failure_still_captures(tmp_path):
    page = ScrolledPage(scroll_y=1200, scroll_eval_raises=True)
    rec = Recorder(snapshot_dir=tmp_path)
    rec.take_snapshot(page, _scene(), 6)

    assert any(c.startswith("screenshot:") for c in page.calls), page.calls
    assert (tmp_path / "scene_6.png").exists()
