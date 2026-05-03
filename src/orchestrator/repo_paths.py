"""Resolve a repo short name (or already-absolute path) to its local checkout.

This machine has multiple emdash root conventions in active use across logins
— `~/emdash/repositories/` for one user, `~/emdash-projects/` for another —
and proposals were getting written with one hardcoded path that didn't exist
on the consumer's machine. Verify-findings then had to fall back manually.

The fix: don't hardcode. Proposals carry the short name; consumers
(verify-findings, implementer agents) call ``resolve_repo_path("ace")`` and
get back the actual path on this machine. Backwards-compat: an existing
``target_repo: ~/emdash-projects/ace`` still works — if it exists, we use it;
if it doesn't, we extract "ace" and re-resolve.
"""
from __future__ import annotations

import os
from pathlib import Path

# Candidate root directories where local checkouts of the user's repos live.
# Order matters — the first match wins. Add entries here when a new
# convention shows up; do NOT hardcode any single root in callers.
DEFAULT_ROOTS = (
    "~/emdash/repositories",
    "~/emdash-projects",
    "~/code",
    "~/dev",
    "~/repos",
    "~/src",
)


def _expand(p: str | os.PathLike) -> Path:
    return Path(os.path.expanduser(str(p)))


def resolve_repo_path(
    target: str,
    roots: tuple[str, ...] = DEFAULT_ROOTS,
) -> Path | None:
    """Resolve `target` to an absolute repo path on this machine.

    `target` accepts either:

    - A short repo name (e.g. ``"ace"``, ``"ace-web"``, ``"canopy"``). We
      search each entry in ``roots`` for ``<root>/<short>`` and return the
      first that contains a ``.git`` (file or directory — git worktrees
      have ``.git`` as a file).
    - An already-absolute or ``~``-relative path (anything containing
      ``/``). We expand ``~`` and return as-is if the path exists; if not,
      we extract the basename (the repo short name) and fall back to the
      short-name search. This keeps backwards compatibility with proposals
      that have a hardcoded ``target_repo: ~/emdash-projects/<repo>`` —
      the path may not exist on this user's machine, but the short name
      will resolve correctly.

    Returns ``None`` when no candidate matches. Callers should treat
    ``None`` as "this repo isn't checked out on this machine; skip
    verification rather than guessing."
    """
    if not target or not isinstance(target, str):
        return None

    target = target.strip()
    if not target:
        return None

    # Path-like: expand and use if it exists. Otherwise extract the short
    # name from the basename and continue to the short-name path below.
    short: str
    if "/" in target:
        path = _expand(target)
        if path.exists() and (path / ".git").exists():
            return path
        short = path.name
    else:
        short = target

    if not short:
        return None

    # Short-name search: first <root>/<short> with a .git wins.
    for root in roots:
        candidate = _expand(root) / short
        if candidate.exists() and (candidate / ".git").exists():
            return candidate

    return None


def list_known_roots(roots: tuple[str, ...] = DEFAULT_ROOTS) -> list[Path]:
    """Return the subset of `roots` that currently exist on this machine.

    Useful for diagnostics / `canopy doctor` output: shows which conventions
    are active so the user knows where new repos will be discovered.
    """
    return [_expand(r) for r in roots if _expand(r).exists()]
