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
from .targets import measure_box, resolve_target, wait_for_target

# ACTION_KINDS lives in the neutral narrative substrate (single source of
# truth — keeps the Pydantic Literal and the dispatcher vocabulary in sync). A
# renderer must not depend on a methodology, so this imports from
# scripts.narrative, not scripts.ddd. Imported lazily to avoid a hard
# dependency on pydantic when the recorder is used standalone.
try:
    from scripts.narrative.models import ACTION_KINDS  # noqa: F401
except Exception:  # pragma: no cover — recorder may run without the narrative package on PYTHONPATH
    ACTION_KINDS = (
        "goto", "click", "click_menu", "fill", "select", "type", "press",
        "hover", "scroll_to", "scroll", "wait_for", "hold", "draw",
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
    """Glide the cursor onto ``target`` and click via ``Locator.click``.

    The cursor glide is visual: ``slow_move`` chunks the move so the overlay
    animates, the pre-click dwell gives the viewer time to register WHERE
    the click is about to land, and the overlay's click feedback (press-pulse
    + ring + lingering dot) fires from the real ``mousedown``.

    The click itself goes through ``Locator.click()`` — actionability checks
    intact (visible, stable, receives events, enabled, not detached). This
    matters: a video where the click silently misses an obscured element
    used to look identical to a successful click; with ``Locator.click()``
    the timeout fires loudly and the failure shows up in the run report.
    """
    cfg = config or RecorderConfig()
    rt = _glide_to(page, target, config=cfg, dwell_ms=cfg.click_dwell_ms)
    if rt is None:
        print(f"  ! click target not found: {target!r}")
        return False
    # Re-measure right before the click in case a settle moved the element
    # mid-glide; the cursor lands on its current centre, not where it was.
    box = measure_box(rt.locator) or rt.box
    slow_move(page, box["x"], box["y"], steps=cfg.cursor_steps_short)
    page.wait_for_timeout(cfg.pre_click_dwell_ms)
    try:
        rt.locator.click(timeout=cfg.interaction_timeout_ms)
    except Exception as e:
        print(f"  ! click failed (actionability): {target!r}: {e}")
        return False
    page.wait_for_timeout(cfg.post_click_settle_ms)
    return True


def click_menu_item(page: Page, item_text: str, *, config: RecorderConfig | None = None) -> bool:
    """Click an item inside an open dropdown / popover.

    Same resolver as :func:`click_text`, shorter post-click settle (menus
    react faster than top-level buttons). The verb is kept distinct so
    spec authors signal "this click closes a menu" — useful for graders.
    """
    cfg = config or RecorderConfig()
    rt = _glide_to(page, item_text, config=cfg)
    if rt is None:
        print(f"  ! menu item not found: {item_text!r}")
        return False
    try:
        rt.locator.click(timeout=cfg.menu_timeout_ms)
    except Exception as e:
        print(f"  ! menu click failed: {item_text!r}: {e}")
        return False
    page.wait_for_timeout(cfg.menu_click_settle_ms)
    return True


def fill_field(page: Page, target: str, value: str, *, config: RecorderConfig | None = None) -> bool:
    """Glide to an input, click to focus, clear, then type character-by-character.

    Uses ``Locator.click()`` + ``Locator.fill("")`` + ``Locator.type(...)`` —
    typing fires real ``input`` events (reactive form widgets that gate
    buttons on debounced input depend on this; a raw ``element.value =``
    setter wouldn't trigger them).
    """
    cfg = config or RecorderConfig()
    rt = _glide_to(page, target, config=cfg, dwell_ms=cfg.pre_fill_dwell_ms)
    if rt is None:
        print(f"  ! fill target not found: {target!r}")
        return False
    try:
        rt.locator.click(timeout=cfg.interaction_timeout_ms)
        rt.locator.fill("")
        rt.locator.type(value, delay=cfg.typing_delay_ms)
    except Exception as e:
        print(f"  ! fill failed: {target!r}: {e}")
        return False
    page.wait_for_timeout(cfg.post_fill_settle_ms)
    return True


def select_option(page: Page, target: str, value: str, *, config: RecorderConfig | None = None) -> bool:
    """Pick an option from a native ``<select>``.

    Native HTML selects can't be reliably opened by clicking — across
    platforms, the dropdown rendering is OS-controlled. ``Locator.select_option``
    is the canonical way: it fires the right ``change`` events without
    needing the visual open. The cursor still glides onto the select so the
    viewer sees which control is changing; the closed widget flips to the
    new value.

    ``value`` is interpreted as the option's ``value`` attribute first, then
    a digit-only string as the 0-based ``index``, then the visible text
    ``label``. Returns False if none match.
    """
    cfg = config or RecorderConfig()
    rt = _glide_to(page, target, config=cfg, dwell_ms=cfg.pre_select_dwell_ms)
    if rt is None:
        print(f"  ! select target not found: {target!r}")
        return False
    # Render a synthetic dropdown so the VIEWER sees the options + which one is
    # picked. Native OS select popups can't be screen-recorded, so without this
    # the closed widget just silently flips value (the user can't tell a choice
    # was made). The cursor then glides down onto the chosen option.
    reveal_open = _reveal_select(page, rt, value, cfg)
    val = str(value)
    attempts: list[dict] = [{"value": val}]
    if val.lstrip("-").isdigit():
        attempts.append({"index": int(val)})
    attempts.append({"label": val})
    ok = False
    # ``.first`` keeps a multi-match target (e.g. one selector matching several
    # rows' <select>s) from throwing strict-mode — commit to the first match,
    # the same one the cursor glided to.
    sel_loc = rt.locator.first
    for attempt in attempts:
        try:
            sel_loc.select_option(**attempt, timeout=cfg.interaction_timeout_ms)
            ok = True
            break
        except Exception:
            continue
    if reveal_open:
        _close_select(page)
    if ok:
        page.wait_for_timeout(cfg.post_select_settle_ms)
        return True
    print(f"  ! select_option failed: {target!r} value={value!r}")
    return False


# Synthetic dropdown: build a styled options list over a native <select>, glide
# the cursor onto the chosen option, hold, then let the caller commit + close.
_SELECT_REVEAL_JS = r"""
(sel, value) => {
  try {
    if (!sel || sel.tagName !== 'SELECT') return null;
    const r = sel.getBoundingClientRect();
    const opts = Array.from(sel.options).map((o) => ({ value: o.value, text: (o.textContent || '').trim() }));
    if (!opts.length) return null;
    let ci = opts.findIndex((o) => o.value === String(value));
    if (ci < 0 && /^-?\d+$/.test(String(value))) ci = parseInt(value, 10);
    if (ci < 0) ci = opts.findIndex((o) => o.text === String(value));
    if (ci < 0) ci = sel.selectedIndex < 0 ? 0 : sel.selectedIndex;
    const W = Math.max(r.width, 180);
    const wrap = document.createElement('div');
    wrap.setAttribute('data-wt-select', '1');
    wrap.style.cssText = 'position:fixed;left:' + Math.round(r.left) + 'px;top:' + Math.round(r.bottom + 4)
      + 'px;width:' + Math.round(W) + 'px;z-index:2147483646;background:#fff;border:1px solid #d1d5db;'
      + 'border-radius:8px;box-shadow:0 12px 28px rgba(0,0,0,.20);overflow:hidden;'
      + "font:13px -apple-system,'Segoe UI',Roboto,sans-serif;color:#111827";
    opts.forEach((o, i) => {
      const on = i === ci;
      const row = document.createElement('div');
      row.style.cssText = 'padding:8px 12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'
        + (i ? 'border-top:1px solid #f3f4f6;' : '') + (on ? 'background:#eff6ff;color:#1d4ed8;font-weight:600;' : '');
      row.textContent = (on ? '✓ ' : '   ') + o.text;
      wrap.appendChild(row);
    });
    document.body.appendChild(wrap);
    const rows = wrap.children;
    let mid = { x: Math.round(r.left + W / 2), y: Math.round(r.bottom + 18) };
    if (rows[ci]) {
      const rr = rows[ci].getBoundingClientRect();
      mid = { x: Math.round(rr.left + Math.min(rr.width / 2, 90)), y: Math.round(rr.top + rr.height / 2) };
    }
    return mid;
  } catch (e) { return null; }
}
"""


def _reveal_select(page: Page, rt, value, cfg: RecorderConfig) -> bool:
    """Open a synthetic dropdown over the native ``<select>`` and glide the
    cursor onto the chosen option. Returns True if the overlay was shown (so
    the caller knows to close it after committing). Best-effort — never blocks
    the actual selection."""
    if not getattr(cfg, "select_reveal", True):
        return False
    try:
        mid = rt.locator.first.evaluate(_SELECT_REVEAL_JS, str(value))
    except Exception:
        return False
    if not mid:
        return False
    try:
        slow_move(page, float(mid["x"]), float(mid["y"]), steps=cfg.cursor_steps)
        page.wait_for_timeout(int(getattr(cfg, "select_reveal_dwell_ms", 700)))
    except Exception:
        pass
    return True


def _close_select(page: Page) -> None:
    try:
        page.evaluate("() => document.querySelectorAll('[data-wt-select]').forEach((e) => e.remove())")
    except Exception:
        pass


def hover(page: Page, target: str, *, seconds: float | None = None, config: RecorderConfig | None = None) -> bool:
    """Glide the cursor onto ``target`` and rest. No click.

    Uses ``Locator.hover()`` to fire real ``mouseenter`` / ``mouseover``
    events — tooltips and hover-revealed controls depend on those. The
    cursor glide is purely visual; the hover semantics come from Playwright.
    """
    cfg = config or RecorderConfig()
    dwell_ms = int(seconds * 1000) if seconds is not None else cfg.glide_dwell_ms
    rt = _glide_to(page, target, config=cfg, dwell_ms=dwell_ms)
    if rt is None:
        return False
    try:
        rt.locator.hover(timeout=cfg.interaction_timeout_ms)
    except Exception:
        # Tooltip-only hovers are not always actionable in Playwright's strict
        # sense; the cursor already landed on the spot, so don't fail loud.
        pass
    return True


def scroll_to(page: Page, target: str, *, config: RecorderConfig | None = None) -> bool:
    """Smooth-scroll the element matching ``target`` into view, with the cursor.

    Resolves via the unified locator engine (same syntax as every other
    primitive). For the actual scroll: ``Locator.scroll_into_view_if_needed``
    guarantees the element ends up visible (handles nested scroll containers,
    fixed headers, sticky elements — all the cases a window-level
    ``scrollTo`` misses). We chase it with a brief in-page smooth-scroll
    nudge so the motion is visible in the recording — the locator's
    instant scroll alone reads as a teleport.

    The cursor glides onto the target BEFORE the scroll, mirroring the
    click_text / fill_field pattern (resolve → glide → act). When the
    target is already in view (the "no-op scroll" case — common because
    spec authors ``scroll_to`` defensively), the page may not move at all
    but the cursor still visibly arrives on what's about to be clicked,
    so the viewer never sees a frozen ``scroll_settle_ms`` of nothing.
    After the smooth-scroll, we re-measure the locator (its viewport
    position changed) and glide the cursor again with ``cursor_steps_short``
    so it follows the element to its new spot — the same re-measure pattern
    ``click_text`` uses to land on a settled element.
    """
    cfg = config or RecorderConfig()
    rt = resolve_target(page, target, timeout_ms=cfg.glide_timeout_ms)
    if rt is None:
        return False
    # Pre-scroll glide — cursor lands on the target at its current viewport
    # position. Same shape every other primitive uses; keeps "boring" frames
    # from accumulating when ``scroll_to`` is a no-op.
    slow_move(page, rt.box["x"], rt.box["y"], steps=cfg.cursor_steps)
    try:
        rt.locator.scroll_into_view_if_needed(timeout=cfg.glide_timeout_ms)
    except Exception:
        # If actionability strictness blocks the scroll, the smooth-scroll
        # nudge below still tries; coordinate-based scroll is harmless.
        pass
    # Re-measure AFTER scroll_into_view_if_needed. That call may have scrolled
    # the page, changing the element's viewport-relative y. The smooth nudge
    # below combines this y with the *live* window.scrollY, so both must be read
    # at the same scroll position — pairing the pre-scroll rt.box.y with the
    # post-scroll window.scrollY computed a wrong target and left the element
    # off-screen on tall pages (e.g. a back-check far below the fold).
    scrolled_box = measure_box(rt.locator) or rt.box
    page.evaluate(
        """([x, y]) => window.scrollTo({top: y + window.scrollY - window.innerHeight / 2, behavior: 'smooth'})""",
        [scrolled_box["x"], scrolled_box["y"]],
    )
    # The smooth-scroll moved the element under our cursor. Re-measure +
    # short glide so the cursor follows it to its new viewport position —
    # this is the analogue of click_text's re-measure-then-click, applied
    # to "cursor must end on the scrolled-to element".
    new_box = measure_box(rt.locator)
    if new_box is not None:
        slow_move(page, new_box["x"], new_box["y"], steps=cfg.cursor_steps_short)
    page.wait_for_timeout(cfg.scroll_settle_ms)
    return True


def draw_polygon(
    page: Page,
    target: str,
    points: list,
    *,
    tool: str | None = None,
    config: RecorderConfig | None = None,
) -> bool:
    """Draw a polygon on a map/canvas by clicking a sequence of fractional points.

    The other primitives resolve a DOM element and click its centre. Map drawing
    (Mapbox GL Draw, or any canvas tool) needs clicks at *coordinates on the canvas*,
    which no labelled-element verb can express — this is the gap ``draw`` fills.

    ``target`` resolves to the map/canvas element; ``points`` is a list of
    ``[fx, fy]`` fractions (0-1) within that element's bounding box. The synthetic
    cursor glides to each vertex and clicks (real Playwright pointer events the
    drawing tool receives, unlike JS-synthetic events), then double-clicks the last
    vertex to close the polygon (Mapbox finishes a polygon on a double-click). The
    drawing tool must already be active — click its toolbar button in a prior
    ``click`` action.

    Returns False if the element doesn't resolve, has no box, or ``points`` is empty.
    """
    cfg = config or RecorderConfig()
    # Activate the drawing tool first if asked. A normal Locator.click on a small map
    # control (e.g. Mapbox's polygon button) fails Playwright's actionability checks;
    # a coordinate mouse-click on its centre activates it reliably.
    if tool:
        trt = resolve_target(page, tool, timeout_ms=cfg.glide_timeout_ms)
        if trt is not None:
            tbox = trt.locator.bounding_box()
            if tbox:
                # Glide the visible cursor onto the tool so the video shows the reach...
                slow_move(page, tbox["x"] + tbox["width"] / 2, tbox["y"] + tbox["height"] / 2, steps=cfg.cursor_steps)
                page.wait_for_timeout(cfg.glide_dwell_ms)
            # ...but TOGGLE via the element's own click() handler. Mapbox-GL-Draw tool
            # buttons don't enter draw mode on a synthetic mouse/Locator click (the
            # mode stays simple_select); el.click() fires the handler that does.
            try:
                trt.locator.evaluate("el => el.click()")
            except Exception:
                pass
            page.wait_for_timeout(cfg.glide_dwell_ms)
    rt = resolve_target(page, target, timeout_ms=cfg.glide_timeout_ms)
    if rt is None:
        return False
    box = rt.locator.bounding_box()
    if not box or not points:
        return False
    coords = [
        (box["x"] + float(fx) * box["width"], box["y"] + float(fy) * box["height"])
        for fx, fy in points
    ]
    for x, y in coords:
        slow_move(page, x, y, steps=cfg.cursor_steps)
        page.wait_for_timeout(cfg.glide_dwell_ms)
        page.mouse.click(x, y)
    # Close the polygon — Mapbox GL Draw finishes on a double-click at the last vertex.
    page.mouse.dblclick(*coords[-1])
    page.wait_for_timeout(cfg.glide_dwell_ms)
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


def wait_for(
    page: Page,
    target: str,
    *,
    seconds: float | None = None,
    config: RecorderConfig | None = None,
) -> bool:
    """Wait for ``target`` (text or selector) to appear, or pause for N ms if ``target`` is all digits.

    Plain-text targets skip the selector engine entirely — see
    :func:`._lib.targets.wait_for_target` for the rationale.

    ``seconds`` is a per-call timeout override (the spec's
    ``{kind: wait_for, target: X, seconds: 120}``). It's converted to
    milliseconds and forwarded as ``timeout_ms`` to
    :func:`._lib.targets.wait_for_target`. ``None`` falls back to
    ``RecorderConfig.wait_for_timeout_ms`` — back-compat with every call
    site that doesn't pass it. Negative values are floored at 0 (the
    underlying Playwright ``wait_for`` would raise on negatives; we
    rather treat "negative timeout" as "don't wait").
    """
    cfg = config or RecorderConfig()
    if seconds is not None:
        timeout_ms = max(0, int(float(seconds) * 1000))
    else:
        timeout_ms = cfg.wait_for_timeout_ms
    return wait_for_target(page, target, timeout_ms=timeout_ms)


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
            ok = wait_for(
                page, str(target or value or "1000"), seconds=seconds, config=cfg
            )
            if not ok:
                error_kind = "timeout"
        elif kind == "hold":
            page.wait_for_timeout(int(float(seconds or value or 1.0) * 1000))
        elif kind == "draw":
            ok = draw_polygon(
                page, target or "", action.get("points") or [], tool=action.get("tool"), config=cfg
            )
            if not ok:
                error_kind = "target_not_found"
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
        must_succeed=must_succeed,
    )
    if not ok and must_succeed:
        raise ActionAssertError(f"required action failed: {label}: {error_message or error_kind}")
    return result
