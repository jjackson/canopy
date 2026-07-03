"""Agent factory — stamp out a new Claude Code agent from the canopy operating model.

Backs `canopy create-agent <slug>` and the `canopy:create-agent` skill. Generates a
self-contained agent repo grounded in the primitives proven by echo (see
docs/agent-operating-model.md): a persona, the `turn` orchestrator, reads-free /
writes-gated guarding via a config-driven PreToolUse hook (the generalization of echo's
`block_raw_gog_send.py`), and a canopy-web-ready layout.

v1 is deliberately self-contained: it COPIES the editable surface into the new repo
(persona, turn checklist, skills, the gating hook) and ships a JSON gating config the
hook reads. Gating defaults to DENY RAILS ONLY with an empty `approve` list — approval
lives procedurally in the turn checklist, never in a blocking hook modal (the §1a
"rails, not gates" revision; see docs/architecture/shared-gog-gdrive.md §4). The email
channel is a thin `bin/<slug>-email` shim over the shared `canopy email` engine
(orchestrator.agent_email), with a deny rail blocking raw `gog gmail send/reply`.

Gating config is JSON, not YAML, so the generated hook is stdlib-only (same rule as
canopy's own hooks: a PreToolUse hook runs under system python3 which may lack PyYAML).
"""
from __future__ import annotations

import re
import sys
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
    if "@example.com" in tokens["MAILBOX"]:
        print(
            f"WARNING: no --mailbox given — scaffolding with placeholder "
            f"{tokens['MAILBOX']!r}. Email will fail late and confusingly at gog "
            f"send/login; set the real mailbox in config/agent.json before the first turn.",
            file=sys.stderr,
        )
    written: list[Path] = []
    for rel_path, template in _TEMPLATES.items():
        rel = _render(rel_path, tokens)        # path itself may carry {{AGENT_SLUG}}
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_render(template, tokens))
        if dest.name.endswith(".py") or dest.parent.name == "bin":
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


def _summarize_action(tool_name, subject):
    """A crisp, human-readable summary of the GATED action — so the approval prompt says exactly
    WHAT you're approving at a glance, not a generic 'needs approval' over a wall of bash."""
    if tool_name != "Bash":
        return tool_name + " -> " + subject[:80]
    s = subject
    m = re.search(r"\bgit\s+push\b([^\n;&|]*)", s)
    if m:
        args = [a for a in m.group(1).split() if not a.startswith("-")]
        return "git PUSH -> " + (" ".join(args[:2]) if args else "default remote/branch")
    m = re.search(r"\bgh\s+pr\s+create\b([^\n;&|]*)", s)
    if m:
        t = re.search(r"--title[= ]+[\"']?([^\"'\n]{0,60})", m.group(1))
        r = re.search(r"-R[= ]+(\S+)", m.group(1))
        return "OPEN a PR" + (' "' + t.group(1).strip() + '"' if t else "") + (" in " + r.group(1) if r else "")
    m = re.search(r"\bgh\s+pr\s+merge\b([^\n;&|]*)", s)
    if m:
        n = re.search(r"\b(\d+)\b", m.group(1))
        r = re.search(r"-R[= ]+(\S+)", m.group(1))
        return "MERGE a PR" + (" #" + n.group(1) if n else "") + (" in " + r.group(1) if r else "")
    m = re.search(r"\bgh\s+repo\s+(create|delete)\b([^\n;&|]*)", s)
    if m:
        nm = re.search(r"([\w.-]+/[\w.-]+|[\w.-]+)", m.group(2))
        return m.group(1).upper() + " GitHub repo" + (" " + nm.group(1) if nm else "")
    return s.strip().replace("\n", " ")[:100]


def _approval_reason(rule, tool_name, subject, cwd):
    """A scannable approval prompt: WHAT (parsed action) + WHERE (repo) + the exact command +
    WHY (policy note). One glance should be enough to decide."""
    action = _summarize_action(tool_name, subject)
    repo = os.path.basename(cwd.rstrip("/")) if cwd else ""
    cmd = subject.strip().replace("\n", " ")
    if len(cmd) > 220:
        cmd = cmd[:220] + " ..."
    note = rule.get("message") or "outbound/write action - needs your approval."
    head = "APPROVE {{AGENT_NAME}} -> " + action + ("   (repo: " + repo + ")" if repo else "")
    return head + "\n  why: " + note + "\n  full command: " + cmd


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
    cwd = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR", "")

    for rule in cfg.get("deny", []):
        if _matches(rule, tool_name, subject):
            msg = rule.get("message") or "BLOCKED by {{AGENT_SLUG}} gating policy (deny rule)."
            sys.stderr.write(msg.rstrip() + "\n")
            sys.exit(2)

    for rule in cfg.get("approve", []):
        if _matches(rule, tool_name, subject):
            reason = _approval_reason(rule, tool_name, subject, cwd)
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
  "_doc": "Rails, not gates (docs/agent-operating-model.md §1a revision, Jon 2026-07-01; canopy docs/architecture/shared-gog-gdrive.md §4): hooks carry DENY rails only — make the wrong path impossible and name the right one, so {{AGENT_NAME}} self-corrects and keeps going at zero autonomy cost. `approve` stays EMPTY by default: a PreToolUse 'ask' is a blocking modal that stalls autonomous work and nags interactive sessions; approval semantics live in the procedural layer (skills/turn Step 2's 'present for approval'). Enforced by hooks/gating_guard.py: deny = hard block (exit 2). Patterns are regex tested against the Bash command, or the file_path for Edit/Write.",
  "deny": [
    {
      "tool": "Bash",
      "pattern": "(?:^|[\\\\n;&|(])\\\\s*gog\\\\s+gmail\\\\s+(send|reply)\\\\b",
      "message": "BLOCKED: raw `gog gmail send/reply` bypasses {{AGENT_NAME}}'s HTML wrapper and thread_id capture. Send via bin/{{AGENT_SLUG}}-email (the shared canopy email engine) instead — write the body to a file and pass --body-file."
    },
    {
      "tool": "Bash",
      "pattern": "canopy\\\\s+email\\\\s+send\\\\b(?=[^\\\\n]*--account)",
      "message": "BLOCKED: `canopy email send --account` overrides {{AGENT_NAME}}'s repo identity — one mailbox + one client per agent (identity bleed is the fleet's one hard rule). Send via bin/{{AGENT_SLUG}}-email, which pins this repo's identity."
    }
  ],
  "approve": []
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

## Invariants are hooks, not memory — and rails, not approval gates
Hard behavioral rules do NOT belong in prose alone — prose relies on the model choosing to
comply, which fails under load. Encode each as **enforcement**: a `deny` rule in
`config/gating.json` that `hooks/gating_guard.py` turns into a hard block naming the right
path (e.g. raw `gog gmail send` → `bin/{{AGENT_SLUG}}-email`). Keep the `approve` list EMPTY:
a PreToolUse "ask" is a blocking modal that stalls autonomous work — approval semantics live
in the turn checklist (Step 2's "present for approval"), not in hooks. See the operating
model's §1a revision (rails, not gates). Add a new outbound action? Add a deny rail pointing
at its one sanctioned path — do not just write a sentence here.

## Doing a turn — load the procedure, don't improvise
"Do a turn" / "check your inbox" = the `skills/turn` procedure. **Re-read `skills/turn/SKILL.md`
at the start of every turn and follow it in order.** Running a turn from memory is exactly how
steps get dropped under load.

## Canopy is installed alongside this agent
{{AGENT_NAME}} runs with the **canopy plugin + CLI** available. Shared infra lives in canopy, not
here: the gating *engine*, channel adapters, the canopy-web client (`canopy agent-publish`), and
the fleet self-improvement loop. This repo holds only what is {{AGENT_NAME}}-specific — persona,
domain skills, gating *rules* (`config/gating.json`), allowlist, secrets. When something is pure
infra you'd want every agent to get, it belongs in canopy; raise it there, don't fork it here.
{{AGENT_NAME}}'s web workspace is `/agents/{{AGENT_SLUG}}` on canopy-web.

## Conventions
- Capability logic belongs in CLIs / MCP tools; skills (`SKILL.md`) orchestrate. That keeps the
  agent portable to the Claude Agent SDK later (MCP is the portability boundary).
- Config/secrets live in a WORKTREE-CLEAN global home `~/.{{AGENT_SLUG}}/.env`, provisioned by
  `canopy provision` from `config/secrets.yaml` (1Password refs + non-secret literals). NOT a
  per-worktree repo `.env` (that gets recreated every turn). Scripts read it via `bin/_env.py`.
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
outbound action waits for explicit human approval.** Approval is PROCEDURAL — the gating hook
carries deny rails only (it blocks wrong paths, it does not ask for you), so drafting-then-asking
in Step 2 is the gate. There is no modal to catch you if you skip it.

**Narrate as you go.** Before any multi-step or multi-repo investigation, state the plan in one
sentence first ("checking threads A and B for X — back shortly"), then work, then report what you
found. Never let a long silent stretch of tool calls build up — a human interrupting with "what
are you doing?" means the turn's communication already failed.

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

**Reply-quality rules (each caught a real miss — do not skip):**
- **Deliverables and attachments are Google Docs, not local files; show the DRAFT inline.** A
  substantial artifact (a script, a report, a plan) goes in a shared gdoc and the reply links it;
  it does NOT get pasted as a wall of text into the email body, and it is NOT stashed in a local
  `.txt` you point the human at. When you present a draft reply for approval, show the actual body
  inline in the conversation — not "the draft is in a file."
- **Decide-then-show, in one coherent order.** Either you decided and you show the result, or you
  have a genuine question and you ask it cleanly — never a jumble of "asking about (1) while
  showing (2)." Number your asks/items and keep the order consistent between what you ask and what
  you present. Don't manufacture a decision out of a thread you've already classified as not
  actionable.
- **Verify recipients before sending.** Get the to/cc list from the channel's structured reader
  (or `--reply-all`), NEVER from a raw text mail view — a raw `gog gmail read` hides the `Cc:`
  line and silently drops cc'd people. Confirm reply-all vs. direct deliberately.

**Email goes out ONLY via `bin/{{AGENT_SLUG}}-email`** (the shared canopy engine — HTML wrapper,
reply threading; a deny rail blocks raw `gog gmail send`). Every send returns JSON with
`thread_id` — **record it in {{AGENT_NAME}}'s state layer** so inbound triage can route the
reply to the right scope. Auth flaky? `canopy email preflight --repo .` prints the exact fix.

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

Then refresh {{AGENT_NAME}}'s canopy-web workspace so `/agents/{{AGENT_SLUG}}` reflects this turn
(the installed canopy plugin provides the shared client — no per-agent client to maintain):
```
canopy agent skills        # mirror the skill catalog (registers the agent if new)
```
If this turn produced a shareable deliverable, also `canopy agent work <items.json>`. The board at
`/agents/{{AGENT_SLUG}}` is the shared trigger + approval surface — where teammates queue work and
approve outbound actions.

Then **package this turn** as a unit of work so `/agents/{{AGENT_SLUG}}` records what you did and
ties it to the request(s) you advanced:
```
canopy agent turn --slug {{AGENT_SLUG}} --title "<what this turn did>" \
  --task <ext_id> [--task <ext_id> …]      # the board task(s) this turn advanced
  # --work-product-url <url> per deliverable produced this turn
```
**Optional transcript link (ASK FIRST):** uploading the transcript publishes to canopy-web — an
outbound action — so it rides the same approval gate as a send. Only if the human says yes, append
`--upload` (reduces THIS session to conversation-only, then hangs a `/share/<token>` link off the
turn). Put that link in your close-out summary. Without `--upload`, the turn is still packaged
(request → what you did → deliverables), just with no transcript.

**CLOSE CHECKLIST — confirm each in the summary (these get silently skipped under load):**
1. `self-review` ran on every outbound reply (Step 2).
2. Skill-development self-check answered (Step 3).
3. Workspace refreshed (`canopy agent skills` above).
4. Turn packaged (`canopy agent turn …`); transcript uploaded ONLY if the human approved.

**Shipping a skill change from a worktree** — emdash runs each turn in a worktree while `main` is
checked out elsewhere, so `git checkout main` and `gh pr merge --delete-branch` FAIL ("main already
checked out"). Instead: `gh pr merge <n> --squash`, then verify with `gh pr view <n> --json state`.

## Related skills
- `self-review` — gate every outbound reply against the original request before sending.
- canopy plugin (installed alongside this agent) — `create-agent`, `agent-publish`, `improve`, and
  the fleet self-improvement loop. {{AGENT_NAME}} has canopy's skills available; use them.
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
7. **Deliverables are gdocs; the draft is inline.** Any substantial artifact goes in a shared
   Google Doc the reply links — never pasted as a wall of text, never left in a local file. Present
   the reply body itself inline for approval, not a pointer to where it lives.
8. **Verify recipients.** Pull to/cc from the structured reader (or `--reply-all`), never a raw
   text mail view (it hides `Cc:`). Confirm reply-all vs. direct on purpose.
'''

_SECRETS_YAML = '''# {{AGENT_NAME}}'s secrets + config, declarative. `canopy provision` materializes these from the
# 1Password AI-Agents vault into the WORKTREE-CLEAN global home ~/.{{AGENT_SLUG}}/.env — NOT a
# per-worktree repo .env. emdash runs each turn in a fresh worktree; a repo .env would be absent
# there and get recreated every turn, so it lives ONCE in the global home and every worktree reads
# it (via bin/_env.py). No values here — only 1Password refs (`op:`) and non-secret literals
# (`value:`). Provision with `canopy provision` (or `--check` to dry-run) from this repo.
env:
  target: "~/.{{AGENT_SLUG}}/.env"
  mode: "0600"
  vars:
    - key: {{AGENT_SLUG}}_PRIMARY_CHANNEL
      value: "{{MAILBOX}}"                                   # not a secret — the agent's channel
    # - key: {{AGENT_SLUG}}_SOME_SECRET
    #   op: "op://AI-Agents/{{AGENT_NAME}} item/field"       # a real secret — resolved from 1Password
    # - key: CANOPY_WEB_PAT
    #   op: "op://AI-Agents/{{AGENT_NAME}} canopy-web PAT/credential"
    #   optional: true
'''

_ENV_LOADER = '''"""Canonical .env resolver for {{AGENT_NAME}}'s scripts — reads the WORKTREE-CLEAN global home.

{{AGENT_NAME}} runs each turn in a fresh emdash worktree; a per-repo `.env` would be absent there and
get recreated every turn. So secrets live ONCE at ~/.{{AGENT_SLUG}}/.env (provisioned by
`canopy provision` from config/secrets.yaml; override the home with ${{AGENT_SLUG}}_ENV, upper-cased).
A repo-local `.env` still works as a per-KEY dev override (it wins).

    from _env import get, load
    val = get("{{AGENT_SLUG}}_PRIMARY_CHANNEL", "")   # os.environ wins, then global .env, then default

Never `source` the .env from bash — values with `>`/`!`/`=` break shell parsing; use this module.
"""
import os

_SLUG = "{{AGENT_SLUG}}"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GLOBAL_ENV = os.environ.get(_SLUG.upper() + "_ENV") or os.path.expanduser("~/." + _SLUG + "/.env")
REPO_ENV = os.path.join(REPO, ".env")
ENV_PATH = GLOBAL_ENV


def load(path=None):
    """Parse .env(s) into a dict — global home merged with an optional repo-local override (repo
    wins per key). Splits on the FIRST '=', value verbatim (so `>`/`!`/`=`/spaces survive)."""
    out = {}
    for p in ([path] if path else [GLOBAL_ENV, REPO_ENV]):
        if not p or not os.path.exists(p):
            continue
        for raw in open(p):
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                v = v[1:-1]
            out[k] = v
    return out


def get(key, default=None):
    """Resolve one var: os.environ first (caller override), then the .env home, else default."""
    if os.environ.get(key):
        return os.environ[key].strip()
    return load().get(key, default)
'''

_EMAIL_SHIM = '''#!/usr/bin/env python3
"""{{AGENT_NAME}}'s ONLY email send path — a thin shim over the shared canopy email engine.

The HTML wrapper (Gmail display-wraps plain text at ~72 cols; HTML reflows), reply
threading, and identity resolution all live in canopy (`canopy email send`), so fixes
propagate fleet-wide. This shim only pins --repo so identity comes from THIS repo's
config/agent.json (`email` + `gog_client`). The deny rail in config/gating.json blocks
raw `gog gmail send/reply`, so email leaves {{AGENT_NAME}} only through here.

SEND-SIDE CONTRACT: every successful send prints JSON with message_id + thread_id —
record thread_id into {{AGENT_NAME}}'s state layer so inbound triage can route the reply.

Usage:
  bin/{{AGENT_SLUG}}-email --to "a@x,b@y" [--cc "c@z"] --subject "Re: ..." \\
      --body-file body.txt [--reply-to-message-id <id>] [--reply-all] [--dry-run]

Auth check: `canopy email preflight --repo <this repo>` (exact `gog login` fix on failure).
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    os.execvp("canopy", ["canopy", "email", "send", "--repo", REPO, *sys.argv[1:]])
except FileNotFoundError:
    sys.exit(
        "canopy CLI not on PATH — the shared email engine lives there.\\n"
        "Install it (`uv tool install canopy`) or run from a canopy checkout: "
        "`uv run canopy email send --repo <this repo> ...`"
    )
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
- **Reads free, writes gated — rails, not gates:** `hooks/gating_guard.py` reads
  `config/gating.json` and hard-blocks wrong paths (`deny` rails that name the right path) at
  the tool-call boundary. Approval is procedural — the turn checklist's explicit
  draft-then-ask step — never a blocking hook modal (`approve` stays empty by default).
- **Email channel:** `bin/{{AGENT_SLUG}}-email` — a thin shim over the shared `canopy email`
  engine; identity from `config/agent.json`. Raw `gog gmail send` is deny-railed.

## Run a turn
In Claude Code, from this repo: "do a turn". {{AGENT_NAME}} re-reads `skills/turn/SKILL.md` and
follows it: preflight → process inbound (one counterpart at a time) → skill self-check → close.

## Make it yours
1. Fill in `persona.md` (voice, mandate detail, memory scope).
2. Add domain skills under `skills/<name>/SKILL.md`.
3. Add each outbound action as a `deny` rail in `config/gating.json` pointing at its one
   sanctioned path — not as prose, and not as an `approve` rule (approval is the turn
   checklist's job; hook modals stall autonomous work).
4. Declare secrets in `config/secrets.yaml` (1Password refs) and run `canopy provision` — they land
   in the worktree-clean global home `~/.{{AGENT_SLUG}}/.env`, read by `bin/_env.py`.
5. Mint the agent's own gog identity (mailbox + OAuth client named `{{AGENT_SLUG}}`), then
   `gog login {{MAILBOX}} --client {{AGENT_SLUG}} --services gmail,drive,docs,sheets,forms`.
   Verify with `canopy email preflight --repo .`; send via `bin/{{AGENT_SLUG}}-email`.
'''

_GITIGNORE = '''.env
__pycache__/
*.pyc
.DS_Store
'''

_AGENT_JSON = '''{
  "_doc": "{{AGENT_NAME}}'s identity for its canopy-web workspace (/agents/{{AGENT_SLUG}}) and for the shared email engine (`canopy email` resolves mailbox + gog client from here). Read by `canopy agent-publish`. slug + description come from .claude-plugin/plugin.json; these override/extend. gog_client is {{AGENT_NAME}}'s OWN gog OAuth client name — never another agent's (identity bleed is the fleet's one hard rule).",
  "name": "{{AGENT_NAME}}",
  "email": "{{MAILBOX}}",
  "gog_client": "{{AGENT_SLUG}}",
  "persona": "{{MANDATE}}",
  "avatar_url": ""
}
'''

_TEMPLATES: dict[str, str] = {
    ".claude-plugin/plugin.json": _PLUGIN_JSON,
    "CLAUDE.md": _CLAUDE_MD,
    "persona.md": _PERSONA_MD,
    "README.md": _README,
    ".gitignore": _GITIGNORE,
    "config/secrets.yaml": _SECRETS_YAML,
    "bin/_env.py": _ENV_LOADER,
    "bin/{{AGENT_SLUG}}-email": _EMAIL_SHIM,
    "config/gating.json": _GATING_JSON,
    "config/allowlist.txt": _ALLOWLIST,
    "config/agent.json": _AGENT_JSON,
    ".claude/settings.json": _SETTINGS_JSON,
    "hooks/gating_guard.py": _GATING_GUARD,
    "skills/turn/SKILL.md": _TURN_SKILL,
    "skills/self-review/SKILL.md": _SELF_REVIEW_SKILL,
}
