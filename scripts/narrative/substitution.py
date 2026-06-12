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


def substitute_scenes(scenes: list[dict], variables: dict[str, Any]) -> list[dict]:
    """Return a deep-substituted copy of *scenes*; the input is not mutated.

    Resolves ``${var}`` in each scene's ``url`` and each action's ``target`` /
    ``value`` from *variables*. Raises :class:`UnresolvedPlaceholderError`
    listing every missing variable (and the available keys) if any placeholder
    has no value — a hard error by design, so a stale/missing outputs file
    fails the render loudly instead of filming a literal ``${run_id}`` URL.
    """
    missing = scenes_placeholders(scenes) - set(variables)
    if missing:
        available = ", ".join(sorted(variables)) or "(none)"
        raise UnresolvedPlaceholderError(
            f"unresolved ${{...}} placeholder(s) in spec scenes: "
            f"{', '.join(sorted(missing))} — available variables: {available}. "
            "Check the setup command's outputs JSON declares every variable the "
            "spec references (and that setup.outputs points at the right file)."
        )

    substituted: list[dict] = []
    for scene in scenes:
        new_scene = dict(scene)
        if isinstance(new_scene.get("url"), str):
            new_scene["url"] = _substitute_text(new_scene["url"], variables)
        new_actions: list[Any] = []
        for action in new_scene.get("actions") or []:
            if isinstance(action, dict):
                new_action = dict(action)
                for key in ("target", "value"):
                    if isinstance(new_action.get(key), str):
                        new_action[key] = _substitute_text(new_action[key], variables)
                new_actions.append(new_action)
            else:
                new_actions.append(action)
        if new_scene.get("actions") is not None:
            new_scene["actions"] = new_actions
        substituted.append(new_scene)
    return substituted
