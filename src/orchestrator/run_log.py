"""Write and read improvement cycle run logs."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def create_run_entry() -> dict[str, Any]:
    """Create a new run log entry."""
    return {
        "started": datetime.now(timezone.utc).isoformat(),
        "completed": None,
        "transcripts_analyzed": 0,
        "observations_created": 0,
        "observations_merged": 0,
        "proposals_generated": 0,
        "proposals_implemented": 0,
        "proposals_failed": 0,
        "processed_sessions": [],
        "errors": [],
    }


def save_run(run: dict, runs_dir: Path) -> Path:
    """Save a run entry to a YAML file."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    ts = run["started"].replace(":", "-").replace("+", "p")
    path = runs_dir / f"run-{ts}.yaml"
    with open(path, "w") as f:
        yaml.dump(run, f, default_flow_style=False, sort_keys=False)
    return path


def load_run(path: Path) -> dict:
    """Load a run entry from a YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)


def get_last_run_ts(runs_dir: Path) -> str | None:
    """Get the started timestamp of the most recent run."""
    if not runs_dir.exists():
        return None
    runs = sorted(runs_dir.glob("run-*.yaml"))
    if not runs:
        return None
    last = load_run(runs[-1])
    return last.get("started")
