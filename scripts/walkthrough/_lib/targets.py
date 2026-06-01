"""Target resolution for the walkthrough recorder.

Every recorder primitive (click, fill, select, scroll_to, wait_for, …) needs to
turn the spec author's free-form ``target`` string into something concrete: a
Playwright ``Locator`` for ``locator.click()`` / ``locator.fill()`` / etc., OR a
viewport-centre coordinate so the synthetic cursor can glide to it.

Before this module each primitive grew its own resolver — its own selector
ladder, its own text-fallback rules, its own selector-vs-text heuristic. Adding
a new verb meant writing a fifth resolver. Worse, the heuristics disagreed:
``wait_for`` ran ``page.wait_for_selector`` on a plain-text target and stacked a
12-second hang per call before the text-match fallback fired (see the
``microplans-10-wards`` recording, 248 s → 193 s once this consolidation landed).

One public entry point:

    resolve_target(page, target, *, timeout_ms) -> ResolvedTarget | None

Returns:
- ``locator``: a Playwright ``Locator`` when the target unambiguously resolves
  via the selector engine (CSS, testid, aria-label, role). ``None`` when the
  target matched via visible-text ranking instead. Primitives that need to
  call a Playwright API (``locator.fill``, ``locator.select_option``) get one
  for free; primitives that only need to click at coordinates ignore it.
- ``box``: ``{x, y}`` viewport-centre of the resolved element, always set —
  this is what the cursor glides to.
- ``kind``: which path resolved the target. Useful for telemetry (the report
  layer wants to know whether a click landed via CSS or text-ranking).

Target syntax (the value of ``Action.target`` / etc.):

    "css:#cfg-strategy"             explicit CSS selector
    "testid:plan-picker-checkbox"   shorthand for [data-testid="..."]
    "aria:Resolved wards"           shorthand for [aria-label*="..."]
    "role:option"                   shorthand for [role="..."]
    "text:Resolved wards"           force the visible-text path (skips heuristic)
    "Resolved wards"                bare — heuristic picks (defaults to text here)
    "#cfg-strategy"                 bare — heuristic picks (defaults to CSS here)

The heuristic only kicks in for bare targets. Explicit prefixes are always
honoured — useful when text happens to start with ``#`` or a CSS selector
happens to be a single English word.
"""

from __future__ import annotations

import time
from typing import NamedTuple

from playwright.sync_api import Locator, Page

# Recognised prefixes, in priority order. Order matters only for documentation —
# at parse time we look for an exact prefix match.
_PREFIXES = ("css", "text", "testid", "aria", "role")
_PREFIX_SEPARATOR = ":"


class ResolvedTarget(NamedTuple):
    """The output of ``resolve_target`` — what the caller actually uses."""

    locator: Locator | None
    box: dict
    kind: str  # "css" | "testid" | "aria" | "role" | "text"


def parse_target(target: str) -> tuple[str, str]:
    """Split an optional ``kind:`` prefix off ``target``.

    Returns ``(kind, value)`` where ``kind`` is one of the prefixes from
    :data:`_PREFIXES`, or ``"auto"`` if no prefix was given. A bare target is
    returned as ``("auto", target)`` so callers can route to the heuristic.
    """
    if not target:
        return "auto", ""
    for p in _PREFIXES:
        head = p + _PREFIX_SEPARATOR
        if target.startswith(head):
            return p, target[len(head):]
    return "auto", target


def looks_like_selector(s: str) -> bool:
    """Heuristic: is ``s`` a CSS selector or visible text?

    Returns True for strings whose first non-space char is a structural
    selector character (``# . [ : > ~ +``) or that contain selector-only
    punctuation alongside an identifier-looking lead. Returns False for
    plain English text.

    Used for two things: (1) routing the ``"auto"`` branch in ``resolve_target``
    when there's no explicit prefix, and (2) deciding whether ``wait_for`` can
    skip ``page.wait_for_selector`` (which would otherwise sit through its
    full timeout on a plain-text target before falling back).
    """
    s = (s or "").strip()
    if not s:
        return False
    if s[0] in "#.[:>~+":
        return True
    if s[0].isalpha() and any(c in s for c in ">[.#:"):
        return True
    return False


def to_css_selector(kind: str, value: str) -> str | None:
    """If ``kind`` unambiguously maps to a CSS selector, return it. Else ``None``.

    Used by callers that need a single string to hand to Playwright's selector
    engine. ``"auto"`` defers to the heuristic — returns the bare value when
    it looks selector-shaped, otherwise ``None`` (signaling fall back to the
    visible-text path).
    """
    if kind == "css":
        return value
    if kind == "testid":
        return f'[data-testid="{value}"]'
    if kind == "aria":
        return f'[aria-label*="{value}"]'
    if kind == "role":
        return f'[role="{value}"]'
    if kind == "auto" and looks_like_selector(value):
        return value
    return None


# JS that finds + scrolls + measures an element by ranked visible-text match.
# Kept here (not on each primitive) so the ranking — actionable controls first,
# exact text over substring, smallest match over wrapping containers — is the
# same wherever a recorder primitive needs to glide to a text label.
_FIND_BY_TEXT_JS = """(t) => {
    const txt = e => (e.innerText || e.textContent || '').trim();
    const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
    const area = e => { const r = e.getBoundingClientRect(); return r.width * r.height; };
    const ACT = 'button, a, [role=button], [role=option], [role=menuitem], summary, li, td';
    const TXT = 'label, span, div, th, h1, h2, h3, p';
    const pools = [
        [...document.querySelectorAll(ACT)].filter(e => vis(e) && txt(e) === t),
        [...document.querySelectorAll(ACT)].filter(e => vis(e) && txt(e).includes(t)),
        [...document.querySelectorAll(TXT)].filter(e => vis(e) && txt(e) === t),
        [...document.querySelectorAll(TXT)].filter(e => vis(e) && txt(e).includes(t)),
    ];
    let el = null;
    for (const pool of pools) {
        if (pool.length) { pool.sort((a, b) => area(a) - area(b)); el = pool[0]; break; }
    }
    if (!el) return null;
    el.scrollIntoView({behavior: 'instant', block: 'center'});
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return null;
    return {x: r.x + r.width / 2, y: r.y + r.height / 2};
}"""


def _measure_locator(loc: Locator) -> dict | None:
    """Return ``{x, y}`` viewport-centre of a Playwright ``Locator``, or ``None``."""
    box = loc.bounding_box()
    if not box:
        return None
    return {"x": box["x"] + box["width"] / 2, "y": box["y"] + box["height"] / 2}


def _resolve_via_css(page: Page, selector: str, *, timeout_ms: int) -> Locator | None:
    """Wait for ``selector`` to become visible, return its first locator or ``None``."""
    try:
        loc = page.locator(selector).first
        loc.wait_for(state="visible", timeout=timeout_ms)
        return loc
    except Exception:
        return None


def _resolve_via_text(page: Page, value: str, *, timeout_ms: int, poll_ms: int = 150) -> dict | None:
    """Poll the page until visible-text ranking finds an element, return its box."""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        try:
            box = page.evaluate(_FIND_BY_TEXT_JS, value)
        except Exception:
            box = None
        if box:
            return box
        page.wait_for_timeout(poll_ms)
    return None


def resolve_target(page: Page, target: str, *, timeout_ms: int = 6000) -> ResolvedTarget | None:
    """Resolve a ``target`` string to a Playwright ``Locator`` + a cursor coordinate.

    Routing:
      - Explicit ``css:|testid:|aria:|role:`` — selector engine only. No text fallback.
      - Explicit ``text:`` — visible-text ranking only. Skips selector engine.
      - Bare target — heuristic: selector engine first if it looks selector-shaped,
        otherwise visible-text ranking. Falls through to the other path on miss.

    Returns ``None`` if neither path resolved within ``timeout_ms``.
    """
    if not target:
        return None
    kind, value = parse_target(target)

    css = to_css_selector(kind, value)
    if css is not None:
        loc = _resolve_via_css(page, css, timeout_ms=timeout_ms)
        if loc is not None:
            box = _measure_locator(loc)
            if box is not None:
                return ResolvedTarget(locator=loc, box=box, kind=kind if kind != "auto" else "css")
        # Explicit selector kinds (css/testid/aria/role) MUST resolve via the
        # selector engine — no text-ranking fallback. The "auto" path keeps
        # going so a heuristic miss can still land on visible text.
        if kind != "auto":
            return None

    if kind == "css":  # explicit css that didn't resolve — caller wanted exactly that
        return None

    box = _resolve_via_text(page, value, timeout_ms=timeout_ms)
    if box is not None:
        return ResolvedTarget(locator=None, box=box, kind="text")
    return None


def wait_for_target(page: Page, target: str, *, timeout_ms: int = 12000) -> bool:
    """Wait for ``target`` to be present.

    Selector targets are awaited via ``page.wait_for_selector`` (the selector
    engine is faster and supports complex selectors). Text targets are awaited
    via ``page.wait_for_function`` against ``document.body.innerText``.

    The split matters: ``wait_for_selector`` on a plain-text target would sit
    through its full timeout before Playwright gave up and raised, stacking
    a per-call hang in front of every fallback. See :func:`looks_like_selector`.
    """
    if not target:
        return False
    if target.isdigit():
        page.wait_for_timeout(int(target))
        return True
    kind, value = parse_target(target)
    css = to_css_selector(kind, value)
    if css is not None:
        try:
            page.wait_for_selector(css, timeout=timeout_ms)
            return True
        except Exception:
            if kind != "auto":
                return False
            # Auto-heuristic was wrong — fall through to text match.
    try:
        page.wait_for_function(
            "(t) => document.body && document.body.innerText.includes(t)",
            arg=value,
            timeout=timeout_ms,
        )
        return True
    except Exception:
        return False
