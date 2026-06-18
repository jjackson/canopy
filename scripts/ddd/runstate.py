"""DDD run-state lifecycle helpers (SP0.4).

Public API
----------
new_run(narrative_slug: str, ddd_dir: Path | None = None) -> str
    Creates a new run directory + run_state.yaml, returns the run_id.

load(run_id: str, ddd_dir: Path | None = None) -> RunState
    Loads and returns a RunState from disk.

save(state: RunState, ddd_dir: Path | None = None) -> None
    Persists a RunState back to disk (overwrites run_state.yaml).

When ``ddd_dir`` is passed it is used directly, bypassing _resolve_ddd_dir().

append_learning(text: str) -> None
    Appends a learning entry to <ddd_dir>/learnings.md.

The DDD directory is resolved by _resolve_ddd_dir() in this precedence order:
  1. explicit ``ddd_dir`` arg on load/save/new_run — used directly, no resolution
  2. ``repo_root`` arg to _resolve_ddd_dir → <repo_root>/.canopy/ddd/
  3. ``DDD_DIR`` env var → used directly
  4. git toplevel of cwd → <repo-root>/.canopy/ddd/
  5. fallback (git absent / not a repo) → $HOME/.canopy/ddd/<cwd-basename>/
"""

from __future__ import annotations

import os
import subprocess
from datetime import date
from pathlib import Path

import yaml

from scripts.ddd.schemas.models import RunState


# ---------------------------------------------------------------------------
# Dir resolver (shells out to git; keep in sync with resolve_ddd_dir.sh)
# ---------------------------------------------------------------------------


def _resolve_ddd_dir(repo_root: Path | None = None) -> Path:
    """Return (and create) the canonical DDD state directory.

    Resolution order (highest precedence first):
      1. ``repo_root`` arg → ``<repo_root>/.canopy/ddd`` (decouples from cwd; the
         caller already knows the repo root, so don't shell out to git).
      2. ``DDD_DIR`` env var → used directly (an explicit operator override).
      3. git toplevel of cwd → ``<repo-root>/.canopy/ddd``.
      4. fallback (git absent / not a repo) → ``$HOME/.canopy/ddd/<cwd-basename>``.

    The cwd-based branches (3/4) mirror resolve_ddd_dir.sh — keep the two in
    sync when changing the fallback path or git invocation.
    """
    if repo_root is not None:
        ddd_dir = Path(repo_root) / ".canopy" / "ddd"
        ddd_dir.mkdir(parents=True, exist_ok=True)
        return ddd_dir

    env_dir = os.environ.get("DDD_DIR", "").strip()
    if env_dir:
        ddd_dir = Path(env_dir)
        ddd_dir.mkdir(parents=True, exist_ok=True)
        return ddd_dir

    try:
        toplevel = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        ddd_dir = Path(toplevel) / ".canopy" / "ddd"
    except (subprocess.CalledProcessError, FileNotFoundError):
        # CalledProcessError: git ran but we're not in a repo
        # FileNotFoundError: git is not installed / not on PATH
        cwd_name = Path(os.getcwd()).name
        ddd_dir = Path.home() / ".canopy" / "ddd" / cwd_name

    ddd_dir.mkdir(parents=True, exist_ok=True)
    return ddd_dir


# ---------------------------------------------------------------------------
# Run-ID generation
# ---------------------------------------------------------------------------


def _next_run_id(runs_dir: Path, narrative_slug: str) -> str:
    """Return the next available run_id of the form <narrative_slug>-<YYYY-MM-DD>-NNN."""
    today = date.today().strftime("%Y-%m-%d")
    prefix = f"{narrative_slug}-{today}-"

    existing = [d.name for d in runs_dir.iterdir() if d.is_dir() and d.name.startswith(prefix)]
    nums = []
    for name in existing:
        suffix = name[len(prefix):]
        if suffix.isdigit():
            nums.append(int(suffix))

    next_num = (max(nums) + 1) if nums else 1
    return f"{prefix}{next_num:03d}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def new_run(narrative_slug: str, ddd_dir: Path | None = None) -> str:
    """Create a new run under <ddd_dir>/runs/ and return the run_id.

    If *ddd_dir* is given it is used directly (no cwd/git resolution).
    """
    if ddd_dir is None:
        ddd_dir = _resolve_ddd_dir()
    runs_dir = ddd_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    run_id = _next_run_id(runs_dir, narrative_slug)
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    state = RunState(run_id=run_id, narrative_slug=narrative_slug)
    _write_state(run_dir, state)

    return run_id


def load(run_id: str, ddd_dir: Path | None = None) -> RunState:
    """Load a RunState from <ddd_dir>/runs/<run_id>/run_state.yaml.

    If *ddd_dir* is given it is used directly (no cwd/git resolution).
    """
    if ddd_dir is None:
        ddd_dir = _resolve_ddd_dir()
    state_file = ddd_dir / "runs" / run_id / "run_state.yaml"
    raw = yaml.safe_load(state_file.read_text())
    return RunState.model_validate(raw)


def save(state: RunState, ddd_dir: Path | None = None) -> None:
    """Persist *state* to <ddd_dir>/runs/<run_id>/run_state.yaml.

    If *ddd_dir* is given it is used directly (no cwd/git resolution).
    """
    if ddd_dir is None:
        ddd_dir = _resolve_ddd_dir()
    run_dir = ddd_dir / "runs" / state.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_state(run_dir, state)


def append_learning(text: str) -> None:
    """Append *text* as a new bullet to <ddd_dir>/learnings.md."""
    ddd_dir = _resolve_ddd_dir()
    learnings_file = ddd_dir / "learnings.md"

    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = f"- [{timestamp}] {text}\n"

    with learnings_file.open("a", encoding="utf-8") as fh:
        fh.write(entry)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _write_state(run_dir: Path, state: RunState) -> None:
    state_file = run_dir / "run_state.yaml"
    # Dump via model_dump to get Python-native types (no pydantic objects)
    data = state.model_dump()
    state_file.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True))
