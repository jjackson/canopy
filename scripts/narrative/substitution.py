"""``${var}`` placeholder substitution for walkthrough / DDD specs.

Specs whose demo data is minted by a setup command (``UnifiedSpec.setup`` —
the synthetic generator that seeds the world before recording) can't hardcode
entity IDs: the generator mints a fresh run/audit/task each time, so a
hardcoded ``run_id=3720`` silently goes stale on every reseed. Instead the
spec writes ``${run_id}`` in ``Scene.url`` and in action ``target`` / ``value``
fields, and the recorder resolves the placeholders at render time from the
setup command's outputs JSON — never mutating the spec file on disk.

This module is the single source of truth for what a placeholder *is*
(``PLACEHOLDER_RE``) and how scenes are scanned/substituted. Both the
recorder (``scripts/walkthrough/record_video.py``) and the structural QA gate
(``scripts/ddd/spec_qa.py``) import it, so the two can never disagree about
the syntax. Stdlib-only on purpose — the recorder runs in minimal portable
installs (pyyaml + playwright) that must not grow a pydantic import from here.

Substitution is deliberately narrow: ONLY ``Scene.url`` and each action's
``target`` and ``value`` are scanned/resolved. Narrative prose that happens to
contain ``${...}`` (e.g. a code snippet in ``show``) is left alone.

Two binding models share this syntax:

  - **Up-front** (``substitute_scenes``): all vars are known at setup time, so
    every ``${var}`` is resolved once before the render and a missing var is a
    hard error. The original path; still used for the pre-warm pass and any
    spec with no on-camera ``capture`` actions.
  - **Late / runtime** (``resolve_string`` + ``scene_capture_vars`` +
    ``ordered_placeholder_violations``): a ``capture`` action mints a ``${var}``
    DURING the render (reads an id off the live page), so a var may not exist
    until a later scene. ``resolve_string`` resolves what it CAN and leaves the
    rest intact (the recorder resolves a scene's url/target/value lazily, right
    before it executes, against the live ``vars`` dict). Validation becomes
    order-aware: a ``${var}`` is valid iff a setup output OR an earlier
    ``capture`` provides it.
"""

from __future__ import annotations

import re
from typing import Any

# ``${var_name}`` — Python-identifier variable names only. A ``${...}`` with a
# non-identifier body (e.g. shell arithmetic in a code-sample string) does not
# match, so it neither substitutes nor trips the unresolved-placeholder gate.
PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class UnresolvedPlaceholderError(ValueError):
    """A ``${...}`` placeholder could not be resolved.

    Raised BEFORE any recording starts — filming with an unresolved
    placeholder navigates to a literal ``/runs/${run_id}/`` URL and produces
    a confidently wrong video. The message lists every missing variable and
    the keys that *are* available, so the fix (rename the placeholder, or fix
    the setup command's outputs) is one read away.
    """


def find_placeholders(text: Any) -> set[str]:
    """Return the set of placeholder names in *text* (empty for non-strings)."""
    if not isinstance(text, str):
        return set()
    return set(PLACEHOLDER_RE.findall(text))


def _scene_strings(scene: dict) -> list[Any]:
    """The substitutable strings of one raw scene dict: url + action target/value."""
    out: list[Any] = [scene.get("url")]
    for action in scene.get("actions") or []:
        if isinstance(action, dict):
            out.append(action.get("target"))
            out.append(action.get("value"))
    return out


def scenes_placeholders(scenes: list[dict]) -> set[str]:
    """All placeholder names used across *scenes* (raw spec dicts).

    Scans exactly the fields substitution touches — ``Scene.url`` and every
    action's ``target`` / ``value`` — so "placeholders present" here means
    "substitution will be attempted".
    """
    names: set[str] = set()
    for scene in scenes:
        for text in _scene_strings(scene):
            names |= find_placeholders(text)
    return names


def _substitute_text(text: str, variables: dict[str, Any]) -> str:
    """Replace every ``${var}`` in *text* from *variables* (values coerced via str)."""
    return PLACEHOLDER_RE.sub(lambda m: str(variables[m.group(1)]), text)


def substitute_scenes(
    scenes: list[dict],
    variables: dict[str, Any],
    *,
    allow_unresolved: set[str] | None = None,
) -> list[dict]:
    """Return a deep-substituted copy of *scenes*; the input is not mutated.

    Resolves ``${var}`` in each scene's ``url`` and each action's ``target`` /
    ``value`` from *variables*. Raises :class:`UnresolvedPlaceholderError`
    listing every missing variable (and the available keys) if any placeholder
    has no value — a hard error by design, so a stale/missing outputs file
    fails the render loudly instead of filming a literal ``${run_id}`` URL.

    ``allow_unresolved`` is the set of variable names that are bound LATER (on
    camera, by a ``capture`` action) and so are PERMITTED to be absent here —
    they're left verbatim for the recorder to resolve at runtime, and don't
    trip the missing-var error. The up-front pass still substitutes every var
    it CAN (the setup-known ones), so pre-warm + early scenes work; only the
    genuinely-late vars survive.
    """
    allow = allow_unresolved or set()
    missing = scenes_placeholders(scenes) - set(variables) - allow
    if missing:
        available = ", ".join(sorted(variables)) or "(none)"
        raise UnresolvedPlaceholderError(
            f"unresolved ${{...}} placeholder(s) in spec scenes: "
            f"{', '.join(sorted(missing))} — available variables: {available}. "
            "Check the setup command's outputs JSON declares every variable the "
            "spec references (and that setup.outputs points at the right file)."
        )

    # Partial substitution: resolve the known vars, leave allow_unresolved (and
    # nothing else, since the missing-check above already passed) intact.
    substituted: list[dict] = []
    for scene in scenes:
        new_scene = dict(scene)
        if isinstance(new_scene.get("url"), str):
            new_scene["url"] = resolve_string(new_scene["url"], variables)
        new_actions: list[Any] = []
        for action in new_scene.get("actions") or []:
            if isinstance(action, dict):
                new_action = dict(action)
                for key in ("target", "value"):
                    if isinstance(new_action.get(key), str):
                        new_action[key] = resolve_string(new_action[key], variables)
                new_actions.append(new_action)
            else:
                new_actions.append(action)
        if new_scene.get("actions") is not None:
            new_scene["actions"] = new_actions
        substituted.append(new_scene)
    return substituted


# --------------------------------------------------------------------------- #
# Late binding — runtime resolution + order-aware validation
# --------------------------------------------------------------------------- #


def resolve_string(text: Any, variables: dict[str, Any]) -> Any:
    """Resolve the ``${var}`` in *text* that *variables* knows; leave the rest.

    Unlike :func:`_substitute_text` (which ``KeyError``s on an unknown var),
    this is the LATE-binding primitive: it substitutes every placeholder
    present in *variables* and leaves any unknown placeholder VERBATIM. The
    recorder calls it just before a scene/action executes — by which point an
    earlier ``capture`` action may have extended *variables* with the very key
    a later scene needs. A still-unresolved ``${var}`` at execution time is the
    recorder's signal that a capture didn't fire (it skips warming/visiting such
    a URL rather than navigating to a literal placeholder).

    Non-string input is returned unchanged (so a ``None`` url stays ``None``).
    """
    if not isinstance(text, str):
        return text
    return PLACEHOLDER_RE.sub(
        lambda m: str(variables[m.group(1)]) if m.group(1) in variables else m.group(0),
        text,
    )


def has_unresolved(text: Any) -> bool:
    """True if *text* still contains a ``${var}`` placeholder (post-resolve)."""
    return bool(find_placeholders(text))


def scene_capture_vars(scene: dict) -> list[str]:
    """The variable names a scene's ``capture`` actions BIND, in action order.

    A ``capture`` action declares its variable via ``var`` (not ``target`` /
    ``value``), so it doesn't show up in :func:`scenes_placeholders` (which
    scans the substitutable fields). This is the complementary scan: what a
    scene PRODUCES, so order-aware validation can mark those vars available to
    LATER scenes.
    """
    out: list[str] = []
    for action in scene.get("actions") or []:
        if not isinstance(action, dict):
            continue
        if (action.get("kind") or "") == "capture":
            var = action.get("var")
            if isinstance(var, str) and var:
                out.append(var)
    return out


def _action_strings(action: dict) -> list[Any]:
    """The substitutable strings of one action dict: target + value."""
    if not isinstance(action, dict):
        return []
    return [action.get("target"), action.get("value")]


def ordered_placeholder_violations(
    scenes: list[dict], setup_vars: set[str] | None = None
) -> list[str]:
    """Order-aware validation: every ``${var}`` must be available WHEN USED.

    Walks *scenes* in order, tracking the set of available variables — seeded
    from *setup_vars* (the setup command's declared outputs) and EXTENDED by
    each ``capture`` action as it's encountered. A ``${var}`` in a scene's
    ``url`` or an action's ``target`` / ``value`` is a violation iff no setup
    output and no EARLIER capture provides it.

    Within a scene the available set is extended as actions run, so a scene that
    captures ``${id}`` in action 1 may use ``${id}`` in action 3 — but NOT in
    its ``url`` (the url is resolved at scene start, before any of the scene's
    actions run). A capture's own ``var`` is available to actions AFTER it and
    to all later scenes, never to earlier ones.

    Returns a list of human-readable violation strings (empty ⇒ valid). The
    pure validator behind both ``spec_qa`` and the recorder's pre-flight, so the
    two can't disagree about what a fresh-lifecycle spec is allowed to do.
    """
    available: set[str] = set(setup_vars or set())
    violations: list[str] = []
    for i, scene in enumerate(scenes, 1):
        title = scene.get("title", f"scene {i}")
        # The scene's URL resolves at scene start — only setup outputs and
        # captures from EARLIER scenes are available; this scene's own captures
        # have not run yet.
        for var in sorted(find_placeholders(scene.get("url"))):
            if var not in available:
                violations.append(
                    f"scene '{title}': url references ${{{var}}} but nothing provides it yet "
                    "(not a setup output, and no earlier `capture` binds it)"
                )
        # Actions resolve in order; a capture extends the available set for the
        # actions that FOLLOW it within this same scene.
        for action in scene.get("actions") or []:
            if not isinstance(action, dict):
                continue
            for text in _action_strings(action):
                for var in sorted(find_placeholders(text)):
                    if var not in available:
                        kind = action.get("kind") or "?"
                        violations.append(
                            f"scene '{title}': {kind} action references ${{{var}}} but nothing "
                            "provides it yet (not a setup output, and no earlier `capture` binds it)"
                        )
            if (action.get("kind") or "") == "capture":
                var = action.get("var")
                if isinstance(var, str) and var:
                    available.add(var)
    return violations
