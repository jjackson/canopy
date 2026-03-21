"""Spawn claude -p sessions in target repos to execute proposals."""
import subprocess
from pathlib import Path

import yaml

from orchestrator.prompts import load_prompt


def build_implementation_prompt(
    proposal: dict,
    observation: dict,
    registry_summary: str,
    registry_path: str = "",
) -> str:
    """Build the full prompt for an implementation session."""
    return load_prompt(
        "implement",
        proposal_yaml=yaml.dump(proposal, default_flow_style=False),
        observation_yaml=yaml.dump(observation, default_flow_style=False),
        registry_summary=registry_summary,
        registry_path=registry_path,
    )


def resolve_repo_path(repo_path: str) -> Path:
    """Resolve a repo path, expanding ~ and making absolute."""
    return Path(repo_path).expanduser().resolve()


def run_implementation(
    proposal: dict,
    observation: dict,
    registry_summary: str,
    registry_path: str = "",
    model: str = "sonnet",
    max_budget_usd: float = 2.00,
) -> dict:
    """Run an implementation session. Returns result dict with success/output.

    For 'team' ownership, the implementation prompt instructs Claude to open
    a PR instead of merging. For 'external' ownership, skip implementation.
    """
    ownership = proposal.get("ownership", "self")

    if ownership == "external":
        return {
            "success": False,
            "error": "External repos are registry-only — skipping implementation",
            "output": "",
        }

    prompt = build_implementation_prompt(
        proposal, observation, registry_summary, registry_path=registry_path,
    )

    # For team repos, append PR instruction
    if ownership == "team":
        prompt += (
            "\n\nIMPORTANT: This is a team-owned repo. Do NOT merge to main. "
            "Instead, push the feature branch and open a pull request with "
            "`gh pr create` including the motivation in the PR description."
        )

    repo_path = resolve_repo_path(proposal["target_repo"])

    if not repo_path.exists():
        return {
            "success": False,
            "error": f"Target repo not found: {repo_path}",
            "output": "",
        }

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
            cwd=repo_path,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Implementation session timed out",
            "output": "",
        }

    return {
        "success": result.returncode == 0,
        "output": result.stdout,
        "error": result.stderr if result.returncode != 0 else None,
    }
