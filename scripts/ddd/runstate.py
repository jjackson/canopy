"""DDD run-state lifecycle helpers (SP0.4).

Public API
----------
new_run(narrative_slug: str) -> str
    Creates a new run directory + run_state.yaml, returns the run_id.

load(run_id: str) -> RunState
    Loads and returns a RunState from disk.

save(state: RunState) -> None
    Persists a RunState back to disk (overwrites run_state.yaml).

append_learning(text: str) -> None
    Appends a learning entry to <ddd_dir>/learnings.md.

The DDD directory is resolved by _resolve_ddd_dir():
  - Inside a git repo: <repo-root>/.canopy/ddd/
  - Outside a git repo: $HOME/.canopy/ddd/<cwd-basename>/
"""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

import yaml

from scripts.ddd.schemas.models import RunState


# ---------------------------------------------------------------------------
# Dir resolver (shells out to git; keep in sync with resolve_ddd_dir.sh)
# ---------------------------------------------------------------------------


def _resolve_ddd_dir() -> Path:
    """Return (and create) the canonical DDD state directory.

    Logic mirrors resolve_ddd_dir.sh — keep the two in sync when changing
    the fallback path or git invocation.
    """
    try:
        repo_root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        ddd_dir = Path(repo_root) / ".canopy" / "ddd"
    except (subprocess.CalledProcessError, FileNotFoundError):
        # CalledProcessError: git ran but we're not in a repo
        # FileNotFoundError: git is not installed / not on PATH
        import os
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


def new_run(narrative_slug: str) -> str:
    """Create a new run under <ddd_dir>/runs/ and return the run_id."""
    ddd_dir = _resolve_ddd_dir()
    runs_dir = ddd_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    run_id = _next_run_id(runs_dir, narrative_slug)
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    state = RunState(run_id=run_id, narrative_slug=narrative_slug)
    _write_state(run_dir, state)

    return run_id


def load(run_id: str) -> RunState:
    """Load a RunState from <ddd_dir>/runs/<run_id>/run_state.yaml."""
    ddd_dir = _resolve_ddd_dir()
    state_file = ddd_dir / "runs" / run_id / "run_state.yaml"
    raw = yaml.safe_load(state_file.read_text())
    return RunState.model_validate(raw)


def save(state: RunState) -> None:
    """Persist *state* to <ddd_dir>/runs/<run_id>/run_state.yaml."""
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
