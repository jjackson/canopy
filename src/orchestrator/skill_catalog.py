"""Enumerate available Claude Code skills across user, project, and plugin scopes.

Used by the proposer to avoid suggesting skills that already exist, and by the
`canopy skills list` CLI for inspection.

Catalog entry shape:
    {
        "name": "doctor",                  # bare skill name
        "qualified": "canopy:doctor",      # plugin:skill, or just name for user-scope
        "scope": "plugin" | "user",        # where it lives
        "source": "canopy" | "user",       # plugin name, or "user" for ~/.claude/skills/
        "description": "...",              # one-line description from frontmatter
        "path": "/abs/path/to/SKILL.md",
    }
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

PLUGIN_CACHE = Path.home() / ".claude" / "plugins" / "cache"
USER_SKILLS = Path.home() / ".claude" / "skills"


def _parse_frontmatter_description(skill_md: Path) -> str:
    """Extract the `description` field from a SKILL.md frontmatter block.

    Returns "" if the file is missing or has no description.
    """
    try:
        text = skill_md.read_text()
    except OSError:
        return ""
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""
    frontmatter = parts[1]
    desc_lines: list[str] = []
    in_desc = False
    for line in frontmatter.splitlines():
        if line.startswith("description:"):
            in_desc = True
            value = line.split(":", 1)[1].strip()
            if value and value not in (">", "|"):
                return value.strip("\"'")
            continue
        if in_desc:
            if line and not line.startswith(" ") and not line.startswith("\t"):
                break
            stripped = line.strip()
            if stripped:
                desc_lines.append(stripped)
    return " ".join(desc_lines).strip("\"'")


def _scan_plugin_caches(cache_root: Path = PLUGIN_CACHE) -> list[dict]:
    """Scan ~/.claude/plugins/cache/<plugin>/<plugin>/<version>/skills/."""
    entries: list[dict] = []
    if not cache_root.exists():
        return entries
    for plugin_root in sorted(cache_root.iterdir()):
        if not plugin_root.is_dir():
            continue
        plugin_name = plugin_root.name
        # Find the highest-version dir under <plugin>/<plugin>/<version>/
        versioned = plugin_root / plugin_name
        if not versioned.is_dir():
            continue
        version_dirs = [d for d in versioned.iterdir() if d.is_dir()]
        if not version_dirs:
            continue
        # Pick the lexicographically largest version dir as "current"
        current = max(version_dirs, key=lambda d: d.name)
        skills_dir = current / "skills"
        if not skills_dir.is_dir():
            continue
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                continue
            entries.append({
                "name": skill_dir.name,
                "qualified": f"{plugin_name}:{skill_dir.name}",
                "scope": "plugin",
                "source": plugin_name,
                "description": _parse_frontmatter_description(skill_md),
                "path": str(skill_md),
            })
    return entries


def _scan_user_skills(user_dir: Path = USER_SKILLS) -> list[dict]:
    """Scan ~/.claude/skills/<name>/SKILL.md."""
    entries: list[dict] = []
    if not user_dir.exists():
        return entries
    for skill_dir in sorted(user_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        entries.append({
            "name": skill_dir.name,
            "qualified": skill_dir.name,
            "scope": "user",
            "source": "user",
            "description": _parse_frontmatter_description(skill_md),
            "path": str(skill_md),
        })
    return entries


def build_catalog(
    plugin_cache: Path = PLUGIN_CACHE,
    user_skills: Path = USER_SKILLS,
) -> list[dict]:
    """Return all known skills across plugin and user scopes."""
    return _scan_plugin_caches(plugin_cache) + _scan_user_skills(user_skills)


# --- Overlap detection ---


_NAME_LIKE = re.compile(r"[a-z][a-z0-9-]{2,}(?::[a-z][a-z0-9-]{2,})?")


def extract_candidate_names(text: str) -> list[str]:
    """Pull skill-name-shaped tokens out of a proposal action string.

    Matches bare names (`doctor`) and plugin-qualified names (`canopy:doctor`).
    Used to guess which skill name a `new_skill` proposal is actually proposing.
    """
    if not text:
        return []
    candidates: list[str] = []
    seen: set[str] = set()
    for match in _NAME_LIKE.findall(text.lower()):
        if match in seen:
            continue
        seen.add(match)
        candidates.append(match)
    return candidates


def find_overlap(
    proposal_action: str,
    catalog: Iterable[dict],
) -> dict | None:
    """If the proposal action mentions an existing skill, return the matching entry.

    Matching rules (conservative, to avoid false positives on common English words
    that happen to be skill names like `health`, `ship`, `learn`):

    - A `plugin:skill` qualified token always matches if it equals an existing
      qualified name.
    - A bare token only matches if it is hyphenated (e.g. `project-status`),
      since most short single-word matches are spurious. Skills with single-word
      names (`doctor`, `ship`) can only be flagged via their qualified form.
    """
    candidates = extract_candidate_names(proposal_action)
    if not candidates:
        return None
    plugin_qualified: dict[str, dict] = {}
    hyphenated_bare: dict[str, dict] = {}
    for entry in catalog:
        qualified = entry["qualified"].lower()
        name = entry["name"].lower()
        if ":" in qualified:
            plugin_qualified.setdefault(qualified, entry)
        if "-" in name:
            hyphenated_bare.setdefault(name, entry)
    for cand in candidates:
        if cand in plugin_qualified:
            return plugin_qualified[cand]
        if "-" in cand and cand in hyphenated_bare:
            return hyphenated_bare[cand]
    return None


def format_for_prompt(catalog: list[dict], max_entries: int = 200) -> str:
    """Render the catalog as a compact list suitable for an LLM prompt."""
    if not catalog:
        return "(no existing skills detected)"
    lines: list[str] = []
    truncated = catalog[:max_entries]
    for entry in truncated:
        desc = entry.get("description", "") or ""
        if len(desc) > 120:
            desc = desc[:117] + "..."
        lines.append(f"- {entry['qualified']} — {desc}" if desc else f"- {entry['qualified']}")
    if len(catalog) > max_entries:
        lines.append(f"... ({len(catalog) - max_entries} more not shown)")
    return "\n".join(lines)
