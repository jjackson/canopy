"""Construct prompts and invoke claude -p to generate proposals from observations."""
import subprocess

import yaml

from orchestrator.prompts import load_prompt


def build_proposal_prompt(
    observations: list[dict],
    registry_summary: str,
    skill_catalog: str = "",
) -> str:
    """Build the full prompt for proposal generation.

    `skill_catalog` is a pre-formatted string listing existing skills (see
    `orchestrator.skill_catalog.format_for_prompt`) — passed in so the LLM
    can avoid proposing duplicates of skills that already exist.
    """
    observations_yaml = yaml.dump(observations, default_flow_style=False)
    return load_prompt(
        "propose",
        registry_summary=registry_summary,
        observations_yaml=observations_yaml,
        skill_catalog=skill_catalog or "(catalog unavailable)",
    )


def parse_proposal_output(output: str) -> list[dict]:
    """Parse YAML proposal list from Claude's output."""
    text = output.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        result = yaml.safe_load(text)
    except yaml.YAMLError:
        return []

    if not isinstance(result, list):
        return []

    return result


def generate_proposals(
    observations: list[dict],
    registry_summary: str,
    model: str = "sonnet",
    max_budget_usd: float = 0.50,
    skill_catalog: str = "",
) -> list[dict]:
    """Generate proposals by invoking claude -p. Returns list of proposals."""
    prompt = build_proposal_prompt(observations, registry_summary, skill_catalog)

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
        return []

    if result.returncode != 0:
        return []

    return parse_proposal_output(result.stdout)
