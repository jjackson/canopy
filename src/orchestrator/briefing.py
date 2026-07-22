"""Strategic brief generation with gstack cognitive patterns.

Replaces the simple digest with a CEO-level report that applies
inversion reflex, leverage obsession, focus as subtraction, and
proxy skepticism to the orchestrator's data.
"""
import subprocess
from pathlib import Path

import yaml

from orchestrator.observations import list_observations
from orchestrator.patterns import detect_patterns
from orchestrator.prompts import load_prompt
from orchestrator.proposals import list_proposals
from orchestrator.run_log import load_run
from orchestrator.tracker import load_outcomes, compute_success_rates


def generate_brief(
    state_dir: Path,
    model: str = "sonnet",
    max_budget_usd: float = 1.00,
) -> str:
    """Generate a strategic brief. Returns markdown string."""
    prompt = build_brief_prompt(state_dir)

    try:
        result = subprocess.run(
            [
                "claude", "-p", prompt,
                "--model", model,
                "--max-budget-usd", str(max_budget_usd),
                "--no-session-persistence",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return _fallback_brief(state_dir)

    if result.returncode != 0:
        return _fallback_brief(state_dir)

    return result.stdout


def build_brief_prompt(state_dir: Path) -> str:
    """Construct the brief prompt from orchestrator state."""
    # Recent runs
    runs_dir = state_dir / "runs"
    recent_activity = "No recent runs."
    if runs_dir.exists():
        run_files = sorted(runs_dir.glob("run-*.yaml"))[-5:]
        if run_files:
            lines = []
            for rf in run_files:
                run = load_run(rf)
                if run:
                    lines.append(
                        f"- {run.get('started', '?')}: "
                        f"{run.get('transcripts_analyzed', 0)} transcripts, "
                        f"{run.get('observations_created', 0)} observations, "
                        f"{run.get('proposals_implemented', 0)} implemented"
                    )
            recent_activity = "\n".join(lines) if lines else "No recent runs."

    # Patterns
    obs_dir = state_dir / "observations"
    patterns = detect_patterns(obs_dir)
    patterns_text = yaml.dump(patterns[:5], default_flow_style=False) if patterns else "No patterns detected yet."

    # Pending observations
    pending = list_observations(obs_dir, status="pending")
    pending_text = ""
    for obs in sorted(pending, key=lambda o: -o.get("frequency", 1))[:10]:
        pending_text += f"- [{obs.get('severity')}] {obs.get('description')} (seen {obs.get('frequency', 1)}x)\n"
    if not pending_text:
        pending_text = "No pending observations."

    # Track record
    tracker_path = state_dir / "tracker.jsonl"
    outcomes = load_outcomes(tracker_path)
    if outcomes:
        rates = compute_success_rates(outcomes)
        track_record = yaml.dump(rates, default_flow_style=False)
    else:
        track_record = "No proposal outcomes tracked yet."

    return load_prompt(
        "briefing",
        recent_activity=recent_activity,
        patterns=patterns_text,
        pending_observations=pending_text,
        track_record=track_record,
    )


def _fallback_brief(state_dir: Path) -> str:
    """Generate a simple brief without calling claude -p."""
    from orchestrator.digest import generate_digest
    return generate_digest(state_dir)
