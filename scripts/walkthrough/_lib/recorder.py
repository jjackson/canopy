"""Interactive recording primitives for DDD walkthrough videos.

The DDD video recorder used to only ``page.goto(url)`` + scroll-pan each scene —
so a rendered demo showed *pages*, never the product being *used*. A demo where
nothing is clicked scores ~1/5 on "demonstrates using the features" no matter how
good the pages look.

This module gives the recorder a synthetic cursor and a small interaction
vocabulary so a scene can declare what the persona *does* (click, fill, open a
menu, dwell, scroll-to) and the recording shows it happening, cursor and all.

Two halves:

1. **Cursor overlay** — ``CURSOR_OVERLAY_JS`` injects an SVG cursor that follows
   ``mousemove`` and draws a ripple on ``mousedown`` (headless Chromium draws no
   OS cursor). Inject it via ``context.add_init_script(CURSOR_OVERLAY_JS)`` so it
   survives navigations.

2. **Primitives + dispatcher** — ``slow_move`` / ``click_text`` / ``fill_field`` /
   ``click_menu_item`` / ``dwell`` / ``scroll_to`` / … glide the cursor to a target
   before acting, so the motion reads as deliberate. ``execute_action`` maps one
   declarative ``Action`` (from the unified spec's ``scene.actions``) onto these.

Pure helpers over a Playwright ``Page`` — no labs/canopy coupling, so any
walkthrough can import them.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

CURSOR_OVERLAY_JS = (Path(__file__).resolve().parent / "cursor_overlay.js").read_text()

# Action verbs the recorder understands. Kept small and demonstrative — this is
# the vocabulary a DDD scene uses to show a feature being operated. Keep in sync
# with scripts/ddd/schemas/models.py:Action and ddd-spec's authoring guidance.
ACTION_KINDS = (
    "goto",       # navigate to a url (target=url)
    "click",      # click a visible text label or CSS selector (target)
    "click_menu", # click an item inside the currently-open dropdown (target=item text)
    "fill",       # focus a field (target=label or selector) and type value
    "type",       # type value into whatever is focused
    "press",      # press a key (value, e.g. "Enter")
    "hover",      # glide the cursor onto target and rest (no click)
    "scroll_to",  # smooth-scroll target into view
    "scroll",     # scroll the page (value: "bottom" | "top" | "<px>")
    "wait_for",   # wait for target text/selector to appear, or value=ms
    "hold",       # dwell in place for seconds (value or seconds)
)


# --------------------------------------------------------------------------- #
# cursor motion
# --------------------------------------------------------------------------- #


def slow_move(page: Page, x: float, y: float, steps: int = 36) -> None:
    """Mouse move with enough steps that the cursor overlay animates the glide.

    Deliberately slow — a cursor that teleports reads as a jump-cut; a cursor that
    visibly travels to its target reads as a person operating the page."""
    page.mouse.move(x, y, steps=steps)


def _box_center(page: Page, target: str) -> dict | None:
    """Viewport-center {x, y} of the first element matching ``target``.

    ``target`` is a CSS selector if it starts with one of ``# . [`` or contains
    no spaces and looks selector-ish; otherwise it's treated as visible text.
    Scrolls the element to center first so the click lands on-screen (a click the
    viewer can't see is a recording bug, not just a functional one).
    """
    js = """(t) => {
        let el = null;
        try { el = document.querySelector(t); } catch (e) { el = null; }
        if (!el) {
            const all = [...document.querySelectorAll('button, a, [role=button], summary, label, span, div, td, th, h1, h2, h3')];
            el = all.find(e => e.innerText && e.innerText.trim() === t)
              || all.find(e => e.innerText && e.innerText.trim().includes(t));
        }
        if (!el) return null;
        el.scrollIntoView({behavior: 'instant', block: 'center'});
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) return null;
        return {x: r.x + r.width / 2, y: r.y + r.height / 2};
    }"""
    return page.evaluate(js, target)


def _glide_to(page: Page, target: str, *, timeout_ms: int = 6000, dwell_s: float = 0.35) -> dict | None:
    """Wait for ``target`` to exist, glide the cursor to its center, dwell, return box."""
    deadline = time.time() + timeout_ms / 1000
    box = None
    while time.time() < deadline:
        box = _box_center(page, target)
        if box:
            break
        page.wait_for_timeout(150)
    if not box:
        return None
    slow_move(page, box["x"], box["y"])
    page.wait_for_timeout(int(dwell_s * 1000))
    return box


# --------------------------------------------------------------------------- #
# interaction primitives
# --------------------------------------------------------------------------- #


def click_text(page: Page, target: str, *, timeout_ms: int = 6000, settle_ms: int = 900) -> bool:
    """Glide the cursor onto ``target`` (text or selector), pause, and click it.

    The pre-click dwell + the overlay's click feedback (press-pulse + ring + a
    lingering dot) make it unmistakable WHERE the click landed — re-measure the
    box right before clicking so the dot lands on the element, not a stale spot."""
    box = _glide_to(page, target, timeout_ms=timeout_ms, dwell_s=0.5)
    if not box:
        print(f"  ! click target not found: {target!r}")
        return False
    box = _box_center(page, target) or box  # re-measure post-glide (page may have shifted)
    slow_move(page, box["x"], box["y"], steps=10)
    page.wait_for_timeout(250)
    page.mouse.click(box["x"], box["y"])
    page.wait_for_timeout(settle_ms)
    return True


def click_menu_item(page: Page, item_text: str, *, timeout_ms: int = 5000) -> bool:
    """Click an item inside an open dropdown/popover, gliding the cursor onto it.

    Matches a button/anchor by visible text anywhere on the page (menus are
    usually absolutely-positioned with no stable id). Verifies on-viewport.
    """
    box = _glide_to(page, item_text, timeout_ms=timeout_ms)
    if not box:
        print(f"  ! menu item not found: {item_text!r}")
        return False
    page.mouse.click(box["x"], box["y"])
    page.wait_for_timeout(700)
    return True


def fill_field(page: Page, target: str, value: str, *, timeout_ms: int = 6000) -> bool:
    """Glide to an input (by placeholder/label text, id, or selector), click it,
    and type ``value`` character-by-character so the typing is visible."""
    selectors = [
        target,
        f"#{target}",
        f"input[placeholder*='{target}']",
        f"textarea[placeholder*='{target}']",
        f"[aria-label*='{target}']",
    ]
    handle = None
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=1200)
            handle = loc
            break
        except Exception:
            continue
    if handle is None:
        # last resort: a <label> whose text matches, then its control
        box = _glide_to(page, target, timeout_ms=timeout_ms)
        if not box:
            print(f"  ! fill target not found: {target!r}")
            return False
        page.mouse.click(box["x"], box["y"])
        page.keyboard.type(value, delay=45)
        return True
    box = handle.bounding_box()
    if box:
        slow_move(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_timeout(200)
    handle.click()
    handle.fill("")
    handle.type(value, delay=45)
    page.wait_for_timeout(300)
    return True


def scroll_to(page: Page, target: str) -> bool:
    """Smooth-scroll the element matching ``target`` into view."""
    return bool(
        page.evaluate(
            """(t) => {
                let el = null;
                try { el = document.querySelector(t); } catch (e) {}
                if (!el) {
                    const all = [...document.querySelectorAll('*')];
                    el = all.find(e => e.children.length === 0 && e.textContent && e.textContent.trim() === t)
                      || all.find(e => e.textContent && e.textContent.includes(t));
                }
                if (!el) return false;
                el.scrollIntoView({behavior: 'smooth', block: 'center'});
                return true;
            }""",
            target,
        )
    )


def scroll_page(page: Page, to: str = "bottom", *, max_duration_ms: int = 4000) -> None:
    """Eased scroll to bottom/top or to a pixel offset."""
    if to == "top":
        page.evaluate("() => window.scrollTo({top: 0, behavior: 'smooth'})")
        page.wait_for_timeout(600)
        return
    if to.isdigit():
        page.evaluate("(y) => window.scrollTo({top: y, behavior: 'smooth'})", int(to))
        page.wait_for_timeout(600)
        return
    # bottom (eased)
    page.evaluate(
        """(maxDur) => new Promise(res => {
            const dist = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
            if (dist <= 50) return res();
            const start = performance.now();
            const dur = Math.min(maxDur, dist * 1.3);
            function step(t) {
                const r = Math.min(1, (t - start) / dur);
                const eased = r < 0.5 ? 4*r*r*r : 1 - Math.pow(-2*r + 2, 3)/2;
                window.scrollTo(0, dist * eased);
                if (r < 1) requestAnimationFrame(step); else res();
            }
            requestAnimationFrame(step);
        })""",
        max_duration_ms,
    )


def wait_for(page: Page, target: str, *, timeout_ms: int = 12000) -> bool:
    """Wait for text or a selector to appear. If ``target`` is all digits, treat
    it as a millisecond pause instead."""
    if target.isdigit():
        page.wait_for_timeout(int(target))
        return True
    try:
        # try as selector first, then as text
        try:
            page.wait_for_selector(target, timeout=timeout_ms)
            return True
        except Exception:
            page.wait_for_function(
                "(t) => document.body && document.body.innerText.includes(t)",
                arg=target,
                timeout=timeout_ms,
            )
            return True
    except Exception as e:
        print(f"  ! wait_for {target!r} timed out: {e}")
        return False


# --------------------------------------------------------------------------- #
# dispatcher
# --------------------------------------------------------------------------- #


def execute_action(page: Page, action: dict[str, Any], *, base_url: str = "") -> None:
    """Execute one declarative ``Action`` (from ``scene.actions``) with the cursor.

    Action shape (all optional except ``kind``)::

        {kind, target, value, seconds, note}

    Unknown kinds are logged and skipped — a bad action never aborts the render.
    """
    kind = (action.get("kind") or "").strip()
    target = action.get("target")
    value = action.get("value")
    seconds = action.get("seconds")
    note = action.get("note")
    label = f"{kind}({target or value or ''})"
    if note:
        label += f"  — {note}"
    print(f"    · {label}")

    try:
        if kind == "goto":
            url = target or value or ""
            if url.startswith("/"):
                url = base_url.rstrip("/") + url
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1200)
        elif kind == "click":
            click_text(page, target or value or "")
        elif kind == "click_menu":
            click_menu_item(page, target or value or "")
        elif kind == "fill":
            fill_field(page, target or "", value or "")
        elif kind == "type":
            page.keyboard.type(value or "", delay=45)
        elif kind == "press":
            page.keyboard.press(value or "Enter")
        elif kind == "hover":
            _glide_to(page, target or value or "", dwell_s=float(seconds or 0.8))
        elif kind == "scroll_to":
            scroll_to(page, target or value or "")
            page.wait_for_timeout(600)
        elif kind == "scroll":
            scroll_page(page, (value or "bottom"))
        elif kind == "wait_for":
            wait_for(page, str(target or value or "1000"))
        elif kind == "hold":
            page.wait_for_timeout(int(float(seconds or value or 1.0) * 1000))
        else:
            print(f"    ! unknown action kind: {kind!r} (skipped)")
    except Exception as e:  # noqa: BLE001 — one bad step must not kill the render
        print(f"    ! action {label} failed: {e}")
