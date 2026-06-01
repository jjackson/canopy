---
description: Triage a GitHub repo's open issues against the current code — recommend implement / investigate / close per issue, then act behind gates. Defaults to the current repo; pass owner/repo to point elsewhere.
argument-hint: "[owner/repo] [--limit N]"
allowed-tools: [Bash, Read, Glob, Grep, Agent, Write, Edit, AskUserQuestion]
---

# Issue Triage

Read the issue-triage SKILL.md from disk and follow it exactly:

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/issue-triage/SKILL.md')"
```

Read that file with the Read tool and follow it. The SKILL.md is the
authoritative procedure — **do NOT improvise from memory.**

## Arguments (pass through to the skill)

- `owner/repo` (optional) — the GitHub repo to triage. If omitted, the skill
  defaults to the current repo's `origin` (`gh repo view`).
- `--limit N` (optional) — cap the number of open issues triaged (default 30).

Whatever the user typed after the command is the target/limit. Substitute it
into the skill's Phase 0 `ARG` and Phase 1 `--limit`.
