"""Construct prompts and invoke claude -p to extract observations from transcripts."""
import json
import subprocess
from pathlib import Path

import yaml

from orchestrator.prompts import load_prompt
from orchestrator.transcripts import read_transcript


def build_analysis_prompt(transcript_path: Path) -> str:
    """Build the full prompt for transcript analysis."""
    entries = read_transcript(transcript_path)

    # Build a chronological transcript summary preserving conversation flow
    parts = []
    for entry in entries:
        msg_type = entry.get("type")
        msg = entry.get("message", {})

        if msg_type == "user":
            content = msg.get("content", "") if isinstance(msg, dict) else ""
            if isinstance(content, str) and content:
                parts.append(f"USER: {content}")
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        result_preview = str(block.get("content", ""))[:200]
                        parts.append(f"TOOL RESULT: {result_preview}")

        elif msg_type == "assistant":
            content = msg.get("content", []) if isinstance(msg, dict) else []
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            parts.append(f"ASSISTANT: {block.get('text', '')[:500]}")
                        elif block.get("type") == "tool_use":
                            parts.append(
                                f"TOOL CALL: {block['name']}"
                                f"({json.dumps(block.get('input', {}))})"
                            )

    transcript_text = "\n".join(parts)

    return load_prompt(
        "analyze",
        transcript_text=transcript_text,
    )


def parse_analysis_output(output: str) -> list[dict]:
    """Parse YAML observation list from Claude's output."""
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


def analyze_transcript(
    transcript_path: Path,
    model: str = "sonnet",
    max_budget_usd: float = 0.50,
) -> list[dict]:
    """Analyze a transcript by invoking claude -p. Returns list of observations."""
    prompt = build_analysis_prompt(transcript_path)

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

    return parse_analysis_output(result.stdout)
