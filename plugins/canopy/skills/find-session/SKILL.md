---
name: find-session
description: Use when you need to find your OTHER active Claude Code session on a repo — to pick up context from a parallel worktree, summarize what a sibling session is mid-work on, or seed a flow (DDD, PM) from work happening elsewhere. Targeted single-session lookup, NOT a multi-session audit (that's session-review) or a picker UI (that's select-session).
---

# Find Session

Targeted lookup for the recurring ask: **"find my other active session on repo
X and tell me what it's doing."** Common when you have a parallel worktree open
and this session needs to pick up context from it (e.g. running `/canopy:ddd`
on top of work happening in a sibling session).

Walks `~/.claude/projects/`, **excludes the current session**, ranks the rest by
recency, and prints a digest — worktree path, branch, recent commits, recent
human prompts, and uncommitted files — that you can act on without re-running
shell. Read-only.

## Process

1. Resolve the plugin path and run the helper:

   ```bash
   PLUGIN_PATH=$(python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); print(d['plugins']['canopy@canopy'][0]['installPath'])")
   python3 "$PLUGIN_PATH/skills/find-session/scripts/find_session.py" "<target>"
   ```

   - `<target>` — a repo-slug substring (`connect-labs`), or a worktree path,
     or **omit it entirely** to consider any recent session that isn't this one.
   - The current session is excluded automatically via `$CLAUDE_CODE_SESSION_ID`
     (the helper reads it from the environment). Do not pass `--exclude-session`
     unless that env var is missing.

2. **Read the digest to the user.** It is already formatted — worktree, session
   id + mtime, recent commits, dirty files, and the last human prompts from that
   session. Relay it; don't paraphrase the prompts away (they're the signal for
   what the other session is actually doing).

3. **If the helper flags ambiguity** (a `⚠️` line — multiple sessions active
   within ~5 minutes of the top candidate), and which one matters, ask the user
   to confirm rather than guessing. Otherwise the top candidate is the answer.

4. **If nothing is found,** widen the window (`--hours 168`) before concluding
   there's no sibling session — the default is 24h.

## Useful flags

Run the helper with `--help` for the full list. The ones you'll reach for:

| Flag | Default | Use |
|------|---------|-----|
| `--hours N` | 24 | recency window — widen to find older sessions |
| `--top N` | 1 | fully digest N candidates (rest become a one-line menu) |
| `--max-prompts N` | 20 | human prompts surfaced per digested candidate |
| `--commits N` | 8 | recent commits shown for digested candidates |
| `--json` | off | machine-readable output for composing this into another flow |

## Composability

Any "resume from a sibling session" flow can call this as its first step —
`/canopy:ddd`, `/canopy:product-management`, or a hand-driven handoff. Use
`--json` when you want to consume the result programmatically (each candidate
carries `cwd`, `branch`, `commits`, `dirty`, `prompts`, `transcript`).

## When NOT to use this skill

- **Multi-session audit / improvement proposals** → `/canopy:session-review`.
- **Browsing session history with a menu UI** → `/canopy:select-session`.
- **Cross-repo discovery** — the natural scope is "the other session on the
  repo I'm asking about." Omitting the target already lists everything recent;
  there's no separate cross-repo mode.
- **Inspecting *this* session** — it is deliberately excluded.
