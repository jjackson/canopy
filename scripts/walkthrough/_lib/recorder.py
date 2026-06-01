"""Interactive recording primitives for DDD walkthrough videos.

The DDD video recorder used to only ``page.goto(url)`` + scroll-pan each scene —
so a rendered demo showed *pages*, never the product being *used*. A demo where
nothing is clicked scores ~1/5 on "demonstrates using the features" no matter how
good the pages look.

This module gives the recorder a synthetic cursor and a small interaction
vocabulary so a scene can declare what the persona *does* (click, fill, open a
menu, dwell, scroll-to) and the recording shows it happening, cursor and all.

Three halves:

1. **Cursor overlay** — :data:`CURSOR_OVERLAY_JS` injects an SVG cursor that
   follows ``mousemove`` and draws a ripple on ``mousedown`` (headless Chromium
   draws no OS cursor). Inject it via ``context.add_init_script(CURSOR_OVERLAY_JS)``
   so it survives navigations.

2. **Primitives** — :func:`click_text`, :func:`click_menu_item`, :func:`fill_field`,
   :func:`select_option`, :func:`scroll_to`, :func:`scroll_page`, :func:`wait_for`,
   :func:`hover`. Each glides the cursor onto its target before acting and
   returns an :class:`ActionResult` so failures stop hiding. All target
   resolution flows through :mod:`._lib.targets` — one resolver to rule them
   all, instead of a different selector ladder per primitive. All timing flows
   through :class:`RecorderConfig` — one place to tune pace, instead of magic
   numbers scattered across primitives.

3. **Dispatcher** — :func:`execute_action` turns one declarative ``Action`` (from
   a scene's ``actions`` list) into the right primitive call. Unknown verbs are
   reported (``error_kind="unknown_kind"``) but never fatal.

Pure helpers over a Playwright ``Page`` — no labs/canopy coupling, so any
walkthrough can import them.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

from .config import RecorderConfig
from .results import ActionAssertError, ActionResult
from .targets import resolve_target, wait_for_target

# ACTION_KINDS lives in the DDD schema (single source of truth — keeps the
# Pydantic Literal and the dispatcher vocabulary in sync). Imported lazily
# to avoid a hard dependency on pydantic when the recorder is used standalone.
try:
    from scripts.ddd.schemas.models import ACTION_KINDS  # noqa: F401
except Exception:  # pragma: no cover — recorder may run without the ddd package on PYTHONPATH
    ACTION_KINDS = (
        "goto", "click", "click_menu", "fill", "select", "type", "press",
        "hover", "scroll_to", "scroll", "wait_for", "hold",
    )

CURSOR_OVERLAY_JS = (Path(__file__).resolve().parent / "cursor_overlay.js").read_text()


# --------------------------------------------------------------------------- #
# cursor motion
# --------------------------------------------------------------------------- #


def slow_move(page: Page, x: float, y: float, *, steps: int = 36) -> None:
    """Mouse move with enough steps that the cursor overlay animates the glide.

    Deliberately slow — a cursor that teleports reads as a jump-cut; a cursor that
    visibly travels to its target reads as a person operating the page.
    """
    page.mouse.move(x, y, steps=steps)


def _glide_to(page: Page, target: str, *, config: RecorderConfig, dwell_ms: int | None = None):
    """Resolve ``target``, glide the cursor to its centre, dwell, return the ResolvedTarget.

    Returns ``None`` if the target didn't resolve in :attr:`config.glide_timeout_ms`.
    The caller decides what that means (a failed click logs + returns False;
    a failed hover is a no-op).
    """
    rt = resolve_target(page, target, timeout_ms=config.glide_timeout_ms)
    if rt is None:
        return None
    slow_move(page, rt.box["x"], rt.box["y"], steps=config.cursor_steps)
    page.wait_for_timeout(dwell_ms if dwell_ms is not None else config.glide_dwell_ms)
    return rt


# --------------------------------------------------------------------------- #
# interaction primitives
# --------------------------------------------------------------------------- #


def click_text(page: Page, target: str, *, config: RecorderConfig | None = None) -> bool:
    """Glide the cursor onto ``target`` (text or selector), pause, and click it.

    The pre-click dwell + the overlay's click feedback (press-pulse + ring + a
    lingering dot) make it unmistakable WHERE the click landed — we re-measure
    the box right before clicking so the dot lands on the element, not a stale
    spot from before a layout shift.
    """
    cfg = config or RecorderConfig()
    rt = _glide_to(page, target, config=cfg, dwell_ms=cfg.click_dwell_ms)
    if rt is None:
        print(f"  ! click target not found: {target!r}")
        return False
    # Re-resolve right before the click in case a settle or layout shift moved
    # the target. The re-resolution uses the same heuristic so we don't end up
    # clicking a different element than we glided to.
    rt2 = resolve_target(page, target, timeout_ms=cfg.interaction_timeout_ms)
    box = (rt2 or rt).box
    slow_move(page, box["x"], box["y"], steps=cfg.cursor_steps_short)
    page.wait_for_timeout(cfg.pre_click_dwell_ms)
    page.mouse.click(box["x"], box["y"])
    page.wait_for_timeout(cfg.post_click_settle_ms)
    return True


def click_menu_item(page: Page, item_text: str, *, config: RecorderConfig | None = None) -> bool:
    """Click an item inside an open dropdown/popover, gliding the cursor onto it.

    Same resolver as :func:`click_text`, shorter post-click settle — menus
    are usually quicker to react than a top-level button click.
    """
    cfg = config or RecorderConfig()
    rt = _glide_to(page, item_text, config=cfg)
    if rt is None:
        print(f"  ! menu item not found: {item_text!r}")
        return False
    page.mouse.click(rt.box["x"], rt.box["y"])
    page.wait_for_timeout(cfg.menu_click_settle_ms)
    return True


def fill_field(page: Page, target: str, value: str, *, config: RecorderConfig | None = None) -> bool:
    """Glide to an input, click to focus, clear, then type ``value`` character-by-character.

    Tries the unified resolver first (CSS / testid / aria / role / text). When
    the resolved target is a Playwright ``Locator``, uses ``locator.fill('')``
    to clear and ``locator.type(value, delay=...)`` so the typing fires real
    ``input`` events (which any reactive form depends on — see the
    ``microplans-10-wards`` bulk-create button that stayed disabled because
    a raw ``element.value =`` setter never fired ``input``).
    """
    cfg = config or RecorderConfig()
    rt = _glide_to(page, target, config=cfg, dwell_ms=cfg.pre_fill_dwell_ms)
    if rt is None:
        # Last-resort fallback for bare targets that resolved via text — try
        # a couple of input-shaped CSS variants. Useful for old specs that
        # write a placeholder string as the bare target (e.g.
        # ``target: "ward-list"`` meaning "the textarea whose id or
        # placeholder is ward-list").
        for sel in (f"#{target}", f"input[placeholder*={target!r}]",
                    f"textarea[placeholder*={target!r}]", f"[aria-label*={target!r}]"):
            rt = resolve_target(page, "css:" + sel, timeout_ms=cfg.interaction_timeout_ms)
            if rt is not None:
                slow_move(page, rt.box["x"], rt.box["y"], steps=cfg.cursor_steps)
                page.wait_for_timeout(cfg.pre_fill_dwell_ms)
                break
        else:
            print(f"  ! fill target not found: {target!r}")
            return False
    if rt.locator is not None:
        rt.locator.click()
        rt.locator.fill("")
        rt.locator.type(value, delay=cfg.typing_delay_ms)
    else:
        # Text-resolved target — fall back to coordinate click + keyboard type.
        page.mouse.click(rt.box["x"], rt.box["y"])
        page.keyboard.type(value, delay=cfg.typing_delay_ms)
    page.wait_for_timeout(cfg.post_fill_settle_ms)
    return True


def select_option(page: Page, target: str, value: str, *, config: RecorderConfig | None = None) -> bool:
    """Pick an option from a ``<select>`` element.

    Native HTML selects can't be opened+clicked via ``page.mouse.click`` reliably
    across platforms — Playwright's ``locator.select_option`` is the canonical
    way to drive them. We glide the synthetic cursor onto the select so the
    viewer sees which control is being driven (the dropdown won't visually open
    — that's a native-control limitation; the new value flips on the closed
    widget).

    ``value`` is interpreted as the option's ``value`` attribute first, then a
    digit-only string as the 0-based ``index``, then the visible text ``label``.
    Returns False (with a printed warning) if none of those match.
    """
    cfg = config or RecorderConfig()
    rt = _glide_to(page, target, config=cfg, dwell_ms=cfg.pre_select_dwell_ms)
    if rt is None:
        # Old-spec fallback: a bare target that's actually an id of a <select>.
        for sel in (f"select#{target}", f"#{target}",
                    f"select[aria-label*={target!r}]", f"select[name={target!r}]"):
            rt = resolve_target(page, "css:" + sel, timeout_ms=cfg.interaction_timeout_ms)
            if rt is not None:
                slow_move(page, rt.box["x"], rt.box["y"], steps=cfg.cursor_steps)
                page.wait_for_timeout(cfg.pre_select_dwell_ms)
                break
        else:
            print(f"  ! select target not found: {target!r}")
            return False
    if rt.locator is None:
        print(f"  ! select target resolved by text, not a <select>: {target!r}")
        return False
    val = str(value)
    attempts: list[dict] = [{"value": val}]
    if val.lstrip("-").isdigit():
        attempts.append({"index": int(val)})
    attempts.append({"label": val})
    for attempt in attempts:
        try:
            rt.locator.select_option(**attempt)
            page.wait_for_timeout(cfg.post_select_settle_ms)
            return True
        except Exception:
            continue
    print(f"  ! select_option failed: {target!r} value={value!r}")
    return False


def hover(page: Page, target: str, *, seconds: float | None = None, config: RecorderConfig | None = None) -> bool:
    """Glide the cursor onto ``target`` and rest. No click."""
    cfg = config or RecorderConfig()
    dwell_ms = int(seconds * 1000) if seconds is not None else cfg.glide_dwell_ms
    rt = _glide_to(page, target, config=cfg, dwell_ms=dwell_ms)
    return rt is not None


def scroll_to(page: Page, target: str, *, config: RecorderConfig | None = None) -> bool:
    """Smooth-scroll the element matching ``target`` into view.

    Uses the same target resolver as the other primitives — so the same
    selector syntax works for ``scroll_to`` as for ``click``. After resolving
    we run the in-page smooth scroll, then dwell so the motion is visible.
    """
    cfg = config or RecorderConfig()
    rt = resolve_target(page, target, timeout_ms=cfg.glide_timeout_ms)
    if rt is None:
        return False
    # The resolver already scrolled the element to centre, but it used
    # ``behavior: 'instant'``. Re-run a smooth scroll for the visible motion.
    if rt.locator is not None:
        try:
            rt.locator.scroll_into_view_if_needed()
        except Exception:
            pass
    page.evaluate(
        """([x, y]) => window.scrollTo({top: y + window.scrollY - window.innerHeight / 2, behavior: 'smooth'})""",
        [rt.box["x"], rt.box["y"]],
    )
    page.wait_for_timeout(cfg.scroll_settle_ms)
    return True


def scroll_page(page: Page, to: str = "bottom", *, max_duration_ms: int = 4000) -> None:
    """Eased scroll to ``"top"``, ``"bottom"``, or a pixel offset."""
    if to == "top":
        page.evaluate("() => window.scrollTo({top: 0, behavior: 'smooth'})")
        page.wait_for_timeout(600)
        return
    if to.isdigit():
        page.evaluate("(y) => window.scrollTo({top: y, behavior: 'smooth'})", int(to))
        page.wait_for_timeout(600)
        return
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


def wait_for(page: Page, target: str, *, config: RecorderConfig | None = None) -> bool:
    """Wait for ``target`` (text or selector) to appear, or pause for N ms if ``target`` is all digits.

    Plain-text targets skip the selector engine entirely — see
    :func:`._lib.targets.wait_for_target` for the rationale.
    """
    cfg = config or RecorderConfig()
    return wait_for_target(page, target, timeout_ms=cfg.wait_for_timeout_ms)


# --------------------------------------------------------------------------- #
# dispatcher
# --------------------------------------------------------------------------- #


def execute_action(
    page: Page,
    action: dict[str, Any],
    *,
    base_url: str = "",
    config: RecorderConfig | None = None,
) -> ActionResult:
    """Execute one declarative ``Action`` (from ``scene.actions``) with the cursor.

    Returns an :class:`ActionResult` describing what happened. A bad action
    yields ``ok=False`` with a tagged ``error_kind`` but does NOT raise — unless
    the action sets ``must_succeed: true``, in which case the failure raises
    :class:`ActionAssertError` for the orchestrator to handle.

    Returning a result (instead of ``None`` as before) lets the orchestrator
    accumulate a :class:`RunReport` so silent failures stop hiding.
    """
    cfg = config or RecorderConfig()
    kind = (action.get("kind") or "").strip()
    target = action.get("target")
    value = action.get("value")
    seconds = action.get("seconds")
    note = action.get("note")
    must_succeed = bool(action.get("must_succeed", False))

    label = f"{kind}({target or value or ''})"
    if note:
        label += f"  — {note}"
    print(f"    · {label}")

    start = time.monotonic()
    ok = True
    error_kind: str | None = None
    error_message: str | None = None

    try:
        if kind == "goto":
            url = (target or value or "").strip()
            if url.startswith("/"):
                url = base_url.rstrip("/") + url
            page.goto(url, wait_until="domcontentloaded", timeout=cfg.goto_timeout_ms)
            page.wait_for_timeout(cfg.goto_settle_ms)
        elif kind == "click":
            ok = click_text(page, target or value or "", config=cfg)
            if not ok:
                error_kind = "target_not_found"
        elif kind == "click_menu":
            ok = click_menu_item(page, target or value or "", config=cfg)
            if not ok:
                error_kind = "target_not_found"
        elif kind == "fill":
            ok = fill_field(page, target or "", value or "", config=cfg)
            if not ok:
                error_kind = "target_not_found"
        elif kind == "select":
            ok = select_option(page, target or "", value or "", config=cfg)
            if not ok:
                error_kind = "target_not_found"
        elif kind == "type":
            page.keyboard.type(value or "", delay=cfg.typing_delay_ms)
        elif kind == "press":
            page.keyboard.press(value or "Enter")
        elif kind == "hover":
            ok = hover(page, target or value or "", seconds=seconds, config=cfg)
            if not ok:
                error_kind = "target_not_found"
        elif kind == "scroll_to":
            ok = scroll_to(page, target or value or "", config=cfg)
            if not ok:
                error_kind = "target_not_found"
        elif kind == "scroll":
            scroll_page(page, value or "bottom")
        elif kind == "wait_for":
            ok = wait_for(page, str(target or value or "1000"), config=cfg)
            if not ok:
                error_kind = "timeout"
        elif kind == "hold":
            page.wait_for_timeout(int(float(seconds or value or 1.0) * 1000))
        else:
            ok = False
            error_kind = "unknown_kind"
            error_message = f"unknown action kind: {kind!r}"
            print(f"    ! {error_message} (skipped)")
    except Exception as e:  # noqa: BLE001
        ok = False
        error_kind = "playwright"
        error_message = str(e)
        print(f"    ! action {label} failed: {e}")

    elapsed_ms = int((time.monotonic() - start) * 1000)
    result = ActionResult(
        kind=kind, ok=ok, target=target, value=value, note=note,
        elapsed_ms=elapsed_ms, error_kind=error_kind, error_message=error_message,
    )
    if not ok and must_succeed:
        raise ActionAssertError(f"required action failed: {label}: {error_message or error_kind}")
    return result
