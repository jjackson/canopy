"""Spawn claude -p sessions in target repos to execute proposals."""
import re
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


def extract_evidence(stdout: str, stderr: str) -> str:
    """Extract test result evidence from subprocess output.

    Looks for common test output patterns (pytest, unittest, etc.)
    and returns the most relevant lines. If no test pattern found,
    returns the last few lines of output.
    """
    lines = stdout.split("\n")

    # Look for pytest-style summary: "X passed", "X failed"
    for line in reversed(lines):
        if re.search(r"\d+ passed", line) or re.search(r"\d+ failed", line):
            return line.strip()

    # Look for "tests passed" / "tests failed" patterns
    for line in reversed(lines):
        if "test" in line.lower() and ("pass" in line.lower() or "fail" in line.lower()):
            return line.strip()

    # Fallback: last non-empty lines
    non_empty = [l.strip() for l in lines if l.strip()]
    return "\n".join(non_empty[-3:]) if non_empty else stderr[:200]


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
            "evidence": "",
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
            "evidence": "",
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
            "evidence": "",
        }

    return {
        "success": result.returncode == 0,
        "output": result.stdout,
        "error": result.stderr if result.returncode != 0 else None,
        "evidence": extract_evidence(result.stdout, result.stderr),
    }
