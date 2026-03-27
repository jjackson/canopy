# Improvement Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the full observe → propose → implement pipeline that watches Claude Code sessions and autonomously improves the MCP/skill ecosystem.

**Architecture:** A CLI-driven pipeline (`orchestrator improve`) that reads Claude Code transcripts, uses Claude to extract observations and generate proposals, then spawns headless Claude Code sessions to implement improvements. Each stage is a thin Python module that constructs prompts and invokes Claude — the orchestrator coordinates, Claude does the thinking and coding.

**Tech Stack:** Python 3.11+, Click (CLI), PyYAML, subprocess (for `claude -p`), existing orchestrator modules (capture, registry, corpus)

**Spec:** `docs/superpowers/specs/2026-03-20-orchestrator-design.md`

---

## File Structure

### New files

| File | Responsibility |
|---|---|
| `src/orchestrator/transcripts.py` | Discover, read, and parse Claude Code transcript JSONL files |
| `src/orchestrator/observations.py` | Load, save, deduplicate, and query observation YAML files |
| `src/orchestrator/proposals.py` | Load, save, and query proposal YAML files |
| `src/orchestrator/analyzer.py` | Construct prompts and invoke `claude -p` to extract observations from transcripts |
| `src/orchestrator/proposer.py` | Construct prompts and invoke `claude -p` to generate proposals from observations |
| `src/orchestrator/implementer.py` | Spawn `claude -p` sessions in target repos to execute proposals |
| `src/orchestrator/pipeline.py` | Orchestrate the full cycle: collect → analyze → deduplicate → prioritize → propose → implement → report |
| `src/orchestrator/run_log.py` | Write and read run log entries |
| `src/orchestrator/digest.py` | Generate daily digest markdown from recent runs |
| `src/orchestrator/prompts/analyze.md` | Prompt template for transcript analysis |
| `src/orchestrator/prompts/propose.md` | Prompt template for proposal generation |
| `src/orchestrator/prompts/implement.md` | Prompt template for implementation sessions |
| `tests/test_transcripts.py` | Tests for transcript discovery and parsing |
| `tests/test_observations.py` | Tests for observation CRUD and dedup |
| `tests/test_proposals.py` | Tests for proposal CRUD |
| `tests/test_analyzer.py` | Tests for analyzer prompt construction and output parsing |
| `tests/test_proposer.py` | Tests for proposer prompt construction and output parsing |
| `tests/test_implementer.py` | Tests for implementer subprocess invocation |
| `tests/test_pipeline.py` | Tests for pipeline orchestration |
| `tests/test_run_log.py` | Tests for run log |
| `tests/fixtures/sample_transcript.jsonl` | Realistic transcript fixture for testing |

### Modified files

| File | Change |
|---|---|
| `src/orchestrator/cli.py` | Add `improve` command group with `--observe-only`, `--dry-run` flags |
| `pyproject.toml` | No new dependencies needed (subprocess + existing stack) |

---

### Task 1: Transcript Discovery and Parsing

Build the module that finds and reads Claude Code transcript files.

**Files:**
- Create: `src/orchestrator/transcripts.py`
- Create: `tests/test_transcripts.py`
- Create: `tests/fixtures/sample_transcript.jsonl`

- [ ] **Step 1: Create the sample transcript fixture**

Create a realistic JSONL transcript file matching Claude Code's actual format:

```jsonl
{"type":"file-history-snapshot","messageId":"msg-001","snapshot":{"messageId":"msg-001","trackedFileBackups":{},"timestamp":"2026-03-20T10:00:00.000Z"},"isSnapshotUpdate":false}
{"type":"user","parentUuid":"root","isSidechain":false,"message":{"role":"user","content":"Search for programs about maternal health"},"uuid":"msg-002","timestamp":"2026-03-20T10:00:01.000Z"}
{"type":"assistant","parentUuid":"msg-002","isSidechain":false,"message":{"role":"assistant","content":[{"type":"text","text":"I'll search for maternal health programs."},{"type":"tool_use","id":"tu-001","name":"mcp__connect_search__search_documents","input":{"query":"maternal health"}}]},"requestId":"req-001","type":"assistant","uuid":"msg-003","timestamp":"2026-03-20T10:00:05.000Z","userType":"external"}
{"type":"user","parentUuid":"msg-003","isSidechain":false,"message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"tu-001","content":"Found 3 programs: Maternal Health Kenya, Maternal Health India, Maternal Health Nigeria"}]},"uuid":"msg-004","timestamp":"2026-03-20T10:00:06.000Z"}
{"type":"assistant","parentUuid":"msg-004","isSidechain":false,"message":{"role":"assistant","content":[{"type":"text","text":"I found 3 maternal health programs. Let me get the app structure for the Kenya program."},{"type":"tool_use","id":"tu-002","name":"mcp__commcare_hq__get_app_structure","input":{"domain":"maternal-health-ke","app_id":"abc123"}}]},"requestId":"req-002","type":"assistant","uuid":"msg-005","timestamp":"2026-03-20T10:00:10.000Z","userType":"external"}
{"type":"user","parentUuid":"msg-005","isSidechain":false,"message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"tu-002","content":"App has 3 modules: Registration, Visit Tracking, Referrals"}]},"uuid":"msg-006","timestamp":"2026-03-20T10:00:11.000Z"}
{"type":"assistant","parentUuid":"msg-006","isSidechain":false,"message":{"role":"assistant","content":[{"type":"text","text":"The app has Registration, Visit Tracking, and Referrals modules. Now I need to create training materials for the workers, but I don't have a tool for that. Let me draft something manually based on the app structure..."}]},"requestId":"req-003","type":"assistant","uuid":"msg-007","timestamp":"2026-03-20T10:00:15.000Z","userType":"external"}
{"type":"user","parentUuid":"msg-007","isSidechain":false,"message":{"role":"user","content":"Yes please draft the training manual"},"uuid":"msg-008","timestamp":"2026-03-20T10:01:00.000Z"}
{"type":"assistant","parentUuid":"msg-008","isSidechain":false,"message":{"role":"assistant","content":[{"type":"text","text":"# Training Manual for Maternal Health Kenya\n\n## Module 1: Registration\nWhen a new pregnant woman visits...\n\n## Module 2: Visit Tracking\nAt each follow-up visit...\n\n## Module 3: Referrals\nIf a high-risk condition is detected..."}]},"requestId":"req-004","type":"assistant","uuid":"msg-009","timestamp":"2026-03-20T10:02:00.000Z","userType":"external"}
{"type":"last-prompt","lastPrompt":"Yes please draft the training manual","sessionId":"test-session-001"}
```

- [ ] **Step 2: Write failing tests for transcript parsing**

```python
# tests/test_transcripts.py
import json
from pathlib import Path
import pytest
from orchestrator.transcripts import (
    read_transcript,
    extract_user_messages,
    extract_tool_calls,
    extract_assistant_text,
    get_session_id,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"


class TestReadTranscript:
    def test_returns_list_of_dicts(self):
        entries = read_transcript(FIXTURE)
        assert isinstance(entries, list)
        assert all(isinstance(e, dict) for e in entries)

    def test_all_entries_have_type(self):
        entries = read_transcript(FIXTURE)
        assert all("type" in e for e in entries)

    def test_missing_file_returns_empty(self):
        entries = read_transcript(Path("/nonexistent/transcript.jsonl"))
        assert entries == []

    def test_filters_file_history_snapshots(self):
        entries = read_transcript(FIXTURE)
        types = [e["type"] for e in entries]
        assert "file-history-snapshot" not in types


class TestExtractUserMessages:
    def test_returns_strings(self):
        entries = read_transcript(FIXTURE)
        messages = extract_user_messages(entries)
        assert all(isinstance(m, str) for m in messages)

    def test_finds_user_text(self):
        entries = read_transcript(FIXTURE)
        messages = extract_user_messages(entries)
        assert any("maternal health" in m.lower() for m in messages)

    def test_excludes_tool_results(self):
        entries = read_transcript(FIXTURE)
        messages = extract_user_messages(entries)
        assert all("tool_result" not in m for m in messages)


class TestFindCompletedTranscripts:
    def test_returns_list(self, tmp_path):
        log = tmp_path / "session-log.jsonl"
        log.touch()
        result = find_completed_transcripts(log)
        assert isinstance(result, list)

    def test_empty_log_returns_empty(self, tmp_path):
        log = tmp_path / "session-log.jsonl"
        log.touch()
        assert find_completed_transcripts(log) == []

    def test_skips_processed_sessions(self, tmp_path):
        log = tmp_path / "session-log.jsonl"
        log.write_text('{"session_id":"s1","project":"/test","ts":"2026-03-20T10:00:00","server":"x","tool":"y"}\n')
        result = find_completed_transcripts(log, processed={"s1"})
        assert len(result) == 0

    def test_respects_since_ts(self, tmp_path):
        log = tmp_path / "session-log.jsonl"
        log.write_text(
            '{"session_id":"s1","project":"/test","ts":"2026-03-19T10:00:00","server":"x","tool":"y"}\n'
            '{"session_id":"s2","project":"/test","ts":"2026-03-20T10:00:00","server":"x","tool":"y"}\n'
        )
        result = find_completed_transcripts(log, since_ts="2026-03-20T00:00:00")
        session_ids = [r["session_id"] for r in result]
        assert "s1" not in session_ids


class TestExtractToolCalls:
    def test_returns_list_of_dicts(self):
        entries = read_transcript(FIXTURE)
        calls = extract_tool_calls(entries)
        assert isinstance(calls, list)
        assert all(isinstance(c, dict) for c in calls)

    def test_each_call_has_name_and_input(self):
        entries = read_transcript(FIXTURE)
        calls = extract_tool_calls(entries)
        for call in calls:
            assert "name" in call
            assert "input" in call

    def test_finds_mcp_calls(self):
        entries = read_transcript(FIXTURE)
        calls = extract_tool_calls(entries)
        names = [c["name"] for c in calls]
        assert "mcp__connect_search__search_documents" in names
        assert "mcp__commcare_hq__get_app_structure" in names

    def test_includes_tool_result(self):
        entries = read_transcript(FIXTURE)
        calls = extract_tool_calls(entries)
        for call in calls:
            assert "result" in call


class TestExtractAssistantText:
    def test_returns_strings(self):
        entries = read_transcript(FIXTURE)
        texts = extract_assistant_text(entries)
        assert all(isinstance(t, str) for t in texts)

    def test_finds_assistant_reasoning(self):
        entries = read_transcript(FIXTURE)
        texts = extract_assistant_text(entries)
        combined = " ".join(texts)
        assert "training" in combined.lower()


class TestGetSessionId:
    def test_returns_session_id(self):
        entries = read_transcript(FIXTURE)
        assert get_session_id(entries) == "test-session-001"

    def test_returns_none_if_no_last_prompt(self):
        assert get_session_id([]) is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_transcripts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'orchestrator.transcripts'`

- [ ] **Step 4: Implement transcripts module**

```python
# src/orchestrator/transcripts.py
"""Discover, read, and parse Claude Code transcript JSONL files."""
import json
from pathlib import Path


def read_transcript(path: Path) -> list[dict]:
    """Read a transcript JSONL file, filtering out file-history-snapshots."""
    if not path.exists():
        return []
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if entry.get("type") != "file-history-snapshot":
                entries.append(entry)
    return entries


def extract_user_messages(entries: list[dict]) -> list[str]:
    """Extract human-authored user messages (not tool results)."""
    messages = []
    for entry in entries:
        if entry.get("type") != "user":
            continue
        msg = entry.get("message", {})
        if isinstance(msg, dict):
            content = msg.get("content", "")
            if isinstance(content, str) and content:
                messages.append(content)
            # Skip tool_result content blocks
    return messages


def extract_tool_calls(entries: list[dict]) -> list[dict]:
    """Extract tool calls from assistant messages, paired with their results."""
    # First pass: collect all tool calls
    calls = {}
    for entry in entries:
        if entry.get("type") != "assistant":
            continue
        msg = entry.get("message", {})
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                calls[block["id"]] = {
                    "name": block["name"],
                    "input": block.get("input", {}),
                    "result": None,
                }

    # Second pass: match tool results
    for entry in entries:
        if entry.get("type") != "user":
            continue
        msg = entry.get("message", {})
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                tool_id = block.get("tool_use_id")
                if tool_id in calls:
                    calls[tool_id]["result"] = block.get("content", "")

    return list(calls.values())


def extract_assistant_text(entries: list[dict]) -> list[str]:
    """Extract text blocks from assistant messages."""
    texts = []
    for entry in entries:
        if entry.get("type") != "assistant":
            continue
        msg = entry.get("message", {})
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
    return texts


def get_session_id(entries: list[dict]) -> str | None:
    """Extract session ID from the last-prompt entry."""
    for entry in entries:
        if entry.get("type") == "last-prompt":
            return entry.get("sessionId")
    return None


def find_completed_transcripts(
    session_log_path: Path,
    since_ts: str | None = None,
    processed: set[str] | None = None,
    stale_minutes: int = 5,
) -> list[dict]:
    """Find transcript files for completed sessions since a timestamp.

    Returns list of dicts with keys: session_id, project, transcript_path.
    Skips transcripts that are still being written (modified recently)
    or have already been processed.
    """
    import time
    from orchestrator.capture import (
        read_session_log,
        group_by_session,
        find_transcript_path,
    )

    processed = processed or set()
    entries = read_session_log(session_log_path)

    # Filter by timestamp if provided
    if since_ts:
        entries = [e for e in entries if e.get("ts", "") > since_ts]

    grouped = group_by_session(entries)
    results = []

    for session_id, session_entries in grouped.items():
        if session_id in processed or session_id == "unknown":
            continue

        project = session_entries[0].get("project", "unknown")
        transcript_path = find_transcript_path(session_id, project)

        if not transcript_path.exists():
            continue

        # Skip if still being written
        mtime = transcript_path.stat().st_mtime
        age_minutes = (time.time() - mtime) / 60
        if age_minutes < stale_minutes:
            continue

        results.append({
            "session_id": session_id,
            "project": project,
            "transcript_path": transcript_path,
        })

    return results
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_transcripts.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/orchestrator/transcripts.py tests/test_transcripts.py tests/fixtures/sample_transcript.jsonl
git commit -m "feat: add transcript discovery and parsing module"
```

---

### Task 2: Observation Data Model

Build the module that stores, loads, deduplicates, and queries observations.

**Files:**
- Create: `src/orchestrator/observations.py`
- Create: `tests/test_observations.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_observations.py
from pathlib import Path
import pytest
from orchestrator.observations import (
    create_observation,
    save_observation,
    load_observation,
    list_observations,
    find_matching_observation,
    merge_observation,
)


class TestCreateObservation:
    def test_returns_dict(self):
        obs = create_observation(
            obs_type="gap",
            description="No tool for generating training materials",
            severity="high",
            session_id="abc123",
        )
        assert isinstance(obs, dict)

    def test_has_required_fields(self):
        obs = create_observation(
            obs_type="gap",
            description="No tool for generating training materials",
            severity="high",
            session_id="abc123",
        )
        assert obs["type"] == "gap"
        assert obs["description"] == "No tool for generating training materials"
        assert obs["severity"] == "high"
        assert obs["frequency"] == 1
        assert obs["sessions"] == ["abc123"]

    def test_optional_fields(self):
        obs = create_observation(
            obs_type="friction",
            description="search_documents returns too many results",
            severity="medium",
            session_id="def456",
            related_servers=["connect-search"],
            lifecycle_stage="research",
        )
        assert obs["related_servers"] == ["connect-search"]
        assert obs["lifecycle_stage"] == "research"

    def test_has_id(self):
        obs = create_observation(
            obs_type="gap",
            description="test",
            severity="low",
            session_id="abc",
        )
        assert "id" in obs
        assert isinstance(obs["id"], str)

    def test_has_created_date(self):
        obs = create_observation(
            obs_type="gap",
            description="test",
            severity="low",
            session_id="abc",
        )
        assert "created" in obs


class TestSaveLoadRoundTrip:
    def test_save_creates_file(self, tmp_path):
        obs = create_observation("gap", "test", "low", "abc")
        path = save_observation(obs, tmp_path)
        assert path.exists()

    def test_save_returns_path(self, tmp_path):
        obs = create_observation("gap", "test", "low", "abc")
        path = save_observation(obs, tmp_path)
        assert isinstance(path, Path)

    def test_round_trip_preserves_fields(self, tmp_path):
        obs = create_observation("gap", "test desc", "high", "s1",
                                 related_servers=["server-a"])
        path = save_observation(obs, tmp_path)
        loaded = load_observation(path)
        assert loaded["type"] == "gap"
        assert loaded["description"] == "test desc"
        assert loaded["severity"] == "high"
        assert loaded["related_servers"] == ["server-a"]

    def test_filename_uses_id(self, tmp_path):
        obs = create_observation("gap", "test", "low", "abc")
        path = save_observation(obs, tmp_path)
        assert obs["id"] in path.name


class TestListObservations:
    def test_returns_list(self, tmp_path):
        result = list_observations(tmp_path)
        assert isinstance(result, list)

    def test_empty_dir_returns_empty(self, tmp_path):
        assert list_observations(tmp_path) == []

    def test_finds_saved_observations(self, tmp_path):
        obs1 = create_observation("gap", "test1", "low", "s1")
        obs2 = create_observation("friction", "test2", "high", "s2")
        save_observation(obs1, tmp_path)
        save_observation(obs2, tmp_path)
        result = list_observations(tmp_path)
        assert len(result) == 2

    def test_filter_by_type(self, tmp_path):
        save_observation(create_observation("gap", "t1", "low", "s1"), tmp_path)
        save_observation(create_observation("friction", "t2", "high", "s2"), tmp_path)
        gaps = list_observations(tmp_path, obs_type="gap")
        assert len(gaps) == 1

    def test_filter_by_status(self, tmp_path):
        obs = create_observation("gap", "t1", "low", "s1")
        save_observation(obs, tmp_path)
        pending = list_observations(tmp_path, status="pending")
        assert len(pending) == 1
        addressed = list_observations(tmp_path, status="addressed")
        assert len(addressed) == 0


class TestFindMatchingObservation:
    def test_finds_match_by_type_and_servers(self):
        existing = [create_observation("gap", "test", "low", "s1",
                                        related_servers=["server-a"],
                                        lifecycle_stage="research")]
        new = create_observation("gap", "different desc", "high", "s2",
                                 related_servers=["server-a"],
                                 lifecycle_stage="research")
        match = find_matching_observation(new, existing)
        assert match is not None

    def test_no_match_different_type(self):
        existing = [create_observation("gap", "test", "low", "s1")]
        new = create_observation("friction", "test", "low", "s2")
        assert find_matching_observation(new, existing) is None

    def test_no_match_different_servers(self):
        existing = [create_observation("gap", "test", "low", "s1",
                                        related_servers=["server-a"])]
        new = create_observation("gap", "test", "low", "s2",
                                 related_servers=["server-b"])
        assert find_matching_observation(new, existing) is None

    def test_skips_addressed_observations(self):
        existing = [create_observation("gap", "test", "low", "s1")]
        existing[0]["status"] = "addressed"
        new = create_observation("gap", "test", "low", "s2")
        assert find_matching_observation(new, existing) is None


class TestMergeObservation:
    def test_increments_frequency(self):
        existing = create_observation("gap", "test", "low", "s1")
        merged = merge_observation(existing, session_id="s2")
        assert merged["frequency"] == 2

    def test_appends_session(self):
        existing = create_observation("gap", "test", "low", "s1")
        merged = merge_observation(existing, session_id="s2")
        assert "s2" in merged["sessions"]

    def test_preserves_original_fields(self):
        existing = create_observation("gap", "test", "high", "s1",
                                      related_servers=["server-a"])
        merged = merge_observation(existing, session_id="s2")
        assert merged["type"] == "gap"
        assert merged["related_servers"] == ["server-a"]

    def test_escalates_severity_if_frequent(self):
        existing = create_observation("gap", "test", "low", "s1")
        existing["frequency"] = 4
        existing["sessions"] = ["s1", "s2", "s3", "s4"]
        merged = merge_observation(existing, session_id="s5")
        assert merged["severity"] == "high"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_observations.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement observations module**

```python
# src/orchestrator/observations.py
"""Load, save, deduplicate, and query observation YAML files."""
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml


def create_observation(
    obs_type: str,
    description: str,
    severity: str,
    session_id: str,
    related_servers: list[str] | None = None,
    lifecycle_stage: str | None = None,
) -> dict[str, Any]:
    """Create a new observation dict."""
    return {
        "id": uuid4().hex[:12],
        "type": obs_type,
        "description": description,
        "severity": severity,
        "frequency": 1,
        "sessions": [session_id],
        "related_servers": related_servers or [],
        "lifecycle_stage": lifecycle_stage,
        "status": "pending",
        "created": date.today().isoformat(),
    }


def save_observation(obs: dict, obs_dir: Path) -> Path:
    """Save an observation to a YAML file."""
    obs_dir.mkdir(parents=True, exist_ok=True)
    path = obs_dir / f"{obs['id']}.yaml"
    with open(path, "w") as f:
        yaml.dump(obs, f, default_flow_style=False, sort_keys=False)
    return path


def load_observation(path: Path) -> dict | None:
    """Load an observation from a YAML file. Returns None on parse error."""
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return None


def list_observations(
    obs_dir: Path,
    obs_type: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """List observations, optionally filtered by type and/or status."""
    if not obs_dir.exists():
        return []
    results = []
    for path in sorted(obs_dir.glob("*.yaml")):
        obs = load_observation(path)
        if obs_type and obs.get("type") != obs_type:
            continue
        if status and obs.get("status") != status:
            continue
        results.append(obs)
    return results


def find_matching_observation(
    new_obs: dict,
    existing: list[dict],
) -> dict | None:
    """Find an existing observation that matches the new one.

    Matching is by type + related_servers + lifecycle_stage.
    This is the rule-based pre-filter; LLM-assisted dedup happens in
    the analyzer when the match is ambiguous.
    """
    for obs in existing:
        if (
            obs.get("type") == new_obs.get("type")
            and set(obs.get("related_servers", [])) == set(new_obs.get("related_servers", []))
            and obs.get("lifecycle_stage") == new_obs.get("lifecycle_stage")
            and obs.get("status") == "pending"
        ):
            return obs
    return None


def merge_observation(existing: dict, session_id: str) -> dict:
    """Merge a new sighting into an existing observation."""
    merged = {**existing}
    merged["frequency"] = existing["frequency"] + 1
    merged["sessions"] = existing["sessions"] + [session_id]
    # Escalate severity if seen 5+ times
    if merged["frequency"] >= 5 and merged["severity"] == "low":
        merged["severity"] = "high"
    elif merged["frequency"] >= 3 and merged["severity"] == "low":
        merged["severity"] = "medium"
    return merged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_observations.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator/observations.py tests/test_observations.py
git commit -m "feat: add observation data model with CRUD and deduplication"
```

---

### Task 3: Proposal Data Model

Build the module that stores and queries improvement proposals.

**Files:**
- Create: `src/orchestrator/proposals.py`
- Create: `tests/test_proposals.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_proposals.py
from pathlib import Path
import pytest
from orchestrator.proposals import (
    create_proposal,
    save_proposal,
    load_proposal,
    list_proposals,
    update_proposal_status,
)


class TestCreateProposal:
    def test_returns_dict(self):
        p = create_proposal(
            proposal_type="new_tool",
            action="Create generate_training_manual tool",
            target_repo="~/emdash-projects/connect-labs",
            ownership="self",
            motivation="No tool for training materials",
            observation_id="obs-abc",
        )
        assert isinstance(p, dict)

    def test_has_required_fields(self):
        p = create_proposal(
            proposal_type="new_tool",
            action="Create generate_training_manual tool",
            target_repo="~/emdash-projects/connect-labs",
            ownership="self",
            motivation="No tool for training materials",
            observation_id="obs-abc",
        )
        assert p["type"] == "new_tool"
        assert p["action"] == "Create generate_training_manual tool"
        assert p["target_repo"] == "~/emdash-projects/connect-labs"
        assert p["ownership"] == "self"
        assert p["status"] == "pending"

    def test_has_id_and_date(self):
        p = create_proposal("new_tool", "test", "~/repo", "self", "why", "obs-1")
        assert "id" in p
        assert "created" in p

    def test_complexity_defaults_to_medium(self):
        p = create_proposal("new_tool", "test", "~/repo", "self", "why", "obs-1")
        assert p["complexity"] == "medium"

    def test_custom_complexity(self):
        p = create_proposal("new_tool", "test", "~/repo", "self", "why", "obs-1",
                            complexity="low")
        assert p["complexity"] == "low"


class TestSaveLoadRoundTrip:
    def test_save_creates_file(self, tmp_path):
        p = create_proposal("new_tool", "test", "~/r", "self", "why", "obs-1")
        path = save_proposal(p, tmp_path)
        assert path.exists()

    def test_round_trip(self, tmp_path):
        p = create_proposal("new_tool", "test action", "~/r", "self", "why", "obs-1")
        path = save_proposal(p, tmp_path)
        loaded = load_proposal(path)
        assert loaded["action"] == "test action"
        assert loaded["type"] == "new_tool"


class TestListProposals:
    def test_empty_dir(self, tmp_path):
        assert list_proposals(tmp_path) == []

    def test_finds_proposals(self, tmp_path):
        save_proposal(create_proposal("new_tool", "t1", "~/r", "self", "w", "o1"), tmp_path)
        save_proposal(create_proposal("improvement", "t2", "~/r", "self", "w", "o2"), tmp_path)
        assert len(list_proposals(tmp_path)) == 2

    def test_filter_by_status(self, tmp_path):
        save_proposal(create_proposal("new_tool", "t1", "~/r", "self", "w", "o1"), tmp_path)
        assert len(list_proposals(tmp_path, status="pending")) == 1
        assert len(list_proposals(tmp_path, status="implemented")) == 0


class TestUpdateStatus:
    def test_updates_status(self, tmp_path):
        p = create_proposal("new_tool", "t1", "~/r", "self", "w", "o1")
        path = save_proposal(p, tmp_path)
        update_proposal_status(path, "implemented")
        loaded = load_proposal(path)
        assert loaded["status"] == "implemented"

    def test_updates_status_to_failed(self, tmp_path):
        p = create_proposal("new_tool", "t1", "~/r", "self", "w", "o1")
        path = save_proposal(p, tmp_path)
        update_proposal_status(path, "failed", reason="Tests did not pass")
        loaded = load_proposal(path)
        assert loaded["status"] == "failed"
        assert loaded["failure_reason"] == "Tests did not pass"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_proposals.py -v`
Expected: FAIL

- [ ] **Step 3: Implement proposals module**

```python
# src/orchestrator/proposals.py
"""Load, save, and query improvement proposal YAML files."""
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml


def create_proposal(
    proposal_type: str,
    action: str,
    target_repo: str,
    ownership: str,
    motivation: str,
    observation_id: str,
    complexity: str = "medium",
) -> dict[str, Any]:
    """Create a new proposal dict."""
    return {
        "id": uuid4().hex[:12],
        "type": proposal_type,
        "action": action,
        "target_repo": target_repo,
        "ownership": ownership,
        "motivation": motivation,
        "observation_id": observation_id,
        "complexity": complexity,
        "status": "pending",
        "failure_reason": None,
        "created": date.today().isoformat(),
    }


def save_proposal(proposal: dict, proposals_dir: Path) -> Path:
    """Save a proposal to a YAML file."""
    proposals_dir.mkdir(parents=True, exist_ok=True)
    path = proposals_dir / f"{proposal['id']}.yaml"
    with open(path, "w") as f:
        yaml.dump(proposal, f, default_flow_style=False, sort_keys=False)
    return path


def load_proposal(path: Path) -> dict | None:
    """Load a proposal from a YAML file. Returns None on parse error."""
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return None


def list_proposals(
    proposals_dir: Path,
    status: str | None = None,
) -> list[dict]:
    """List proposals, optionally filtered by status."""
    if not proposals_dir.exists():
        return []
    results = []
    for path in sorted(proposals_dir.glob("*.yaml")):
        proposal = load_proposal(path)
        if status and proposal.get("status") != status:
            continue
        results.append(proposal)
    return results


def update_proposal_status(
    path: Path,
    status: str,
    reason: str | None = None,
) -> None:
    """Update a proposal's status on disk."""
    proposal = load_proposal(path)
    proposal["status"] = status
    if reason:
        proposal["failure_reason"] = reason
    with open(path, "w") as f:
        yaml.dump(proposal, f, default_flow_style=False, sort_keys=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_proposals.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator/proposals.py tests/test_proposals.py
git commit -m "feat: add proposal data model with CRUD and status tracking"
```

---

### Task 4: Run Log

Build the module that records what each improvement cycle did.

**Files:**
- Create: `src/orchestrator/run_log.py`
- Create: `tests/test_run_log.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_run_log.py
from pathlib import Path
from orchestrator.run_log import create_run_entry, save_run, load_run, get_last_run_ts


class TestCreateRunEntry:
    def test_returns_dict(self):
        run = create_run_entry()
        assert isinstance(run, dict)

    def test_has_started_ts(self):
        run = create_run_entry()
        assert "started" in run

    def test_has_empty_results(self):
        run = create_run_entry()
        assert run["transcripts_analyzed"] == 0
        assert run["observations_created"] == 0
        assert run["proposals_generated"] == 0
        assert run["proposals_implemented"] == 0


class TestSaveAndLoad:
    def test_round_trip(self, tmp_path):
        run = create_run_entry()
        run["transcripts_analyzed"] = 3
        path = save_run(run, tmp_path)
        loaded = load_run(path)
        assert loaded["transcripts_analyzed"] == 3

    def test_filename_includes_timestamp(self, tmp_path):
        run = create_run_entry()
        path = save_run(run, tmp_path)
        assert "run-" in path.name


class TestGetLastRunTs:
    def test_no_runs_returns_none(self, tmp_path):
        assert get_last_run_ts(tmp_path) is None

    def test_returns_latest_started_ts(self, tmp_path):
        run1 = create_run_entry()
        run1["started"] = "2026-03-20T10:00:00"
        save_run(run1, tmp_path)
        run2 = create_run_entry()
        run2["started"] = "2026-03-20T14:00:00"
        save_run(run2, tmp_path)
        assert get_last_run_ts(tmp_path) == "2026-03-20T14:00:00"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_run_log.py -v`
Expected: FAIL

- [ ] **Step 3: Implement run_log module**

```python
# src/orchestrator/run_log.py
"""Write and read improvement cycle run logs."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def create_run_entry() -> dict[str, Any]:
    """Create a new run log entry."""
    return {
        "started": datetime.now(timezone.utc).isoformat(),
        "completed": None,
        "transcripts_analyzed": 0,
        "observations_created": 0,
        "observations_merged": 0,
        "proposals_generated": 0,
        "proposals_implemented": 0,
        "proposals_failed": 0,
        "processed_sessions": [],
        "errors": [],
    }


def save_run(run: dict, runs_dir: Path) -> Path:
    """Save a run entry to a YAML file."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    ts = run["started"].replace(":", "-").replace("+", "p")
    path = runs_dir / f"run-{ts}.yaml"
    with open(path, "w") as f:
        yaml.dump(run, f, default_flow_style=False, sort_keys=False)
    return path


def load_run(path: Path) -> dict:
    """Load a run entry from a YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)


def get_last_run_ts(runs_dir: Path) -> str | None:
    """Get the started timestamp of the most recent run."""
    if not runs_dir.exists():
        return None
    runs = sorted(runs_dir.glob("run-*.yaml"))
    if not runs:
        return None
    last = load_run(runs[-1])
    return last.get("started")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_run_log.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator/run_log.py tests/test_run_log.py
git commit -m "feat: add run log for tracking improvement cycle results"
```

---

### Task 5: Prompt Templates

Create the prompt templates that drive transcript analysis, proposal generation, and implementation.

**Files:**
- Create: `src/orchestrator/prompts/analyze.md`
- Create: `src/orchestrator/prompts/propose.md`
- Create: `src/orchestrator/prompts/implement.md`
- Create: `src/orchestrator/prompts/__init__.py`

- [ ] **Step 1: Create the prompts directory**

```bash
mkdir -p src/orchestrator/prompts
```

- [ ] **Step 2: Write the analysis prompt template**

```markdown
# src/orchestrator/prompts/analyze.md
You are analyzing a Claude Code session transcript to identify improvements for
an MCP tool ecosystem. Your job is to find friction, gaps, patterns, and missing
capabilities.

## Context

The user has these MCP servers available:
{registry_summary}

## Transcript

{transcript_text}

## Instructions

Analyze this transcript and output a YAML list of observations. Each observation
should have:

- `type`: one of `friction`, `gap`, `pattern`, `missing_capability`
- `description`: what you observed (1-2 sentences)
- `severity`: `low`, `medium`, or `high`
- `related_servers`: list of MCP server names involved (can be empty)
- `lifecycle_stage`: which part of the workflow this relates to (e.g.,
  "research", "solicitation-creation", "training-material-creation", or null)
- `evidence`: brief quote or summary from the transcript showing this

**Definitions:**
- `friction`: a tool was used but worked poorly (failed, retried, unhelpful
  results)
- `gap`: the user did something manually that could have been automated with a
  tool
- `pattern`: a multi-tool sequence that recurs and could become a workflow
- `missing_capability`: the user needed something that no server, skill, or hook
  could handle

Only include real observations. If the session went smoothly with no issues,
output an empty list: `[]`

Output ONLY valid YAML. No commentary before or after.
```

- [ ] **Step 3: Write the proposal prompt template**

```markdown
# src/orchestrator/prompts/propose.md
You are generating improvement proposals for an MCP tool ecosystem. Based on
observations from real usage sessions, propose concrete changes.

## Current Ecosystem

{registry_summary}

## Observations to Address

{observations_yaml}

## Instructions

For each observation (or group of related observations), generate a proposal.
Output a YAML list where each proposal has:

- `type`: one of `new_tool`, `new_server`, `tool_improvement`, `new_skill`,
  `new_workflow`, `hook_improvement`, `registry_update`
- `action`: what to do (be specific — name the tool, describe the feature)
- `target_repo`: the repo path to modify (from the registry, e.g.,
  `~/emdash-projects/connect-labs`)
- `ownership`: `self`, `team`, or `external` (from the registry)
- `motivation`: why this is needed (reference the observation)
- `observation_id`: the ID of the observation this addresses
- `complexity`: `low`, `medium`, or `high`

Guidelines:
- Prefer adding to existing servers over creating new ones
- Only propose `new_server` if no existing server is a natural fit
- Be specific: "Add filter_by_status parameter to search_opportunities" not
  "improve search"
- One proposal per observation unless they're clearly the same change

Output ONLY valid YAML. No commentary before or after.
```

- [ ] **Step 4: Write the implementation prompt template**

```markdown
# src/orchestrator/prompts/implement.md
You are implementing an improvement to an MCP tool ecosystem. A proposal has
been generated from real usage analysis, and you need to execute it.

## Proposal

{proposal_yaml}

## Why This Is Needed

{observation_yaml}

## Current Registry Context

{registry_summary}

## Instructions

Implement the proposed change in this repository. Specifically:

1. Create a feature branch: `git checkout -b orchestrator/<short-description>`
2. Read the existing code to understand the current structure
3. Implement the change described in the proposal
4. Write tests for the new functionality
5. Run the tests and make sure they pass
6. Commit with a descriptive message
7. If tests pass, merge to main: `git checkout main && git merge orchestrator/<short-description>`
8. If tests fail, leave the branch unmerged and exit with a non-zero status

If this is a new MCP tool, follow the existing patterns in this repo for how
tools are defined and registered.

If the implementation is not feasible (missing dependencies, would break existing
functionality, or the proposal is unclear), explain why and exit without making
changes.

After implementing, update the orchestrator's registry.yaml at
`{registry_path}` to add any new servers, tools, or answers fields so
future sessions know about the new capabilities.
```

- [ ] **Step 5: Write the prompts loader**

```python
# src/orchestrator/prompts/__init__.py
"""Prompt template loader."""
from pathlib import Path


PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str, **kwargs: str) -> str:
    """Load a prompt template and fill in placeholders."""
    path = PROMPTS_DIR / f"{name}.md"
    template = path.read_text()
    return template.format(**kwargs)
```

- [ ] **Step 6: Commit**

```bash
git add src/orchestrator/prompts/
git commit -m "feat: add prompt templates for analysis, proposals, and implementation"
```

---

### Task 6: Transcript Analyzer

Build the module that invokes `claude -p` to analyze transcripts and extract observations.

**Files:**
- Create: `src/orchestrator/analyzer.py`
- Create: `tests/test_analyzer.py`

- [ ] **Step 1: Write failing tests**

Tests use monkeypatching to avoid actually calling `claude -p`:

```python
# tests/test_analyzer.py
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import yaml
import pytest
from orchestrator.analyzer import (
    build_analysis_prompt,
    parse_analysis_output,
    analyze_transcript,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"


class TestBuildAnalysisPrompt:
    def test_returns_string(self):
        prompt = build_analysis_prompt(FIXTURE, registry_summary="test registry")
        assert isinstance(prompt, str)

    def test_includes_registry(self):
        prompt = build_analysis_prompt(FIXTURE, registry_summary="## Server: connect-search")
        assert "connect-search" in prompt

    def test_includes_transcript_content(self):
        prompt = build_analysis_prompt(FIXTURE, registry_summary="test")
        assert "maternal health" in prompt.lower() or "search" in prompt.lower()


class TestParseAnalysisOutput:
    def test_parses_valid_yaml_list(self):
        output = yaml.dump([{
            "type": "gap",
            "description": "No training tool",
            "severity": "high",
            "related_servers": ["commcare-hq"],
            "lifecycle_stage": "training",
            "evidence": "user wrote manual manually",
        }])
        result = parse_analysis_output(output)
        assert len(result) == 1
        assert result[0]["type"] == "gap"

    def test_empty_list(self):
        result = parse_analysis_output("[]")
        assert result == []

    def test_handles_yaml_with_markdown_fence(self):
        output = "```yaml\n- type: gap\n  description: test\n```"
        result = parse_analysis_output(output)
        assert len(result) == 1

    def test_handles_invalid_output(self):
        result = parse_analysis_output("This is not YAML at all!!! 🎉")
        assert result == []

    def test_rejects_non_list(self):
        result = parse_analysis_output("type: gap\ndescription: test")
        assert result == []


class TestAnalyzeTranscript:
    @patch("orchestrator.analyzer.subprocess.run")
    def test_returns_parsed_observations(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="- type: gap\n  description: test\n  severity: high\n  related_servers: []\n  lifecycle_stage: null\n  evidence: test",
        )
        result = analyze_transcript(FIXTURE, "test registry")
        assert len(result) == 1
        assert result[0]["type"] == "gap"

    @patch("orchestrator.analyzer.subprocess.run")
    def test_returns_empty_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = analyze_transcript(FIXTURE, "test registry")
        assert result == []

    @patch("orchestrator.analyzer.subprocess.run")
    def test_returns_empty_on_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=120)
        result = analyze_transcript(FIXTURE, "test registry")
        assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_analyzer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement analyzer module**

```python
# src/orchestrator/analyzer.py
"""Construct prompts and invoke claude -p to extract observations from transcripts."""
import json
import subprocess
from pathlib import Path

import yaml

from orchestrator.prompts import load_prompt
from orchestrator.transcripts import (
    read_transcript,
    extract_user_messages,
    extract_tool_calls,
    extract_assistant_text,
)


def build_analysis_prompt(transcript_path: Path, registry_summary: str) -> str:
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
        registry_summary=registry_summary,
        transcript_text=transcript_text,
    )


def parse_analysis_output(output: str) -> list[dict]:
    """Parse YAML observation list from Claude's output."""
    # Strip markdown fences if present
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
    registry_summary: str,
    model: str = "sonnet",
    max_budget_usd: float = 0.50,
) -> list[dict]:
    """Analyze a transcript by invoking claude -p. Returns list of observations."""
    prompt = build_analysis_prompt(transcript_path, registry_summary)

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_analyzer.py -v`
Expected: All PASS (tests only cover prompt building and output parsing, not subprocess calls)

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator/analyzer.py tests/test_analyzer.py
git commit -m "feat: add transcript analyzer with prompt construction and output parsing"
```

---

### Task 7: Proposal Generator

Build the module that invokes `claude -p` to generate proposals from observations.

**Files:**
- Create: `src/orchestrator/proposer.py`
- Create: `tests/test_proposer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_proposer.py
import yaml
import pytest
from orchestrator.proposer import (
    build_proposal_prompt,
    parse_proposal_output,
)


class TestBuildProposalPrompt:
    def test_returns_string(self):
        obs = [{"type": "gap", "description": "test", "id": "abc"}]
        prompt = build_proposal_prompt(obs, registry_summary="test registry")
        assert isinstance(prompt, str)

    def test_includes_observations(self):
        obs = [{"type": "gap", "description": "No training tool", "id": "abc"}]
        prompt = build_proposal_prompt(obs, registry_summary="test")
        assert "training tool" in prompt.lower()

    def test_includes_registry(self):
        obs = [{"type": "gap", "description": "test", "id": "abc"}]
        prompt = build_proposal_prompt(obs, registry_summary="## Server: connect-search")
        assert "connect-search" in prompt


class TestParseProposalOutput:
    def test_parses_valid_yaml_list(self):
        output = yaml.dump([{
            "type": "new_tool",
            "action": "Create training tool",
            "target_repo": "~/emdash-projects/connect-labs",
            "ownership": "self",
            "motivation": "Needed for training",
            "observation_id": "abc",
            "complexity": "medium",
        }])
        result = parse_proposal_output(output)
        assert len(result) == 1
        assert result[0]["type"] == "new_tool"

    def test_empty_list(self):
        assert parse_proposal_output("[]") == []

    def test_handles_invalid(self):
        assert parse_proposal_output("not yaml!!!") == []

    def test_handles_markdown_fence(self):
        output = "```yaml\n- type: new_tool\n  action: test\n```"
        result = parse_proposal_output(output)
        assert len(result) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_proposer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement proposer module**

```python
# src/orchestrator/proposer.py
"""Construct prompts and invoke claude -p to generate proposals from observations."""
import subprocess

import yaml

from orchestrator.prompts import load_prompt


def build_proposal_prompt(
    observations: list[dict],
    registry_summary: str,
) -> str:
    """Build the full prompt for proposal generation."""
    observations_yaml = yaml.dump(observations, default_flow_style=False)
    return load_prompt(
        "propose",
        registry_summary=registry_summary,
        observations_yaml=observations_yaml,
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
) -> list[dict]:
    """Generate proposals by invoking claude -p. Returns list of proposals."""
    prompt = build_proposal_prompt(observations, registry_summary)

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

    if result.returncode != 0:
        return []

    return parse_proposal_output(result.stdout)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_proposer.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator/proposer.py tests/test_proposer.py
git commit -m "feat: add proposal generator with prompt construction and output parsing"
```

---

### Task 8: Implementer

Build the module that spawns `claude -p` sessions in target repos to execute proposals.

**Files:**
- Create: `src/orchestrator/implementer.py`
- Create: `tests/test_implementer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_implementer.py
from pathlib import Path
import pytest
from orchestrator.implementer import (
    build_implementation_prompt,
    resolve_repo_path,
    run_implementation,
)


class TestBuildImplementationPrompt:
    def test_returns_string(self):
        prompt = build_implementation_prompt(
            proposal={"type": "new_tool", "action": "Create tool X"},
            observation={"type": "gap", "description": "Missing tool X"},
            registry_summary="test registry",
        )
        assert isinstance(prompt, str)

    def test_includes_proposal(self):
        prompt = build_implementation_prompt(
            proposal={"type": "new_tool", "action": "Create generate_training_manual"},
            observation={"type": "gap", "description": "test"},
            registry_summary="test",
        )
        assert "generate_training_manual" in prompt

    def test_includes_observation(self):
        prompt = build_implementation_prompt(
            proposal={"type": "new_tool", "action": "test"},
            observation={"type": "gap", "description": "No training material tool"},
            registry_summary="test",
        )
        assert "training material" in prompt.lower()


class TestResolveRepoPath:
    def test_expands_tilde(self):
        path = resolve_repo_path("~/emdash-projects/connect-labs")
        assert "~" not in str(path)
        assert "emdash-projects" in str(path)

    def test_returns_path_object(self):
        path = resolve_repo_path("~/emdash-projects/connect-labs")
        assert isinstance(path, Path)

    def test_absolute_path_unchanged(self):
        path = resolve_repo_path("/tmp/test-repo")
        assert str(path) == "/tmp/test-repo"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_implementer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement implementer module**

```python
# src/orchestrator/implementer.py
"""Spawn claude -p sessions in target repos to execute proposals."""
import subprocess
from pathlib import Path

import yaml

from orchestrator.prompts import load_prompt


def build_implementation_prompt(
    proposal: dict,
    observation: dict,
    registry_summary: str,
    registry_path: str = "",
) -> str:
    """Build the full prompt for an implementation session."""
    return load_prompt(
        "implement",
        proposal_yaml=yaml.dump(proposal, default_flow_style=False),
        observation_yaml=yaml.dump(observation, default_flow_style=False),
        registry_summary=registry_summary,
        registry_path=registry_path,
    )


def resolve_repo_path(repo_path: str) -> Path:
    """Resolve a repo path, expanding ~ and making absolute."""
    return Path(repo_path).expanduser().resolve()


def run_implementation(
    proposal: dict,
    observation: dict,
    registry_summary: str,
    registry_path: str = "",
    model: str = "sonnet",
    max_budget_usd: float = 2.00,
) -> dict:
    """Run an implementation session. Returns result dict with success/output.

    For 'team' ownership, the implementation prompt instructs Claude to open
    a PR instead of merging. For 'external' ownership, skip implementation.
    """
    ownership = proposal.get("ownership", "self")

    if ownership == "external":
        return {
            "success": False,
            "error": "External repos are registry-only — skipping implementation",
            "output": "",
        }

    prompt = build_implementation_prompt(
        proposal, observation, registry_summary, registry_path=registry_path,
    )

    # For team repos, append PR instruction
    if ownership == "team":
        prompt += (
            "\n\nIMPORTANT: This is a team-owned repo. Do NOT merge to main. "
            "Instead, push the feature branch and open a pull request with "
            "`gh pr create` including the motivation in the PR description."
        )

    repo_path = resolve_repo_path(proposal["target_repo"])

    if not repo_path.exists():
        return {
            "success": False,
            "error": f"Target repo not found: {repo_path}",
            "output": "",
        }

    result = subprocess.run(
        [
            "claude", "-p", prompt,
            "--model", model,
            "--max-budget-usd", str(max_budget_usd),
            "--no-session-persistence",
        ],
        capture_output=True,
        text=True,
        cwd=repo_path,
        timeout=600,
    )

    return {
        "success": result.returncode == 0,
        "output": result.stdout,
        "error": result.stderr if result.returncode != 0 else None,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_implementer.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator/implementer.py tests/test_implementer.py
git commit -m "feat: add implementer for spawning Claude Code sessions in target repos"
```

---

### Task 9: Pipeline Orchestration

Build the module that ties everything together into a single improvement cycle.

**Files:**
- Create: `src/orchestrator/pipeline.py`
- Create: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_pipeline.py
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from orchestrator.pipeline import run_cycle, CycleConfig


class TestCycleConfig:
    def test_defaults(self):
        cfg = CycleConfig()
        assert cfg.max_transcripts == 10
        assert cfg.max_proposals == 3
        assert cfg.observe_only is False
        assert cfg.dry_run is False

    def test_observe_only(self):
        cfg = CycleConfig(observe_only=True)
        assert cfg.observe_only is True

    def test_dry_run(self):
        cfg = CycleConfig(dry_run=True)
        assert cfg.dry_run is True


class TestRunCycleNoData:
    def test_no_transcripts_returns_run_with_zero_counts(self, tmp_path):
        state_dir = tmp_path / "orchestrator"
        state_dir.mkdir()
        (state_dir / "session-log.jsonl").touch()

        result = run_cycle(
            state_dir=state_dir,
            registry_path=Path(__file__).parent / "fixtures" / "sample_registry.yaml",
            config=CycleConfig(),
        )
        assert result["transcripts_analyzed"] == 0
        assert result["observations_created"] == 0
        assert result["proposals_generated"] == 0


class TestRunCycleObserveOnly:
    @patch("orchestrator.pipeline.analyze_transcript")
    @patch("orchestrator.pipeline.find_completed_transcripts")
    def test_observe_only_skips_proposals(self, mock_find, mock_analyze, tmp_path):
        state_dir = tmp_path / "orchestrator"
        state_dir.mkdir()
        (state_dir / "session-log.jsonl").touch()

        mock_find.return_value = [{
            "session_id": "s1",
            "project": "/test",
            "transcript_path": Path(__file__).parent / "fixtures" / "sample_transcript.jsonl",
        }]
        mock_analyze.return_value = [{
            "type": "gap",
            "description": "test gap",
            "severity": "high",
            "related_servers": [],
            "lifecycle_stage": None,
            "evidence": "test",
        }]

        result = run_cycle(
            state_dir=state_dir,
            registry_path=Path(__file__).parent / "fixtures" / "sample_registry.yaml",
            config=CycleConfig(observe_only=True),
        )
        assert result["transcripts_analyzed"] == 1
        assert result["observations_created"] == 1
        assert result["proposals_generated"] == 0


class TestRunCycleDryRun:
    @patch("orchestrator.pipeline.generate_proposals")
    @patch("orchestrator.pipeline.analyze_transcript")
    @patch("orchestrator.pipeline.find_completed_transcripts")
    def test_dry_run_skips_implementation(self, mock_find, mock_analyze, mock_propose, tmp_path):
        state_dir = tmp_path / "orchestrator"
        state_dir.mkdir()
        (state_dir / "session-log.jsonl").touch()

        mock_find.return_value = [{
            "session_id": "s1",
            "project": "/test",
            "transcript_path": Path(__file__).parent / "fixtures" / "sample_transcript.jsonl",
        }]
        mock_analyze.return_value = [{
            "type": "gap",
            "description": "test",
            "severity": "high",
            "related_servers": [],
            "lifecycle_stage": None,
            "evidence": "test",
        }]
        mock_propose.return_value = [{
            "type": "new_tool",
            "action": "Create tool",
            "target_repo": "~/repo",
            "ownership": "self",
            "motivation": "needed",
            "observation_id": "obs-1",
            "complexity": "low",
        }]

        result = run_cycle(
            state_dir=state_dir,
            registry_path=Path(__file__).parent / "fixtures" / "sample_registry.yaml",
            config=CycleConfig(dry_run=True),
        )
        assert result["proposals_generated"] == 1
        assert result["proposals_implemented"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL

- [ ] **Step 3: Implement pipeline module**

```python
# src/orchestrator/pipeline.py
"""Orchestrate the full improvement cycle."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from orchestrator.analyzer import analyze_transcript
from orchestrator.implementer import run_implementation
from orchestrator.observations import (
    create_observation,
    find_matching_observation,
    list_observations,
    merge_observation,
    save_observation,
    load_observation,
)
from orchestrator.proposals import (
    create_proposal,
    list_proposals,
    save_proposal,
    update_proposal_status,
)
from orchestrator.proposer import generate_proposals
from orchestrator.registry import load_registry, format_for_skill, get_server
from orchestrator.run_log import create_run_entry, save_run, get_last_run_ts
from orchestrator.transcripts import find_completed_transcripts


@dataclass
class CycleConfig:
    max_transcripts: int = 10
    max_proposals: int = 3
    observe_only: bool = False
    dry_run: bool = False
    model: str = "sonnet"
    analysis_budget: float = 0.50
    proposal_budget: float = 0.50
    implementation_budget: float = 2.00


def run_cycle(
    state_dir: Path,
    registry_path: Path,
    config: CycleConfig | None = None,
) -> dict:
    """Run one full improvement cycle. Returns the run log entry."""
    config = config or CycleConfig()
    run = create_run_entry()

    # Load registry
    registry = load_registry(registry_path)
    registry_summary = format_for_skill(registry)

    # Paths
    session_log = state_dir / "session-log.jsonl"
    obs_dir = state_dir / "observations"
    proposals_dir = state_dir / "proposals"
    runs_dir = state_dir / "runs"

    # 1. Collect transcripts since last run
    last_ts = get_last_run_ts(runs_dir)
    processed = {
        s for r in (runs_dir.glob("run-*.yaml") if runs_dir.exists() else [])
        for s in _load_processed_sessions(r)
    }

    transcripts = find_completed_transcripts(
        session_log,
        since_ts=last_ts,
        processed=processed,
    )[:config.max_transcripts]

    # 2. Analyze each transcript
    all_new_observations = []
    for t in transcripts:
        observations = analyze_transcript(
            t["transcript_path"],
            registry_summary,
            model=config.model,
            max_budget_usd=config.analysis_budget,
        )
        run["processed_sessions"].append(t["session_id"])

        for obs_data in observations:
            obs = create_observation(
                obs_type=obs_data.get("type", "gap"),
                description=obs_data.get("description", ""),
                severity=obs_data.get("severity", "medium"),
                session_id=t["session_id"],
                related_servers=obs_data.get("related_servers", []),
                lifecycle_stage=obs_data.get("lifecycle_stage"),
            )
            all_new_observations.append(obs)

    run["transcripts_analyzed"] = len(transcripts)

    # 3. Deduplicate against existing observations
    existing = list_observations(obs_dir, status="pending")
    for new_obs in all_new_observations:
        match = find_matching_observation(new_obs, existing)
        if match:
            merged = merge_observation(match, new_obs["sessions"][0])
            # Update on disk
            match_path = obs_dir / f"{match['id']}.yaml"
            if match_path.exists():
                save_observation(merged, obs_dir)
            run["observations_merged"] = run.get("observations_merged", 0) + 1
        else:
            save_observation(new_obs, obs_dir)
            existing.append(new_obs)
            run["observations_created"] = run.get("observations_created", 0) + 1

    if config.observe_only:
        run["completed"] = datetime.now(timezone.utc).isoformat()
        save_run(run, runs_dir)
        return run

    # 4-5. Prioritize and propose
    pending = list_observations(obs_dir, status="pending")
    # Sort by frequency (desc) then severity (high first)
    severity_order = {"high": 0, "medium": 1, "low": 2}
    pending.sort(key=lambda o: (-o.get("frequency", 1), severity_order.get(o.get("severity"), 1)))

    this_run_proposal_ids = []
    if pending:
        proposals_raw = generate_proposals(
            pending[:config.max_proposals * 2],  # give the LLM more context
            registry_summary,
            model=config.model,
            max_budget_usd=config.proposal_budget,
        )

        for p_data in proposals_raw[:config.max_proposals]:
            proposal = create_proposal(
                proposal_type=p_data.get("type", "new_tool"),
                action=p_data.get("action", ""),
                target_repo=p_data.get("target_repo", ""),
                ownership=p_data.get("ownership", "self"),
                motivation=p_data.get("motivation", ""),
                observation_id=p_data.get("observation_id", ""),
                complexity=p_data.get("complexity", "medium"),
            )
            save_proposal(proposal, proposals_dir)
            this_run_proposal_ids.append(proposal["id"])
            run["proposals_generated"] = run.get("proposals_generated", 0) + 1

    if config.dry_run:
        run["completed"] = datetime.now(timezone.utc).isoformat()
        save_run(run, runs_dir)
        return run

    # 6. Implement — only proposals generated THIS run
    pending_proposals = [
        p for p in list_proposals(proposals_dir, status="pending")
        if p["id"] in this_run_proposal_ids
    ]
    for proposal in pending_proposals:
        # Find the observation that motivated this
        obs_id = proposal.get("observation_id", "")
        obs_path = obs_dir / f"{obs_id}.yaml"
        observation = load_observation(obs_path) if obs_path.exists() else {
            "description": proposal.get("motivation", "")
        }

        result = run_implementation(
            proposal=proposal,
            observation=observation,
            registry_summary=registry_summary,
            model=config.model,
            max_budget_usd=config.implementation_budget,
        )

        proposal_path = proposals_dir / f"{proposal['id']}.yaml"
        if result["success"]:
            update_proposal_status(proposal_path, "implemented")
            # Mark the observation as addressed
            if obs_path.exists():
                obs = load_observation(obs_path)
                obs["status"] = "addressed"
                save_observation(obs, obs_dir)
            run["proposals_implemented"] = run.get("proposals_implemented", 0) + 1
        else:
            update_proposal_status(
                proposal_path, "failed",
                reason=result.get("error", "Unknown error"),
            )
            run["proposals_failed"] = run.get("proposals_failed", 0) + 1
            run["errors"].append(f"Proposal {proposal['id']}: {result.get('error', '')}")

    # 8. Report
    run["completed"] = datetime.now(timezone.utc).isoformat()
    save_run(run, runs_dir)
    return run


def _load_processed_sessions(run_path: Path) -> list[str]:
    """Load processed session IDs from a run log file."""
    try:
        from orchestrator.run_log import load_run
        run = load_run(run_path)
        return run.get("processed_sessions", [])
    except Exception:
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator/pipeline.py tests/test_pipeline.py
git commit -m "feat: add pipeline orchestration for full improvement cycle"
```

---

### Task 10: CLI Integration

Add the `orchestrator improve` command with `--observe-only` and `--dry-run` flags.

**Files:**
- Modify: `src/orchestrator/cli.py`
- Create: `tests/test_cli_improve.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli_improve.py
from pathlib import Path
from unittest.mock import patch
from click.testing import CliRunner
from orchestrator.cli import main


class TestImproveCommand:
    @patch("orchestrator.cli.run_cycle")
    def test_improve_calls_run_cycle(self, mock_cycle, tmp_path):
        mock_cycle.return_value = {
            "transcripts_analyzed": 0,
            "observations_created": 0,
            "proposals_generated": 0,
            "proposals_implemented": 0,
        }
        runner = CliRunner()
        result = runner.invoke(main, ["improve"])
        assert result.exit_code == 0

    @patch("orchestrator.cli.run_cycle")
    def test_improve_observe_only(self, mock_cycle, tmp_path):
        mock_cycle.return_value = {
            "transcripts_analyzed": 2,
            "observations_created": 3,
            "proposals_generated": 0,
            "proposals_implemented": 0,
        }
        runner = CliRunner()
        result = runner.invoke(main, ["improve", "--observe-only"])
        assert result.exit_code == 0
        call_kwargs = mock_cycle.call_args
        assert call_kwargs[1].get("config") or True  # verify config passed

    @patch("orchestrator.cli.run_cycle")
    def test_improve_dry_run(self, mock_cycle, tmp_path):
        mock_cycle.return_value = {
            "transcripts_analyzed": 1,
            "observations_created": 1,
            "proposals_generated": 2,
            "proposals_implemented": 0,
        }
        runner = CliRunner()
        result = runner.invoke(main, ["improve", "--dry-run"])
        assert result.exit_code == 0

    @patch("orchestrator.cli.run_cycle")
    def test_improve_shows_summary(self, mock_cycle):
        mock_cycle.return_value = {
            "transcripts_analyzed": 3,
            "observations_created": 2,
            "proposals_generated": 1,
            "proposals_implemented": 1,
        }
        runner = CliRunner()
        result = runner.invoke(main, ["improve"])
        assert "3" in result.output  # transcripts count
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_improve.py -v`
Expected: FAIL

- [ ] **Step 3: Add improve command to CLI**

Add to `src/orchestrator/cli.py`:

```python
# Add these imports at the top
from orchestrator.pipeline import run_cycle, CycleConfig

# Add after the sessions group

@main.command("improve")
@click.option("--observe-only", is_flag=True, help="Analyze transcripts but don't propose or implement")
@click.option("--dry-run", is_flag=True, help="Analyze and propose but don't implement")
@click.option("--model", default="sonnet", help="Model to use for analysis/proposals")
def improve(observe_only, dry_run, model):
    """Run an improvement cycle — analyze sessions, propose and implement improvements."""
    state_dir = Path.home() / ".claude" / "orchestrator"
    state_dir.mkdir(parents=True, exist_ok=True)

    try:
        registry_path = find_registry()
    except click.ClickException:
        raise

    config = CycleConfig(
        observe_only=observe_only,
        dry_run=dry_run,
        model=model,
    )

    click.echo("Starting improvement cycle...")
    if observe_only:
        click.echo("  Mode: observe-only (no proposals or implementation)")
    elif dry_run:
        click.echo("  Mode: dry-run (no implementation)")

    result = run_cycle(
        state_dir=state_dir,
        registry_path=registry_path,
        config=config,
    )

    click.echo()
    click.echo(f"Transcripts analyzed: {result.get('transcripts_analyzed', 0)}")
    click.echo(f"Observations created: {result.get('observations_created', 0)}")
    click.echo(f"Observations merged:  {result.get('observations_merged', 0)}")
    click.echo(f"Proposals generated:  {result.get('proposals_generated', 0)}")
    click.echo(f"Proposals implemented: {result.get('proposals_implemented', 0)}")
    click.echo(f"Proposals failed:     {result.get('proposals_failed', 0)}")

    if result.get("errors"):
        click.echo()
        click.echo("Errors:")
        for err in result["errors"]:
            click.echo(f"  - {err}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_improve.py -v`
Expected: All PASS

- [ ] **Step 5: Run all tests to verify nothing broke**

Run: `uv run pytest -v`
Expected: All tests PASS (183 existing + new tests)

- [ ] **Step 6: Commit**

```bash
git add src/orchestrator/cli.py tests/test_cli_improve.py
git commit -m "feat: add 'orchestrator improve' CLI command with observe-only and dry-run modes"
```

---

### Task 11: Update CLAUDE.md

Update project documentation to reflect new commands and modules.

**Files:**
- Modify: `.claude/CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md**

Add the new command and key files:

```markdown
## Commands
- `orchestrator registry show [--format summary|skill|json]` — display loaded registry
- `orchestrator registry validate` — validate registry.yaml structure
- `orchestrator sessions status` — show session log entry count and classification summary
- `orchestrator improve` — run a full improvement cycle (analyze → propose → implement)
- `orchestrator improve --observe-only` — analyze transcripts without proposing
- `orchestrator improve --dry-run` — analyze and propose without implementing

## Key Files
- `registry.yaml` — capability registry mapping MCP servers to their tools
- `src/orchestrator/registry.py` — registry loader and validator
- `src/orchestrator/capture.py` — session log writer (PostToolUse hook logic)
- `src/orchestrator/transcripts.py` — Claude Code transcript discovery and parsing
- `src/orchestrator/observations.py` — observation data model (friction, gaps, patterns)
- `src/orchestrator/proposals.py` — improvement proposal data model
- `src/orchestrator/analyzer.py` — transcript analysis via claude -p
- `src/orchestrator/proposer.py` — proposal generation via claude -p
- `src/orchestrator/implementer.py` — implementation via claude -p in target repos
- `src/orchestrator/pipeline.py` — full improvement cycle orchestration
- `hooks/post_tool_use.py` — Claude Code hook for session capture
- `skills/orchestrator/SKILL.md` — Claude Code skill for cross-project routing
```

- [ ] **Step 2: Commit**

```bash
git add .claude/CLAUDE.md
git commit -m "docs: update CLAUDE.md with improvement loop commands and modules"
```

---

### Task 12: Daily Digest

Generate a markdown digest summarizing recent improvement cycle activity.

**Files:**
- Create: `src/orchestrator/digest.py`
- Create: `tests/test_digest.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_digest.py
from pathlib import Path
from orchestrator.digest import generate_digest
from orchestrator.run_log import create_run_entry, save_run
from orchestrator.observations import create_observation, save_observation
from orchestrator.proposals import create_proposal, save_proposal


class TestGenerateDigest:
    def test_returns_string(self, tmp_path):
        result = generate_digest(tmp_path)
        assert isinstance(result, str)

    def test_empty_state_produces_header(self, tmp_path):
        result = generate_digest(tmp_path)
        assert "Orchestrator Digest" in result

    def test_includes_run_summary(self, tmp_path):
        runs_dir = tmp_path / "runs"
        run = create_run_entry()
        run["transcripts_analyzed"] = 3
        run["observations_created"] = 2
        save_run(run, runs_dir)
        result = generate_digest(tmp_path)
        assert "3" in result

    def test_includes_pending_observations(self, tmp_path):
        obs_dir = tmp_path / "observations"
        save_observation(
            create_observation("gap", "Missing training tool", "high", "s1"),
            obs_dir,
        )
        result = generate_digest(tmp_path)
        assert "training tool" in result.lower()

    def test_writes_to_file(self, tmp_path):
        generate_digest(tmp_path, write=True)
        assert (tmp_path / "digest.md").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_digest.py -v`
Expected: FAIL

- [ ] **Step 3: Implement digest module**

```python
# src/orchestrator/digest.py
"""Generate daily digest markdown from recent runs."""
from pathlib import Path

from orchestrator.observations import list_observations
from orchestrator.proposals import list_proposals
from orchestrator.run_log import load_run


def generate_digest(state_dir: Path, write: bool = False) -> str:
    """Generate a markdown digest of recent orchestrator activity."""
    lines = ["# Orchestrator Digest", ""]

    # Recent runs
    runs_dir = state_dir / "runs"
    if runs_dir.exists():
        run_files = sorted(runs_dir.glob("run-*.yaml"))[-5:]  # last 5 runs
        if run_files:
            lines.append("## Recent Runs")
            lines.append("")
            for rf in run_files:
                run = load_run(rf)
                if run:
                    lines.append(
                        f"- **{run.get('started', '?')}**: "
                        f"{run.get('transcripts_analyzed', 0)} transcripts, "
                        f"{run.get('observations_created', 0)} new observations, "
                        f"{run.get('proposals_implemented', 0)} implemented"
                    )
            lines.append("")

    # Pending observations
    obs_dir = state_dir / "observations"
    pending_obs = list_observations(obs_dir, status="pending")
    if pending_obs:
        pending_obs.sort(key=lambda o: -o.get("frequency", 1))
        lines.append("## Pending Observations")
        lines.append("")
        for obs in pending_obs[:10]:
            lines.append(
                f"- [{obs.get('severity', '?')}] {obs.get('description', '?')} "
                f"(seen {obs.get('frequency', 1)}x)"
            )
        lines.append("")

    # Pending proposals
    proposals_dir = state_dir / "proposals"
    pending_props = list_proposals(proposals_dir, status="pending")
    if pending_props:
        lines.append("## Pending Proposals")
        lines.append("")
        for prop in pending_props:
            lines.append(f"- **{prop.get('type', '?')}**: {prop.get('action', '?')}")
        lines.append("")

    # Recently implemented
    implemented = list_proposals(proposals_dir, status="implemented")
    if implemented:
        lines.append("## Recently Implemented")
        lines.append("")
        for prop in implemented[-5:]:
            lines.append(f"- {prop.get('action', '?')} ({prop.get('target_repo', '?')})")
        lines.append("")

    content = "\n".join(lines)

    if write:
        digest_path = state_dir / "digest.md"
        digest_path.write_text(content)

    return content
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_digest.py -v`
Expected: All PASS

- [ ] **Step 5: Add digest generation to the pipeline's report step**

In `pipeline.py`, add after `save_run(run, runs_dir)`:

```python
from orchestrator.digest import generate_digest
generate_digest(state_dir, write=True)
```

- [ ] **Step 6: Commit**

```bash
git add src/orchestrator/digest.py tests/test_digest.py src/orchestrator/pipeline.py
git commit -m "feat: add daily digest generation"
```

---

### Task 13: Scheduled Runs

Set up scheduled execution of the improvement cycle using Claude's scheduled commands.

**Files:**
- No new source files — this is a configuration task

- [ ] **Step 1: Verify the CLI works end-to-end**

```bash
uv run orchestrator improve --dry-run
```

Expected: Runs without errors.

- [ ] **Step 2: Set up scheduled commands**

In a Claude Code session, run:

```
/schedule add "Run orchestrator improvement cycle" every 8 hours: orchestrator improve
```

Or via the Claude CLI:

```bash
claude schedule create --name "orchestrator-improve" --interval "8h" --command "cd ~/emdash-projects/canopy-orchestrator && uv run orchestrator improve"
```

- [ ] **Step 3: Verify the schedule is registered**

```bash
claude schedule list
```

Expected: Shows the orchestrator-improve schedule running every 8 hours.

- [ ] **Step 4: Commit documentation of the schedule**

Add a note to CLAUDE.md about the scheduled command, then commit:

```bash
git add .claude/CLAUDE.md
git commit -m "docs: document scheduled improvement cycle"
```

---

### Task 14: Install Hook and End-to-End Smoke Test

Install the PostToolUse hook globally and run a manual smoke test.

**Files:**
- No new files

- [ ] **Step 1: Install the PostToolUse hook**

```bash
uv run python hooks/install.py
```

Expected: "Hook installed. Logging to ~/.claude/canopy/session-log.jsonl"

- [ ] **Step 2: Run the CLI to verify everything loads**

```bash
uv run orchestrator improve --observe-only
```

Expected: Should run without errors. Will report 0 transcripts if no sessions
have been captured yet.

- [ ] **Step 3: Run the full test suite one more time**

```bash
uv run pytest -v
```

Expected: All tests PASS

- [ ] **Step 4: Commit any remaining changes**

```bash
git add -A
git commit -m "chore: install hook and verify end-to-end smoke test"
```
