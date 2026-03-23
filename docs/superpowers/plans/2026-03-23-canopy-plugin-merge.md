# Canopy Plugin Merge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge canopy-skills into canopy-orchestrator, rename the package to canopy, and expose orchestrator capabilities as Claude Code skills via proper plugin scaffolding.

**Architecture:** The repo becomes a Claude Code plugin marketplace (Pattern A) with `plugins/canopy/` containing skills, commands, and agents. The Python engine stays at `src/orchestrator/`. The CLI entry point changes from `orchestrator` to `canopy`.

**Tech Stack:** Python 3.11+, Click, PyYAML, Claude Code plugin system (marketplace.json, plugin.json, SKILL.md, commands/*.md, agents/*.md)

**Spec:** `docs/superpowers/specs/2026-03-23-canopy-plugin-merge-design.md`

---

### Task 1: Rename package and CLI entry point

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/orchestrator/cli.py:25-27`

- [ ] **Step 1: Update pyproject.toml**

Change the package name and script entry point:

```toml
[project]
name = "canopy"
```

```toml
[project.scripts]
canopy = "orchestrator.cli:main"
```

Remove the old `orchestrator` entry point. Keep everything else the same.

- [ ] **Step 2: Update cli.py docstring**

Change the main group docstring from:
```python
"""Orchestrator — self-improving MCP orchestration."""
```
to:
```python
"""Canopy — self-improving MCP orchestration."""
```

- [ ] **Step 3: Verify the rename works**

Run: `uv run canopy --help`
Expected: Shows "Canopy — self-improving MCP orchestration." and all existing subcommands.

Run: `uv run canopy registry show`
Expected: Shows registry summary (same as before).

- [ ] **Step 4: Run all tests**

Run: `uv run pytest -x -q`
Expected: All tests pass. Tests import `orchestrator.cli` directly so the package rename doesn't break them.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/orchestrator/cli.py
git commit -m "feat: rename package to canopy, CLI entry point orchestrator → canopy"
```

---

### Task 2: Create plugin scaffolding

**Files:**
- Create: `.claude-plugin/marketplace.json`
- Create: `plugins/canopy/.claude-plugin/plugin.json`

- [ ] **Step 1: Create marketplace.json**

Create `.claude-plugin/marketplace.json`:

```json
{
  "name": "canopy",
  "description": "Self-improving AI orchestration — watches sessions, identifies gaps, builds improvements",
  "owner": {
    "name": "Jonathan Jackson",
    "url": "https://github.com/jjackson"
  },
  "metadata": {
    "version": "0.1.0"
  },
  "plugins": [
    {
      "name": "canopy",
      "source": "./plugins/canopy",
      "version": "0.1.0",
      "description": "Self-improving AI workflow skills — session analysis, PM supervision, autonomous development"
    }
  ]
}
```

- [ ] **Step 2: Create plugin.json**

Create `plugins/canopy/.claude-plugin/plugin.json`:

```json
{
  "name": "canopy",
  "description": "Self-improving AI workflow skills — session analysis, improvement cycles, PM supervision, and learning loops",
  "author": {
    "name": "Jonathan Jackson",
    "email": "jjackson@github.com"
  },
  "repository": "https://github.com/jjackson/canopy",
  "license": "MIT",
  "keywords": ["orchestration", "self-improving", "pm", "autonomous", "sessions"]
}
```

- [ ] **Step 3: Verify directory structure**

Run: `find .claude-plugin plugins -type f | sort`
Expected:
```
.claude-plugin/marketplace.json
plugins/canopy/.claude-plugin/plugin.json
```

- [ ] **Step 4: Commit**

```bash
git add .claude-plugin/ plugins/
git commit -m "feat: add Claude Code plugin scaffolding (marketplace pattern)"
```

---

### Task 3: Move canopy-skills content into plugin

**Files:**
- Create: `plugins/canopy/skills/product-management/SKILL.md`
- Create: `plugins/canopy/skills/product-management/templates/scout.md`
- Create: `plugins/canopy/skills/product-management/templates/implement.md`
- Create: `plugins/canopy/skills/doc-regeneration/SKILL.md`
- Create: `plugins/canopy/commands/pm-scout.md`
- Create: `plugins/canopy/commands/pm-status.md`
- Create: `plugins/canopy/commands/doc-regen.md`
- Create: `plugins/canopy/agents/pm-supervisor.md`

- [ ] **Step 1: Copy skills from canopy-skills plugin**

Copy verbatim from `~/.claude/plugins/marketplaces/canopy-skills/plugins/canopy/`:
- `skills/product-management/SKILL.md` and `templates/`
- `skills/doc-regeneration/SKILL.md`
- `commands/pm-scout.md`, `pm-status.md`, `doc-regen.md`
- `agents/pm-supervisor.md`

```bash
# Skills
mkdir -p plugins/canopy/skills/product-management/templates
cp ~/.claude/plugins/marketplaces/canopy-skills/plugins/canopy/skills/product-management/SKILL.md plugins/canopy/skills/product-management/
cp ~/.claude/plugins/marketplaces/canopy-skills/plugins/canopy/skills/product-management/templates/scout.md plugins/canopy/skills/product-management/templates/
cp ~/.claude/plugins/marketplaces/canopy-skills/plugins/canopy/skills/product-management/templates/implement.md plugins/canopy/skills/product-management/templates/
mkdir -p plugins/canopy/skills/doc-regeneration
cp ~/.claude/plugins/marketplaces/canopy-skills/plugins/canopy/skills/doc-regeneration/SKILL.md plugins/canopy/skills/doc-regeneration/

# Commands
mkdir -p plugins/canopy/commands
cp ~/.claude/plugins/marketplaces/canopy-skills/plugins/canopy/commands/pm-scout.md plugins/canopy/commands/
cp ~/.claude/plugins/marketplaces/canopy-skills/plugins/canopy/commands/pm-status.md plugins/canopy/commands/
cp ~/.claude/plugins/marketplaces/canopy-skills/plugins/canopy/commands/doc-regen.md plugins/canopy/commands/

# Agents
mkdir -p plugins/canopy/agents
cp ~/.claude/plugins/marketplaces/canopy-skills/plugins/canopy/agents/pm-supervisor.md plugins/canopy/agents/
```

- [ ] **Step 2: Update references in copied files**

In `plugins/canopy/skills/product-management/SKILL.md`, update all 3 occurrences of `canopy-skills`:
- "Propose a PR to `jjackson/canopy-skills`" → `jjackson/canopy`
- "Clone `jjackson/canopy-skills` to a temp directory" → `jjackson/canopy`
- "Open PR to `jjackson/canopy-skills` (NOT the current project repo)" → `jjackson/canopy`

In `plugins/canopy/agents/pm-supervisor.md`, update 1 occurrence:
- "create a PR to `jjackson/canopy-skills`" → `jjackson/canopy`

The relative path `plugins/canopy/skills/product-management/SKILL.md` in the self-improvement section stays the same.

No `uv run orchestrator` references exist in these files (they delegate to skills, not CLI commands), so no CLI rename needed here.

**Note:** The canopy-skills marketplace also has a `select-session` skill. We use the repo-local version as canonical (Task 4) and do NOT copy the canopy-skills version here.

- [ ] **Step 3: Verify all files exist**

Run: `find plugins/canopy -type f | sort`
Expected:
```
plugins/canopy/.claude-plugin/plugin.json
plugins/canopy/agents/pm-supervisor.md
plugins/canopy/commands/doc-regen.md
plugins/canopy/commands/pm-scout.md
plugins/canopy/commands/pm-status.md
plugins/canopy/skills/doc-regeneration/SKILL.md
plugins/canopy/skills/product-management/SKILL.md
plugins/canopy/skills/product-management/templates/implement.md
plugins/canopy/skills/product-management/templates/scout.md
```

- [ ] **Step 4: Commit**

```bash
git add plugins/canopy/
git commit -m "feat: move canopy-skills content into plugin (skills, commands, agents)"
```

---

### Task 4: Move repo-local skills into plugin

**Files:**
- Move: `skills/orchestrator/SKILL.md` → `plugins/canopy/skills/orchestrator/SKILL.md`
- Move: `skills/select-session/SKILL.md` → `plugins/canopy/skills/select-session/SKILL.md`
- Delete: `skills/` directory

- [ ] **Step 1: Move and update orchestrator skill**

```bash
mkdir -p plugins/canopy/skills/orchestrator
cp skills/orchestrator/SKILL.md plugins/canopy/skills/orchestrator/SKILL.md
```

In `plugins/canopy/skills/orchestrator/SKILL.md`, update:
- `~/emdash-projects/canopy-orchestrator/registry.yaml` → `~/emdash-projects/canopy-orchestrator/registry.yaml` (keep as-is — the repo directory won't rename until GitHub rename, per spec transition plan)

- [ ] **Step 2: Move and update select-session skill**

```bash
mkdir -p plugins/canopy/skills/select-session
cp skills/select-session/SKILL.md plugins/canopy/skills/select-session/SKILL.md
```

In `plugins/canopy/skills/select-session/SKILL.md`, update all occurrences of:
- `uv run orchestrator` → `uv run canopy`
- `~/emdash-projects/canopy-orchestrator` → keep as-is (transition path — directory hasn't renamed yet)

- [ ] **Step 3: Delete old skills directory**

```bash
rm -rf skills/
```

- [ ] **Step 4: Verify**

Run: `find plugins/canopy/skills -name "SKILL.md" | sort`
Expected: Should now include `orchestrator/SKILL.md` and `select-session/SKILL.md`.

Run: `test -d skills && echo "ERROR: old skills dir still exists" || echo "OK: old skills dir removed"`
Expected: "OK: old skills dir removed"

- [ ] **Step 5: Commit**

```bash
git add plugins/canopy/skills/orchestrator/ plugins/canopy/skills/select-session/
git rm -r skills/
git commit -m "feat: move orchestrator and select-session skills into plugin"
```

---

### Task 5: Add `canopy brief` CLI command

**Files:**
- Modify: `src/orchestrator/cli.py`
- Create: `tests/test_cli_brief.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_brief.py`:

```python
"""Tests for the canopy brief CLI command."""
from unittest.mock import patch
from click.testing import CliRunner
from orchestrator.cli import main


class TestBriefCommand:
    def test_exit_code_zero(self):
        runner = CliRunner()
        with patch("orchestrator.briefing.generate_brief", return_value="# Strategic Brief\n\nAll clear."):
            result = runner.invoke(main, ["brief"])
        assert result.exit_code == 0

    def test_outputs_brief_content(self):
        runner = CliRunner()
        brief_text = "# Strategic Brief\n\nPattern: recurring friction in connect-search."
        with patch("orchestrator.briefing.generate_brief", return_value=brief_text):
            result = runner.invoke(main, ["brief"])
        assert "recurring friction" in result.output

    def test_passes_model_option(self):
        runner = CliRunner()
        with patch("orchestrator.briefing.generate_brief", return_value="brief") as mock:
            runner.invoke(main, ["brief", "--model", "opus"])
        mock.assert_called_once()
        assert mock.call_args[1]["model"] == "opus"

    def test_passes_budget_option(self):
        runner = CliRunner()
        with patch("orchestrator.briefing.generate_brief", return_value="brief") as mock:
            runner.invoke(main, ["brief", "--budget", "2.0"])
        mock.assert_called_once()
        assert mock.call_args[1]["max_budget_usd"] == 2.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_brief.py -v`
Expected: FAIL — `brief` command doesn't exist yet.

- [ ] **Step 3: Implement the brief command**

Add to `src/orchestrator/cli.py`, after the `serve` command and before `_validate_proposals`:

```python
@main.command("brief")
@click.option("--model", default="sonnet", help="Model to use for brief generation")
@click.option("--budget", default=1.0, type=float, help="Max USD per claude -p call")
def brief(model, budget):
    """Generate a strategic brief from recent activity."""
    from orchestrator.briefing import generate_brief

    state_dir = Path.home() / ".claude" / "orchestrator"
    state_dir.mkdir(parents=True, exist_ok=True)

    # brief can run without registry (falls back to simple digest), unlike improve which requires it
    try:
        registry_path = find_registry()
    except click.ClickException:
        registry_path = None

    click.echo(generate_brief(
        state_dir=state_dir,
        registry_path=registry_path,
        model=model,
        max_budget_usd=budget,
    ))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_brief.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add src/orchestrator/cli.py tests/test_cli_brief.py
git commit -m "feat: add canopy brief CLI command"
```

---

### Task 6: Add `canopy patterns` CLI command

**Files:**
- Modify: `src/orchestrator/cli.py`
- Create: `tests/test_cli_patterns.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_patterns.py`:

```python
"""Tests for the canopy patterns CLI command."""
import json
from unittest.mock import patch
from click.testing import CliRunner
from orchestrator.cli import main


SAMPLE_PATTERNS = [
    {
        "type": "recurring_issue",
        "issue_type": "gap",
        "related_servers": ["connect-search"],
        "observation_count": 3,
        "total_frequency": 7,
        "unique_sessions": 5,
        "descriptions": ["Missing tool for X", "No way to Y"],
        "severity": "high",
        "actionable": True,
    },
    {
        "type": "project_hotspot",
        "server": "connect-search",
        "issue_count": 4,
        "high_severity_count": 2,
        "actionable": True,
    },
]


class TestPatternsCommand:
    def test_exit_code_zero(self):
        runner = CliRunner()
        with patch("orchestrator.patterns.detect_patterns", return_value=[]):
            result = runner.invoke(main, ["patterns"])
        assert result.exit_code == 0

    def test_no_patterns_message(self):
        runner = CliRunner()
        with patch("orchestrator.patterns.detect_patterns", return_value=[]):
            result = runner.invoke(main, ["patterns"])
        assert "No patterns" in result.output

    def test_shows_recurring_issues(self):
        runner = CliRunner()
        with patch("orchestrator.patterns.detect_patterns", return_value=SAMPLE_PATTERNS):
            result = runner.invoke(main, ["patterns"])
        assert "connect-search" in result.output
        assert "recurring" in result.output.lower() or "gap" in result.output.lower()

    def test_json_output(self):
        runner = CliRunner()
        with patch("orchestrator.patterns.detect_patterns", return_value=SAMPLE_PATTERNS):
            result = runner.invoke(main, ["patterns", "--json-output"])
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["type"] == "recurring_issue"

    def test_shows_hotspots(self):
        runner = CliRunner()
        with patch("orchestrator.patterns.detect_patterns", return_value=SAMPLE_PATTERNS):
            result = runner.invoke(main, ["patterns"])
        assert "hotspot" in result.output.lower() or "connect-search" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_patterns.py -v`
Expected: FAIL — `patterns` command doesn't exist yet.

- [ ] **Step 3: Implement the patterns command**

Add to `src/orchestrator/cli.py`, after the `brief` command:

```python
@main.command("patterns")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def patterns_cmd(as_json):
    """Show cross-session friction patterns."""
    import json as json_mod
    from orchestrator.patterns import detect_patterns

    state_dir = Path.home() / ".claude" / "orchestrator"
    state_dir.mkdir(parents=True, exist_ok=True)
    obs_dir = state_dir / "observations"

    results = detect_patterns(obs_dir)

    if as_json:
        click.echo(json_mod.dumps(results, indent=2, default=str))
        return

    if not results:
        click.echo("No patterns detected. Run `canopy improve` to analyze sessions first.")
        return

    recurring = [p for p in results if p["type"] == "recurring_issue"]
    hotspots = [p for p in results if p["type"] == "project_hotspot"]

    if recurring:
        click.echo("Recurring Issues:\n")
        for p in recurring:
            servers = ", ".join(p["related_servers"]) if p["related_servers"] else "general"
            click.echo(f"  [{p['severity']}] {p['issue_type']} — {servers}")
            click.echo(f"    Seen {p['total_frequency']}x across {p['unique_sessions']} sessions ({p['observation_count']} observations)")
            for desc in p.get("descriptions", [])[:2]:
                click.echo(f"    - {desc[:80]}")
            click.echo()

    if hotspots:
        click.echo("Project Hotspots:\n")
        for p in hotspots:
            high = f" ({p['high_severity_count']} high)" if p["high_severity_count"] else ""
            click.echo(f"  {p['server']}: {p['issue_count']} issues{high}")
        click.echo()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_patterns.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add src/orchestrator/cli.py tests/test_cli_patterns.py
git commit -m "feat: add canopy patterns CLI command"
```

---

### Task 7: Create new skills and commands

**Files:**
- Create: `plugins/canopy/skills/improve/SKILL.md`
- Create: `plugins/canopy/skills/brief/SKILL.md`
- Create: `plugins/canopy/skills/patterns/SKILL.md`
- Create: `plugins/canopy/commands/improve.md`
- Create: `plugins/canopy/commands/brief.md`
- Create: `plugins/canopy/commands/patterns.md`

- [ ] **Step 1: Create improve skill**

Create `plugins/canopy/skills/improve/SKILL.md`:

```markdown
---
name: improve
description: Run a full canopy improvement cycle — analyze recent sessions, propose improvements, and optionally implement them
version: 0.1.0
---

# Improve

Runs the canopy improvement pipeline on recent Claude Code sessions.

## Arguments

- No args: full cycle (analyze + propose + implement)
- `observe`: analyze only, no proposals
- `dry-run`: analyze + propose, no implementation

## Flow

1. Run the appropriate command from the canopy repo working directory:

```bash
# Full cycle
uv run canopy improve

# Observe only
uv run canopy improve --observe-only

# Dry run
uv run canopy improve --dry-run
```

2. Show progress as it runs (the command streams output)
3. Display the results summary: transcripts analyzed, observations created, proposals generated, implementations completed

## Rules

- Always use `uv run` to invoke the canopy CLI
- The working directory is the canopy repo (wherever `pyproject.toml` with `name = "canopy"` is)
- The command may take several minutes — it invokes `claude -p` for analysis and proposal generation
- If the circuit breaker trips (too many consecutive failures), the command will report this
```

- [ ] **Step 2: Create brief skill**

Create `plugins/canopy/skills/brief/SKILL.md`:

```markdown
---
name: brief
description: Generate a strategic brief from recent canopy activity — patterns, success rates, and improvement opportunities
version: 0.1.0
---

# Brief

Generates a CEO-level strategic brief from recent orchestrator activity. Applies inversion reflex, leverage obsession, and focus-as-subtraction to the pipeline's data.

## Flow

1. Run from the canopy repo working directory:

```bash
uv run canopy brief
```

2. Display the markdown output to the user

## Options

- `--model MODEL`: Model to use (default: sonnet)
- `--budget BUDGET`: Max USD per claude -p call (default: 1.0)

## Rules

- The command invokes `claude -p` internally — may take 30-60 seconds
- If `claude -p` fails, it falls back to a simple digest from local data
- The brief draws from: recent run logs, detected patterns, pending observations, and proposal success rates
```

- [ ] **Step 3: Create patterns skill**

Create `plugins/canopy/skills/patterns/SKILL.md`:

```markdown
---
name: patterns
description: Show cross-session friction patterns — recurring issues and project hotspots detected across Claude Code sessions
version: 0.1.0
---

# Patterns

Shows aggregated patterns from session analysis — recurring issues ranked by frequency and project hotspots by issue count.

## Flow

1. Run from the canopy repo working directory:

```bash
uv run canopy patterns
```

2. Display the output showing:
   - Recurring issues: grouped by type and related servers, ranked by total frequency
   - Project hotspots: servers with the most issues, flagging high-severity concentrations

## Options

- `--json-output`: Output as JSON for programmatic consumption

## Rules

- This reads from `~/.claude/orchestrator/observations/` — requires running `canopy improve` at least once first
- If no patterns are detected, suggest running `canopy improve` to populate observations
```

- [ ] **Step 4: Create improve command**

Create `plugins/canopy/commands/improve.md`:

```markdown
---
description: Run a full canopy improvement cycle — analyze sessions, propose and implement improvements
argument-hint: [observe|dry-run]
allowed-tools: [Read, Bash, Write, Edit, Agent]
---

# Improve

Run a canopy improvement cycle on recent Claude Code sessions.

## Arguments

- No args: full cycle (analyze + propose + implement)
- `observe`: analyze only
- `dry-run`: analyze + propose, skip implementation

## Process

1. Invoke the `improve` skill
2. Run the appropriate `uv run canopy improve` command
3. Display results
```

- [ ] **Step 5: Create brief command**

Create `plugins/canopy/commands/brief.md`:

```markdown
---
description: Generate a strategic brief from recent canopy activity
allowed-tools: [Read, Bash]
---

# Brief

Generate a strategic brief from recent orchestrator activity.

## Process

1. Invoke the `brief` skill
2. Run `uv run canopy brief`
3. Display the markdown output
```

- [ ] **Step 6: Create patterns command**

Create `plugins/canopy/commands/patterns.md`:

```markdown
---
description: Show cross-session friction patterns — recurring issues and project hotspots
allowed-tools: [Read, Bash]
---

# Patterns

Show cross-session friction patterns.

## Process

1. Invoke the `patterns` skill
2. Run `uv run canopy patterns`
3. Display the output
```

- [ ] **Step 7: Verify all plugin files exist**

Run: `find plugins/canopy -type f | sort`
Expected: All 16 files present (plugin.json + 7 skills + 6 commands + 1 agent + 2 templates).

- [ ] **Step 8: Commit**

```bash
git add plugins/canopy/skills/improve/ plugins/canopy/skills/brief/ plugins/canopy/skills/patterns/
git add plugins/canopy/commands/improve.md plugins/canopy/commands/brief.md plugins/canopy/commands/patterns.md
git commit -m "feat: add improve, brief, and patterns skills and commands"
```

---

### Task 8: Update CLAUDE.md

**Files:**
- Modify: `.claude/CLAUDE.md`

- [ ] **Step 1: Update all references**

In `.claude/CLAUDE.md`, make these changes:
- Title: "Canopy Orchestrator" → "Canopy"
- Description: update to mention it's a Claude Code plugin
- Git worktree paths: keep `canopy-orchestrator` (won't rename until GitHub rename)
- All `orchestrator` CLI references → `canopy` (e.g., `canopy registry show`, `canopy improve`, etc.)
- Testing section: `uv run pytest` stays the same
- Add note about plugin structure under Key Modules

- [ ] **Step 2: Verify CLAUDE.md has no stale `orchestrator` CLI references**

Run: `grep -n 'orchestrator ' .claude/CLAUDE.md | grep -v 'src/orchestrator' | grep -v 'canopy-orchestrator'`
Expected: No matches (all CLI references should now say `canopy`).

- [ ] **Step 3: Commit**

```bash
git add .claude/CLAUDE.md
git commit -m "docs: update CLAUDE.md — rename orchestrator CLI refs to canopy, add plugin structure"
```

---

### Task 9: Run full test suite and verify

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass (should be 411+ with the new test files).

- [ ] **Step 2: Verify canopy CLI**

Run: `uv run canopy --help`
Expected: Shows all commands including `brief` and `patterns`.

Run: `uv run canopy brief --help`
Expected: Shows brief command help.

Run: `uv run canopy patterns --help`
Expected: Shows patterns command help.

Run: `uv run canopy sessions list --hours 1`
Expected: Lists recent sessions (same output as before, just invoked via `canopy` instead of `orchestrator`).

- [ ] **Step 3: Verify plugin structure**

Run: `find .claude-plugin plugins -type f | sort`
Expected: Complete marketplace.json + plugin.json + all skills/commands/agents.

Run: `cat .claude-plugin/marketplace.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['name'])"`
Expected: `canopy`

- [ ] **Step 4: Commit any fixes if needed**

If any tests or verifications failed, fix and commit.

---

### Task 10: Plugin registration and cleanup

**Files:** None (system configuration, not code)

This task is manual — the implementor should present these steps to the user for confirmation before executing, since they modify system-level Claude Code plugin configuration.

- [ ] **Step 1: Uninstall old canopy-skills plugin**

```bash
claude plugin uninstall canopy@canopy-skills
```

If this command doesn't exist or fails, manually edit:
- `~/.claude/plugins/installed_plugins.json` — remove the `canopy@canopy-skills` entry
- `~/.claude/plugins/known_marketplaces.json` — remove the `canopy-skills` entry

- [ ] **Step 2: Register new marketplace**

For local development (before GitHub rename):
```bash
claude plugin marketplace add --local ~/emdash-projects/canopy-orchestrator
```

Or manually edit `~/.claude/plugins/known_marketplaces.json` to add an entry pointing at the local repo.

- [ ] **Step 3: Install the plugin**

```bash
claude plugin install canopy@canopy
```

- [ ] **Step 4: Verify skills are discoverable**

Start a new Claude Code session and check:
- `/select-session` — should appear in autocomplete
- `/improve` — should appear
- `/brief` — should appear
- `/patterns` — should appear
- `/pm-scout` — should appear
- `/pm-status` — should appear
- `/doc-regen` — should appear

- [ ] **Step 5: Clean up old plugin cache**

```bash
rm -rf ~/.claude/plugins/marketplaces/canopy-skills
```

- [ ] **Step 6: Final commit — merge to main**

```bash
cd ~/emdash-projects/canopy-orchestrator && git pull --rebase && git merge emdash/new-session-selection-74y && git push
```
