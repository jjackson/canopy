"""Invoke any Claude Code skill headlessly via slash commands.

The skill runner sends slash commands to `claude -p` with an instruction
to auto-select recommended options for any interactive decisions.
Plugin-agnostic: works with gstack, superpowers, canopy, or any skill.

Usage:
    result = run_skill("/review", context="Check src/foo.py for issues")
    result = run_skill("/qa", context="Test the MCP server", cwd=repo_path)
    result = run_skill("/plan-eng-review", context="Review the architecture")

The AUTO_SELECT_INSTRUCTION tells Claude to:
- Always pick the recommended option for AskUserQuestion
- Never wait for human input
- Complete the full workflow without pausing

This is the core infrastructure that enables autonomous convergence
with gstack, superpowers, and any future skill system.
"""
import subprocess
from dataclasses import dataclass
from pathlib import Path


AUTO_SELECT_INSTRUCTION = """
IMPORTANT: You are running autonomously as part of an automated improvement
pipeline. For ANY interactive question, menu, or decision prompt:
- Always select the RECOMMENDED option
- If no option is marked as recommended, select the first option
- Do NOT wait for human input
- Do NOT use AskUserQuestion — make the decision and proceed
- Complete the full workflow without pausing
"""


@dataclass
class SkillResult:
    """Result from running a skill."""
    success: bool
    output: str
    skill: str
    error: str | None = None


def build_skill_prompt(skill_command: str, context: str) -> str:
    """Build the prompt for headless skill invocation."""
    return f"""{AUTO_SELECT_INSTRUCTION}

Run the following skill command:
{skill_command} {context}
"""


def run_skill(
    skill_command: str,
    context: str,
    cwd: Path | None = None,
    model: str = "sonnet",
    max_budget_usd: float = 2.00,
    timeout: int = 300,
) -> SkillResult:
    """Run a Claude Code skill headlessly.

    Args:
        skill_command: The slash command (e.g., "/review")
        context: Context for the skill
        cwd: Working directory for the skill invocation
        model: Model to use
        max_budget_usd: Budget cap for the invocation
        timeout: Timeout in seconds
    """
    prompt = build_skill_prompt(skill_command, context)

    cmd = [
        "claude", "-p", prompt,
        "--model", model,
        "--max-budget-usd", str(max_budget_usd),
        "--no-session-persistence",
    ]

    kwargs = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
    }
    if cwd:
        kwargs["cwd"] = cwd

    try:
        result = subprocess.run(cmd, **kwargs)
    except subprocess.TimeoutExpired:
        return SkillResult(
            success=False,
            output="",
            skill=skill_command,
            error=f"Timeout after {timeout}s",
        )

    return SkillResult(
        success=result.returncode == 0,
        output=result.stdout,
        skill=skill_command,
        error=result.stderr if result.returncode != 0 else None,
    )
