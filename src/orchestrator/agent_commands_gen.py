"""Stamp first-class slash commands over an agent's entry-point skills.

Commands — not skills — are the launch surface a human or the harness triggers.
A skill is model-invoked (the model *decides* to load it from its description); a
command is caller-invoked, namespaced (`/<slug>:<name>`), and discoverable. Every
agent's entry-point skills should therefore have a thin command wrapper, so the
capability that lives in `skills/<x>/SKILL.md` is actually launchable.

This module is the generator that stamps those wrappers. It is:
  - DRY — the wrapper is generated from the skill's own frontmatter `description`,
  - idempotent — it NEVER clobbers an existing `commands/<name>.md`,
  - additive — it only writes; it never deletes.

Which skills get a command (the "entry-point" policy). There is deliberately NO
per-skill `launchable` flag — a command is launchable by definition, so a flag on
the skill would be redundant. Instead a skill is promoted UNLESS it is:
  - a framework internal every agent carries (`FRAMEWORK_SKILLS`) — `turn`/`setup`
    get their own dedicated command wrappers; the rest are never launched directly,
  - an eval/QA grader (name ends `-eval` / `-qa`) — invoked by an orchestrator,
  - listed in the agent's own `commands/.exclude` (one skill name per line, `#`
    comments allowed) — the escape hatch for domain sub-steps and utilities that
    only make sense when another skill drives them (e.g. a pipeline's later stages,
    a shared `gdoc-writer`/`email-communicator` utility).

Everything else is promoted by default: the permissive bias is intentional — an
entry-point skill with no command is invisible to a launcher, which is the failure
this closes.
"""
from __future__ import annotations

import re
from pathlib import Path

# Operating-model skills every agent inherits from the factory. `turn` and `setup`
# have their own command wrappers; the others are gates/state that nobody *launches*.
FRAMEWORK_SKILLS = {"turn", "setup", "task-tracker", "agent-turn-review", "self-review"}
_GRADER_SUFFIXES = ("-eval", "-qa")


def _frontmatter(text: str) -> str:
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    return m.group(1) if m else ""


def skill_description(skill_md: str) -> str:
    """Condense a skill's frontmatter `description` into one command-sized line.

    Handles YAML folded (`>`) multi-line blocks, drops the trigger tail
    ("Use when …"), and trims to a whole-sentence (never mid-word) boundary.
    """
    fm = _frontmatter(skill_md)
    dm = re.search(
        r"^description:\s*(?:[>|][-+]?)?\s*\n?(.*?)(?=^\w[\w-]*:\s|\Z)",
        fm + "\n",
        re.S | re.M,
    )
    if not dm:
        return ""
    desc = " ".join(line.strip() for line in dm.group(1).splitlines() if line.strip())
    for cut in (" Use when", " Use for", " Use to", " Triggers on", " Usage"):
        i = desc.find(cut)
        if i != -1:
            desc = desc[:i]
            break
    desc = desc.strip().rstrip(".")
    if len(desc) > 200:
        seg = desc[:200]
        j = seg.rfind(". ")
        if j > 60:
            desc = seg[: j + 1].rstrip(".")
        else:
            k = seg.rfind(" ")            # never truncate mid-word
            desc = seg[:k] if k > 60 else seg
    return (desc + ".") if desc else ""


_COMMAND_TEMPLATE = """---
description: {desc}
---

Run {name_display}'s `{skill}` procedure.

Read `skills/{skill}/SKILL.md` and follow it **in order**, top to bottom — do not run it from
memory.

Scope (from arguments): **$ARGUMENTS**

Guardrail (unchanged): reads are free; **every outbound action — sending, publishing, writing —
waits for explicit human approval.** {name_display} drafts; the human disposes.
"""


def command_body(agent_name: str, skill: str, desc: str) -> str:
    return _COMMAND_TEMPLATE.format(desc=desc, name_display=agent_name, skill=skill)


def _load_exclude(commands_dir: Path) -> set[str]:
    f = commands_dir / ".exclude"
    if not f.exists():
        return set()
    out = set()
    for line in f.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.add(line)
    return out


def _agent_name(repo: Path) -> str:
    """Best-effort display name from config/agent.json, else the plugin name, else dir."""
    import json

    for rel, key in (("config/agent.json", "name"), (".claude-plugin/plugin.json", "name")):
        p = repo / rel
        if p.exists():
            try:
                d = json.loads(p.read_text())
                val = d.get("display_name") or d.get(key) or ""
                if val:
                    return val if rel.endswith("agent.json") else str(val).title()
            except (ValueError, OSError):
                pass
    return repo.name.title()


def plan_commands(repo: Path) -> dict:
    """Compute what stamp_commands would do, without writing. Pure + testable.

    Returns {"create": [{skill, path, description}], "skip": [{skill, reason}]}.
    """
    repo = Path(repo)
    skills_dir = repo / "skills"
    commands_dir = repo / "commands"
    agent_name = _agent_name(repo)
    exclude = _load_exclude(commands_dir)

    create, skip = [], []
    if not skills_dir.is_dir():
        return {"create": create, "skip": skip, "agent_name": agent_name}

    for skill_path in sorted(skills_dir.iterdir()):
        md = skill_path / "SKILL.md"
        if not md.is_file():
            continue
        name = skill_path.name
        cmd_path = commands_dir / f"{name}.md"
        if name in FRAMEWORK_SKILLS:
            skip.append({"skill": name, "reason": "framework"})
        elif name.endswith(_GRADER_SUFFIXES):
            skip.append({"skill": name, "reason": "grader"})
        elif name in exclude:
            skip.append({"skill": name, "reason": "excluded"})
        elif cmd_path.exists():
            skip.append({"skill": name, "reason": "exists"})
        else:
            desc = skill_description(md.read_text()) or f"Run the {name} procedure."
            create.append({"skill": name, "path": str(cmd_path), "description": desc})
    return {"create": create, "skip": skip, "agent_name": agent_name}


def stamp_commands(repo: Path, *, write: bool = True) -> dict:
    """Stamp missing command wrappers for entry-point skills. Idempotent, additive.

    Returns the same shape as plan_commands; when write=True the `create` files are
    written to disk.
    """
    repo = Path(repo)
    plan = plan_commands(repo)
    if write and plan["create"]:
        commands_dir = repo / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        for item in plan["create"]:
            Path(item["path"]).write_text(
                command_body(plan["agent_name"], item["skill"], item["description"])
            )
    return plan
