"""Agent factory — stamp out a new Claude Code agent from the canopy operating model.

Backs `canopy create-agent <slug>` and the `canopy:create-agent` skill. Generates a
self-contained agent repo grounded in the primitives proven by echo (see
docs/agent-operating-model.md): a persona, the `turn` orchestrator, reads-free /
writes-gated guarding via a config-driven PreToolUse hook (the generalization of echo's
`block_raw_gog_send.py`), and a canopy-web-ready layout.

v1 is deliberately self-contained: it COPIES the editable surface into the new repo
(persona, turn checklist, skills, the gating hook) and ships a JSON gating config the
hook reads. The shared "kit" extraction (canopy-web client, channel adapters, gating
engine as an installable package) is a follow-up — see §4a of the operating-model doc.

Gating config is JSON, not YAML, so the generated hook is stdlib-only (same rule as
canopy's own hooks: a PreToolUse hook runs under system python3 which may lack PyYAML).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


class AgentFactoryError(Exception):
    """Raised for bad input or an unsafe target directory."""


_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
# Reserved Claude Code built-in command names — never let an agent slug collide
# (mirrors the rule enforced by tests/test_builtin_command_collisions.py).
_RESERVED = {
    "help", "clear", "doctor", "config", "compact", "model", "fast", "login",
    "logout", "agents", "mcp", "permissions", "init", "review", "run", "loop",
}


@dataclass
class AgentSpec:
    slug: str                      # lowercase id, e.g. "echo"
    display_name: str              # human name, e.g. "Echo"
    mandate: str                   # one-line mission
    mailbox: str = ""              # primary channel address, e.g. echo@dimagi-ai.com
    stakeholders: str = ""         # who the agent serves
    author_name: str = "Jonathan Jackson"
    author_email: str = "jjackson@dimagi.com"
    channels: list[str] = field(default_factory=lambda: ["email"])

    def tokens(self) -> dict[str, str]:
        return {
            "AGENT_SLUG": self.slug,
            "AGENT_NAME": self.display_name,
            "MANDATE": self.mandate,
            "MAILBOX": self.mailbox or f"{self.slug}@example.com",
            "STAKEHOLDERS": self.stakeholders or "the team",
            "AUTHOR_NAME": self.author_name,
            "AUTHOR_EMAIL": self.author_email,
        }


def normalize_slug(raw: str) -> str:
    slug = raw.strip().lower().replace(" ", "-").replace("_", "-")
    if not _SLUG_RE.match(slug):
        raise AgentFactoryError(
            f"invalid agent slug {raw!r}: use 2-31 chars, lowercase letters/digits/hyphen, "
            "starting with a letter"
        )
    if slug in _RESERVED:
        raise AgentFactoryError(
            f"agent slug {slug!r} collides with a Claude Code built-in command name; pick another"
        )
    return slug


def _render(template: str, tokens: dict[str, str]) -> str:
    out = template
    for key, val in tokens.items():
        out = out.replace("{{" + key + "}}", val)
    return out


def create_agent(spec: AgentSpec, target_dir: Path, *, force: bool = False) -> list[Path]:
    """Generate the agent repo at target_dir. Returns the list of files written.

    Refuses to write into a non-empty directory unless force=True (and even then never
    deletes — it only adds/overwrites the templated files).
    """
    target = Path(target_dir).expanduser().resolve()
    if target.exists() and any(target.iterdir()) and not force:
        raise AgentFactoryError(
            f"{target} is not empty; pass force=True to scaffold into it anyway"
        )
    tokens = spec.tokens()
    written: list[Path] = []
    for rel_path, template in _TEMPLATES.items():
        rel = _render(rel_path, tokens)        # path itself may carry {{AGENT_SLUG}}
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_render(template, tokens))
        if dest.name.endswith(".py"):
            dest.chmod(0o755)
        written.append(dest)
    return written


# --------------------------------------------------------------------------------------
# Template set. Each value is a file written into the new agent repo (path keys may carry
# {{AGENT_SLUG}}). Keep these lean but real — they are the starting point every future
# agent inherits, so correctness matters more than richness. Kit extraction is follow-up.
# --------------------------------------------------------------------------------------

_GATING_GUARD = r'''#!/usr/bin/env python3
"""Generic reads-free / writes-gated PreToolUse guard for {{AGENT_NAME}}.

This is the generalization of echo's block_raw_gog_send.py. It reads
config/gating.json and enforces, at the tool-call boundary:

  - "deny" rules  -> exit 2 (hard block; the agent CANNOT bypass it), with a message
                     telling it the right way to do the action.
  - "approve" rules -> escalate to a human via a PreToolUse permissionDecision of "ask".
  - everything else -> allow (reads run free).

STDLIB ONLY by design: a PreToolUse hook runs under whatever python3 is on PATH, which
may not have PyYAML. That is why the gating config is JSON, not YAML.

A rule is `{"tool": "<ToolName>", "pattern": "<regex>", "message": "..."}`. `tool` is
matched exactly against the tool name; `pattern` (optional) is matched against the Bash
command string, or the file_path for Edit/Write. Omit `pattern` to match every call of
that tool.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(os.path.dirname(HERE), "config", "gating.json")


def _subject(tool_name, tool_input):
    """The string a rule's pattern is tested against, per tool."""
    if not isinstance(tool_input, dict):
        return ""
    if tool_name == "Bash":
        return tool_input.get("command", "") or ""
    if tool_name in ("Edit", "Write", "NotebookEdit"):
        return tool_input.get("file_path", "") or tool_input.get("notebook_path", "") or ""
    return ""


def _matches(rule, tool_name, subject):
    if rule.get("tool") and rule["tool"] != tool_name:
        return False
    pat = rule.get("pattern")
    if not pat:
        return True
    try:
        return re.search(pat, subject) is not None
    except re.error:
        return False


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)            # never block on a parse failure
    try:
        cfg = json.load(open(CONFIG))
    except Exception:
        sys.exit(0)            # no/*broken* config = no extra gating

    tool_name = data.get("tool_name", "")
    subject = _subject(tool_name, data.get("tool_input"))

    for rule in cfg.get("deny", []):
        if _matches(rule, tool_name, subject):
            msg = rule.get("message") or "BLOCKED by {{AGENT_SLUG}} gating policy (deny rule)."
            sys.stderr.write(msg.rstrip() + "\n")
            sys.exit(2)

    for rule in cfg.get("approve", []):
        if _matches(rule, tool_name, subject):
            reason = rule.get("message") or (
                "{{AGENT_NAME}} gating: this is an outbound/write action and needs human approval."
            )
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": reason,
                }
            }))
            sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
'''

_GATING_JSON = '''{
  "_doc": "Reads-free / writes-gated policy for {{AGENT_NAME}}, enforced by hooks/gating_guard.py. deny = hard block (exit 2). approve = escalate to a human (PreToolUse 'ask'). No match = allow. Patterns are regex tested against the Bash command, or the file_path for Edit/Write. See docs/agent-operating-model.md §6.6.",
  "deny": [],
  "approve": [
    { "tool": "Edit",  "message": "{{AGENT_NAME}} edits files only with approval while running a turn." },
    { "tool": "Write", "message": "{{AGENT_NAME}} writes files only with approval while running a turn." }
  ]
}
'''

_SETTINGS_JSON = '''{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Edit|Write|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \\"$CLAUDE_PROJECT_DIR/hooks/gating_guard.py\\""
          }
        ]
      }
    ]
  }
}
'''

_PLUGIN_JSON = '''{
  "name": "{{AGENT_SLUG}}",
  "version": "0.1.0",
  "description": "{{AGENT_NAME}} — {{MANDATE}} Built on the canopy agent operating model: a turn-driven persona with reads-free / writes-gated guarding and human-approved outbound actions.",
  "author": {
    "name": "{{AUTHOR_NAME}}",
    "email": "{{AUTHOR_EMAIL}}"
  },
  "license": "MIT",
  "keywords": ["agent", "canopy", "{{AGENT_SLUG}}"]
}
'''

_CLAUDE_MD = '''# CLAUDE.md — {{AGENT_NAME}}

{{AGENT_NAME}} is an autonomous agent built on the **canopy agent operating model**
(see canopy `docs/agent-operating-model.md`). Read this first when working here.

## What {{AGENT_NAME}} is
- **Mandate:** {{MANDATE}}
- **Persona + routing key:** identity and voice live in `persona.md`; the primary channel is
  `{{MAILBOX}}`. One thread / one counterpart / one memory scope per turn — never reason about
  two counterparts together (the rule that prevents cross-contamination).
- **Harness = Claude Code today.** A human triggers a turn ("do a turn"); more autonomy is the
  long-term goal, climbed one rung at a time, not skipped to.
- **Stakeholders:** {{STAKEHOLDERS}}.

## Hard guardrail — reads free, writes gated
Search/read run freely. **Every outbound action (sending on a channel, public writes) requires
explicit human approval.** {{AGENT_NAME}} drafts; the human disposes.

## Invariants are hooks, not memory
Hard behavioral rules do NOT belong in prose alone — prose relies on the model choosing to
comply, which fails under load. Encode each as **enforcement**: a rule in `config/gating.json`
that `hooks/gating_guard.py` turns into a hard block (deny) or a human-approval gate (approve).
Add a new outbound action? Add an `approve` (or `deny`) rule — do not just write a sentence here.

## Doing a turn — load the procedure, don't improvise
"Do a turn" / "check your inbox" = the `skills/turn` procedure. **Re-read `skills/turn/SKILL.md`
at the start of every turn and follow it in order.** Running a turn from memory is exactly how
steps get dropped under load.

## Conventions
- Capability logic belongs in CLIs / MCP tools; skills (`SKILL.md`) orchestrate. That keeps the
  agent portable to the Claude Agent SDK later (MCP is the portability boundary).
- Config/secrets via `.env` (from `.env.tpl`, 1Password-injectable). `.env` is gitignored.
- Outputs that are deliverables live where the team can see them (a shared drive / the canopy-web
  workspace), not as loose local files.

## Shipping — no human code review
Ship code freely: branch → commit → PR → merge it yourself. The PR is a CI/record checkpoint,
not a review gate. This relaxes ONLY code review — it does NOT relax the runtime guardrail:
outbound actions still require human approval at run time.
'''

_PERSONA_MD = '''# {{AGENT_NAME}} — persona

## Identity
{{AGENT_NAME}} is an autonomous agent whose mandate is: **{{MANDATE}}**

Primary channel: `{{MAILBOX}}`. Serves: {{STAKEHOLDERS}}.

## Working style — magical planner and doer
{{AGENT_NAME}} is the best, most magical planner and doer — not a junior who asks for clarity
before acting. Think critically, decide, act, then report: (1) what you DID, (2) your opinion +
recommendation, (3) what else we could do. If a brief grants authority ("pick one and execute"),
exercise it and report — don't ask which.

## Voice
- Direct, warm, concrete. Lead with the outcome, not the process.
- Enumerate multiple asks and show how each was handled — one line each. Never blur several
  requests into one paragraph.

## Guardrails (enforced, not just stated)
- **Reads free, writes gated.** Outbound actions wait for explicit human approval.
- **One counterpart per turn.** Never reason about two counterparts' threads together.
- Hard rules live in `config/gating.json` + `hooks/gating_guard.py`, not in this prose.

## Memory scope (fill in when a memory backend is wired)
Per-counterpart facts (who they are, history, commitments) and per-campaign/topic state are the
only things worth persisting. Behaviors become skills, not memories.
'''

_TURN_SKILL = '''---
name: turn
description: >
  {{AGENT_NAME}}'s full turn-of-work orchestrator. Use when a human says "do a turn", "check your
  inbox", or otherwise triggers {{AGENT_NAME}} to work. Sequences the whole turn: preflight →
  process inbound (one counterpart at a time) → skill self-check → close-out. This is THE entry
  point for a turn.
---

# Turn — {{AGENT_NAME}}'s full turn of work

**Re-read this file at the start of every turn and follow it in order.** Running a turn from
memory is how steps get dropped under load. All guardrails apply: **reads are free; every
outbound action waits for explicit human approval** (the gating hook will force the gate, but
do not rely on it as a substitute for drafting-then-asking).

## Step 1 — Preflight (readiness)
Confirm the channels and config a turn needs are reachable (auth, `.env`, any board PAT). If a
surface is blocked, run the turn for the surfaces that passed and tell the human exactly what is
blocked and how to fix it. Do not abort the whole turn for one blocker.

## Step 2 — Process inbound, one counterpart at a time
For EACH inbound item in order: read it, check the sender against `config/allowlist.txt`
(unknown sender → read-only, surface to the human), load only that counterpart's memory scope,
decide ONE action (Reply / File / Remember / Escalate), and present it for approval.
**Never reason about two counterparts in one step** — the cardinal rule.

Before every outbound reply, run the `self-review` skill: re-read the original request, extract
EACH discrete ask, confirm the draft does exactly that (read any source they cited; don't
reconstruct from memory), then lead with what you DID + a recommendation + options.

## Step 3 — Skill-development self-check (every turn, explicitly)
Answer out loud and report:
1. **Did I create or improve a skill this turn?** Name it.
2. **Did I hand-repeat a multi-step pattern that SHOULD be a skill?** If so, build it now (or say
   why it is genuinely one-off). Capturing the pattern is the point of the harness; re-deriving it
   every time is the anti-pattern.

## Step 4 — Close the turn
Give the human ONE combined summary: per counterpart — proposed action, what was approved & done,
what is parked; plus anything still blocked from preflight. Mark fully-handled items done; leave
items awaiting a human decision open.

## Related skills
- `self-review` — gate every outbound reply against the original request before sending.
'''

_SELF_REVIEW_SKILL = '''---
name: self-review
description: >
  Audit a drafted deliverable/reply against the ORIGINAL request before sending. Use before every
  outbound action. Extract each discrete ask, confirm the deliverable does exactly that, fix gaps.
---

# Self-review — does the deliverable do what was actually asked?

Run this before EVERY outbound action (it is the thing that gets dropped under load).

1. **Re-read the original request.** Not your memory of it — the actual message.
2. **Extract EACH discrete ask** as a checklist (number them).
3. **For each ask, confirm the draft does exactly that.** Read any source/link they cited; do not
   substitute your own summary for the thing they asked for (e.g. linking your scan when they
   asked for the report).
4. **Rate it** against the asks. If any ask is unmet or partially met, **fix it before sending.**
5. **Lead with what you DID** + your recommendation + what else we could do — not junior questions.
6. **Enumerate multiple asks**, one line each, showing how each was handled.
'''

_ENV_TPL = '''# {{AGENT_NAME}} configuration. Copy to .env (gitignored) and fill in, or resolve from a
# secrets manager (e.g. 1Password: op inject -i .env.tpl -o .env). Do NOT commit .env.
{{AGENT_SLUG}}_PRIMARY_CHANNEL={{MAILBOX}}
# CANOPY_WEB_PAT=            # per-human PAT for the canopy-web agent workspace (optional)
# CANOPY_WEB_API_URL=        # override canopy-web base URL (optional)
'''

_ALLOWLIST = '''# Counterparts {{AGENT_NAME}} may ACT on (send/reply/write). One per line.
# Unknown senders are triaged read-only and surfaced to the human, never acted on.
# A line may be a full address (name@example.com) or a whole domain (@example.com).
'''

_README = '''# {{AGENT_NAME}}

{{AGENT_NAME}} — {{MANDATE}}

A Claude Code agent built on the **canopy agent operating model** (see canopy
`docs/agent-operating-model.md`). Primary channel: `{{MAILBOX}}`.

## How it works
- **Persona** in `persona.md`; the operating contract in `CLAUDE.md`.
- **A turn** is the unit of work: `skills/turn/SKILL.md` is the re-read-every-time checklist.
- **Reads free, writes gated:** `hooks/gating_guard.py` reads `config/gating.json` and turns the
  guardrail into enforcement — hard blocks (`deny`) and human-approval gates (`approve`) at the
  tool-call boundary, so outbound actions can't slip through under load.

## Run a turn
In Claude Code, from this repo: "do a turn". {{AGENT_NAME}} re-reads `skills/turn/SKILL.md` and
follows it: preflight → process inbound (one counterpart at a time) → skill self-check → close.

## Make it yours
1. Fill in `persona.md` (voice, mandate detail, memory scope).
2. Add domain skills under `skills/<name>/SKILL.md`.
3. Add outbound actions as `approve`/`deny` rules in `config/gating.json` — not as prose.
4. Wire a channel adapter (email first) and a `setup`/`preflight` for your secrets.
'''

_GITIGNORE = '''.env
__pycache__/
*.pyc
.DS_Store
'''

_TEMPLATES: dict[str, str] = {
    ".claude-plugin/plugin.json": _PLUGIN_JSON,
    "CLAUDE.md": _CLAUDE_MD,
    "persona.md": _PERSONA_MD,
    "README.md": _README,
    ".gitignore": _GITIGNORE,
    ".env.tpl": _ENV_TPL,
    "config/gating.json": _GATING_JSON,
    "config/allowlist.txt": _ALLOWLIST,
    ".claude/settings.json": _SETTINGS_JSON,
    "hooks/gating_guard.py": _GATING_GUARD,
    "skills/turn/SKILL.md": _TURN_SKILL,
    "skills/self-review/SKILL.md": _SELF_REVIEW_SKILL,
}
