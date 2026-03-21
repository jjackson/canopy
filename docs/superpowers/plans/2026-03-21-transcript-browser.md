# Transcript Browser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a localhost web UI for browsing, labeling, and analyzing Claude Code session transcripts — grouped by GitHub repo with inline analysis and AI review.

**Architecture:** A Python HTTP server (`http.server`) serves a vanilla HTML/JS single-page app and JSON API endpoints. Data modules handle labels, repo mapping, and transcript scanning. The server reuses existing orchestrator modules (analyzer, proposer, observations, proposals) for analysis actions.

**Tech Stack:** Python 3.11+ (http.server, json), vanilla HTML/CSS/JS (no build step), existing orchestrator modules

**Spec:** `docs/superpowers/specs/2026-03-21-transcript-browser-design.md`

---

## File Structure

### New files

| File | Responsibility |
|---|---|
| `src/orchestrator/labels.py` | Load, save, and query transcript labels from `labels.yaml` |
| `src/orchestrator/repo_map.py` | Load, save, and query repo mappings from `repo-map.yaml` |
| `src/orchestrator/scanner.py` | Scan `~/.claude/projects/` for transcripts, extract metadata, group by repo |
| `src/orchestrator/reviewer.py` | AI strategic review via `claude -p` with product-thinking prompt |
| `src/orchestrator/server.py` | HTTP server with JSON API endpoints |
| `src/orchestrator/prompts/review.md` | Prompt template for AI strategic review |
| `src/orchestrator/static/index.html` | Single-page app (HTML + embedded CSS + JS) |
| `tests/test_labels.py` | Tests for labels module |
| `tests/test_repo_map.py` | Tests for repo mapping module |
| `tests/test_scanner.py` | Tests for transcript scanning |
| `tests/test_reviewer.py` | Tests for AI review prompt/parsing |
| `tests/test_server.py` | Tests for API endpoints |

### Modified files

| File | Change |
|---|---|
| `src/orchestrator/cli.py` | Add `serve` command |
| `hooks/post_tool_use.py` | Add repo mapping capture on first call per session |

---

### Task 1: Labels Module

Store and retrieve transcript labels.

**Files:**
- Create: `src/orchestrator/labels.py`
- Create: `tests/test_labels.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_labels.py
from pathlib import Path
import pytest
from orchestrator.labels import load_labels, save_label, get_label, QUALITY_VALUES


class TestQualityValues:
    def test_contains_expected_values(self):
        assert "unlabeled" in QUALITY_VALUES
        assert "went-well" in QUALITY_VALUES
        assert "had-friction" in QUALITY_VALUES
        assert "skip-coding" in QUALITY_VALUES
        assert "good-for-eval" in QUALITY_VALUES


class TestLoadLabels:
    def test_missing_file_returns_empty(self, tmp_path):
        assert load_labels(tmp_path / "labels.yaml") == {}

    def test_returns_dict(self, tmp_path):
        assert isinstance(load_labels(tmp_path / "labels.yaml"), dict)


class TestSaveAndGetLabel:
    def test_save_creates_file(self, tmp_path):
        path = tmp_path / "labels.yaml"
        save_label(path, "session-1", quality="went-well")
        assert path.exists()

    def test_round_trip_quality(self, tmp_path):
        path = tmp_path / "labels.yaml"
        save_label(path, "session-1", quality="had-friction")
        label = get_label(load_labels(path), "session-1")
        assert label["quality"] == "had-friction"

    def test_round_trip_tags(self, tmp_path):
        path = tmp_path / "labels.yaml"
        save_label(path, "session-1", use_case_tags=["salesforce", "research"])
        label = get_label(load_labels(path), "session-1")
        assert "salesforce" in label["use_case_tags"]

    def test_round_trip_notes(self, tmp_path):
        path = tmp_path / "labels.yaml"
        save_label(path, "session-1", notes="Good test case")
        label = get_label(load_labels(path), "session-1")
        assert label["notes"] == "Good test case"

    def test_round_trip_eval_candidate(self, tmp_path):
        path = tmp_path / "labels.yaml"
        save_label(path, "session-1", eval_candidate=True)
        label = get_label(load_labels(path), "session-1")
        assert label["eval_candidate"] is True

    def test_get_unlabeled_returns_defaults(self, tmp_path):
        path = tmp_path / "labels.yaml"
        label = get_label(load_labels(path), "nonexistent")
        assert label["quality"] == "unlabeled"
        assert label["use_case_tags"] == []
        assert label["notes"] == ""
        assert label["eval_candidate"] is False

    def test_update_preserves_other_fields(self, tmp_path):
        path = tmp_path / "labels.yaml"
        save_label(path, "s1", quality="went-well", notes="first note")
        save_label(path, "s1", quality="had-friction")
        label = get_label(load_labels(path), "s1")
        assert label["quality"] == "had-friction"
        assert label["notes"] == "first note"

    def test_multiple_sessions(self, tmp_path):
        path = tmp_path / "labels.yaml"
        save_label(path, "s1", quality="went-well")
        save_label(path, "s2", quality="disaster")
        labels = load_labels(path)
        assert get_label(labels, "s1")["quality"] == "went-well"
        assert get_label(labels, "s2")["quality"] == "disaster"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_labels.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement labels module**

```python
# src/orchestrator/labels.py
"""Load, save, and query transcript labels."""
from pathlib import Path

import yaml

QUALITY_VALUES = [
    "unlabeled", "went-well", "had-friction", "disaster",
    "skip-coding", "skip-setup", "good-for-eval",
]

DEFAULT_LABEL = {
    "quality": "unlabeled",
    "use_case_tags": [],
    "eval_candidate": False,
    "notes": "",
}


def load_labels(path: Path) -> dict:
    """Load all labels from a YAML file."""
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError:
        return {}


def save_label(
    path: Path,
    session_id: str,
    quality: str | None = None,
    use_case_tags: list[str] | None = None,
    eval_candidate: bool | None = None,
    notes: str | None = None,
) -> None:
    """Save or update a label for a session. Merges with existing data."""
    labels = load_labels(path)
    existing = labels.get(session_id, {**DEFAULT_LABEL})

    if quality is not None:
        existing["quality"] = quality
    if use_case_tags is not None:
        existing["use_case_tags"] = use_case_tags
    if eval_candidate is not None:
        existing["eval_candidate"] = eval_candidate
    if notes is not None:
        existing["notes"] = notes

    labels[session_id] = existing
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(labels, f, default_flow_style=False, sort_keys=False)


def get_label(labels: dict, session_id: str) -> dict:
    """Get label for a session, returning defaults if not found."""
    return labels.get(session_id, {**DEFAULT_LABEL})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_labels.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator/labels.py tests/test_labels.py
git commit -m "feat: add labels module for transcript metadata"
```

---

### Task 2: Repo Mapping Module

Store and retrieve project-directory-to-GitHub-repo mappings.

**Files:**
- Create: `src/orchestrator/repo_map.py`
- Create: `tests/test_repo_map.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_repo_map.py
from pathlib import Path
import pytest
from orchestrator.repo_map import (
    load_repo_map,
    save_repo_mapping,
    get_repo_for_project,
    extract_repo_from_git_url,
)


class TestExtractRepoFromGitUrl:
    def test_ssh_url(self):
        assert extract_repo_from_git_url("git@github.com:jjackson/connect-labs.git") == "jjackson/connect-labs"

    def test_https_url(self):
        assert extract_repo_from_git_url("https://github.com/jjackson/connect-labs.git") == "jjackson/connect-labs"

    def test_https_no_dot_git(self):
        assert extract_repo_from_git_url("https://github.com/jjackson/connect-labs") == "jjackson/connect-labs"

    def test_invalid_url_returns_none(self):
        assert extract_repo_from_git_url("not-a-url") is None

    def test_empty_returns_none(self):
        assert extract_repo_from_git_url("") is None


class TestLoadRepoMap:
    def test_missing_file_returns_empty(self, tmp_path):
        assert load_repo_map(tmp_path / "repo-map.yaml") == {}

    def test_returns_dict(self, tmp_path):
        assert isinstance(load_repo_map(tmp_path / "repo-map.yaml"), dict)


class TestSaveAndGet:
    def test_save_creates_file(self, tmp_path):
        path = tmp_path / "repo-map.yaml"
        save_repo_mapping(path, "-Users-jjackson-project", "jjackson/my-repo")
        assert path.exists()

    def test_round_trip(self, tmp_path):
        path = tmp_path / "repo-map.yaml"
        save_repo_mapping(path, "-Users-jjackson-project", "jjackson/my-repo")
        repo_map = load_repo_map(path)
        assert get_repo_for_project(repo_map, "-Users-jjackson-project") == "jjackson/my-repo"

    def test_unknown_project_returns_none(self, tmp_path):
        path = tmp_path / "repo-map.yaml"
        repo_map = load_repo_map(path)
        assert get_repo_for_project(repo_map, "unknown") is None

    def test_multiple_mappings(self, tmp_path):
        path = tmp_path / "repo-map.yaml"
        save_repo_mapping(path, "proj-a", "owner/repo-a")
        save_repo_mapping(path, "proj-b", "owner/repo-b")
        repo_map = load_repo_map(path)
        assert get_repo_for_project(repo_map, "proj-a") == "owner/repo-a"
        assert get_repo_for_project(repo_map, "proj-b") == "owner/repo-b"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_repo_map.py -v`
Expected: FAIL

- [ ] **Step 3: Implement repo_map module**

```python
# src/orchestrator/repo_map.py
"""Load, save, and query project-directory-to-GitHub-repo mappings."""
import re
from pathlib import Path

import yaml


def load_repo_map(path: Path) -> dict:
    """Load repo mappings from a YAML file."""
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError:
        return {}


def save_repo_mapping(path: Path, project_key: str, repo: str) -> None:
    """Save a single project-to-repo mapping."""
    repo_map = load_repo_map(path)
    repo_map[project_key] = repo
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(repo_map, f, default_flow_style=False, sort_keys=False)


def get_repo_for_project(repo_map: dict, project_key: str) -> str | None:
    """Look up the GitHub repo for a project directory key."""
    return repo_map.get(project_key)


def extract_repo_from_git_url(url: str) -> str | None:
    """Extract owner/repo from a GitHub git URL."""
    if not url:
        return None
    match = re.search(r"github\.com[:/]([^/]+/[^/\s]+?)(?:\.git)?$", url)
    return match.group(1) if match else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_repo_map.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator/repo_map.py tests/test_repo_map.py
git commit -m "feat: add repo mapping module for project-to-GitHub-repo lookups"
```

---

### Task 3: Transcript Scanner

Scan `~/.claude/projects/` for transcripts and extract metadata, grouped by repo.

**Files:**
- Create: `src/orchestrator/scanner.py`
- Create: `tests/test_scanner.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scanner.py
import json
from pathlib import Path
import pytest
from orchestrator.scanner import scan_transcript, scan_all_transcripts


FIXTURE = Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"


class TestScanTranscript:
    def test_returns_dict(self):
        result = scan_transcript(FIXTURE)
        assert isinstance(result, dict)

    def test_has_session_id(self):
        result = scan_transcript(FIXTURE)
        assert result["session_id"] == "test-session-001"

    def test_has_file_path(self):
        result = scan_transcript(FIXTURE)
        assert result["path"] == str(FIXTURE)

    def test_has_line_count(self):
        result = scan_transcript(FIXTURE)
        assert result["lines"] > 0

    def test_has_user_message_count(self):
        result = scan_transcript(FIXTURE)
        assert result["user_msgs"] > 0

    def test_has_first_message(self):
        result = scan_transcript(FIXTURE)
        assert "maternal health" in result["first_msg"].lower()

    def test_has_mcp_tools(self):
        result = scan_transcript(FIXTURE)
        assert "connect_search" in result["mcp_servers"]

    def test_has_mcp_call_count(self):
        result = scan_transcript(FIXTURE)
        assert result["mcp_call_count"] >= 2

    def test_has_timestamps(self):
        result = scan_transcript(FIXTURE)
        assert result["first_ts"] is not None
        assert result["last_ts"] is not None

    def test_has_project_key(self):
        result = scan_transcript(FIXTURE)
        assert "project_key" in result


class TestScanAllTranscripts:
    def test_returns_list(self, tmp_path):
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        result = scan_all_transcripts(projects_dir)
        assert isinstance(result, list)

    def test_finds_transcripts(self, tmp_path):
        projects_dir = tmp_path / "projects"
        proj = projects_dir / "-test-project"
        proj.mkdir(parents=True)
        # Copy fixture
        import shutil
        shutil.copy(FIXTURE, proj / "abc123.jsonl")
        result = scan_all_transcripts(projects_dir)
        assert len(result) == 1

    def test_skips_non_jsonl(self, tmp_path):
        projects_dir = tmp_path / "projects"
        proj = projects_dir / "-test-project"
        proj.mkdir(parents=True)
        (proj / "not-a-transcript.txt").write_text("hello")
        result = scan_all_transcripts(projects_dir)
        assert len(result) == 0

    def test_includes_repo_from_map(self, tmp_path):
        projects_dir = tmp_path / "projects"
        proj = projects_dir / "-test-project"
        proj.mkdir(parents=True)
        import shutil
        shutil.copy(FIXTURE, proj / "abc123.jsonl")
        repo_map = {"-test-project": "owner/my-repo"}
        result = scan_all_transcripts(projects_dir, repo_map=repo_map)
        assert result[0]["repo"] == "owner/my-repo"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scanner.py -v`
Expected: FAIL

- [ ] **Step 3: Implement scanner module**

```python
# src/orchestrator/scanner.py
"""Scan ~/.claude/projects/ for transcripts and extract metadata."""
import json
from pathlib import Path

from orchestrator.transcripts import read_transcript, get_session_id


def scan_transcript(path: Path) -> dict:
    """Extract metadata from a single transcript file."""
    entries = read_transcript(path)
    project_key = path.parent.name

    # Count lines (raw, not filtered)
    line_count = sum(1 for _ in open(path))

    # Extract metadata
    user_msgs = 0
    first_msg = ""
    first_ts = None
    last_ts = None
    mcp_servers = set()
    mcp_call_count = 0

    for entry in entries:
        ts = entry.get("timestamp")
        if ts:
            if first_ts is None or ts < first_ts:
                first_ts = ts
            if last_ts is None or ts > last_ts:
                last_ts = ts

        if entry.get("type") == "user":
            msg = entry.get("message", {})
            if isinstance(msg, dict):
                content = msg.get("content", "")
                if isinstance(content, str) and content:
                    user_msgs += 1
                    if not first_msg:
                        first_msg = content[:100]

        elif entry.get("type") == "assistant":
            msg = entry.get("message", {})
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        name = block.get("name", "")
                        if name.startswith("mcp__"):
                            parts = name.split("__", 2)
                            if len(parts) >= 2:
                                mcp_servers.add(parts[1])
                            mcp_call_count += 1

    session_id = get_session_id(entries) or path.stem

    return {
        "session_id": session_id,
        "path": str(path),
        "project_key": project_key,
        "lines": line_count,
        "user_msgs": user_msgs,
        "first_msg": first_msg,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "mcp_servers": sorted(mcp_servers),
        "mcp_call_count": mcp_call_count,
    }


def scan_all_transcripts(
    projects_dir: Path,
    repo_map: dict | None = None,
    labels: dict | None = None,
) -> list[dict]:
    """Scan all transcript files under projects_dir."""
    repo_map = repo_map or {}
    labels = labels or {}
    results = []

    if not projects_dir.exists():
        return results

    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        for jsonl in sorted(project_dir.glob("*.jsonl")):
            try:
                meta = scan_transcript(jsonl)
                meta["repo"] = repo_map.get(project_dir.name)
                meta["label"] = labels.get(meta["session_id"], {
                    "quality": "unlabeled",
                    "use_case_tags": [],
                    "eval_candidate": False,
                    "notes": "",
                })
                results.append(meta)
            except Exception:
                continue

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scanner.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator/scanner.py tests/test_scanner.py
git commit -m "feat: add transcript scanner with metadata extraction"
```

---

### Task 4: AI Review Prompt and Module

Build the strategic review module that applies product-thinking to transcripts.

**Files:**
- Create: `src/orchestrator/prompts/review.md`
- Create: `src/orchestrator/reviewer.py`
- Create: `tests/test_reviewer.py`

- [ ] **Step 1: Create the review prompt template**

```markdown
# src/orchestrator/prompts/review.md
You are a product strategist reviewing a Claude Code session transcript.
Go beyond finding bugs — think about what should be built next.

## Context

The user has these MCP servers available:
{registry_summary}

## Transcript

{transcript_text}

## Instructions

Analyze this session as a product manager and strategic advisor would.
Answer these questions:

1. **Intent**: What was the user really trying to accomplish? Not the
   literal task, but the underlying goal.

2. **Highest-leverage improvement**: If you could only build one thing
   to make this session go better, what would it be? Be specific.

3. **Missed opportunities**: Were there tools, approaches, or workflows
   that weren't considered but could have helped?

4. **Automation candidates**: What parts of this session were repetitive
   enough to automate as a workflow or tool?

5. **Strategic recommendation**: Zooming out — what does this session
   tell you about what the user's ecosystem is missing?

Write your analysis as clear, concise markdown. Be opinionated — give
specific recommendations, not vague suggestions.
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_reviewer.py
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from orchestrator.reviewer import (
    build_review_prompt,
    run_review,
    save_review,
    load_review,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"


class TestBuildReviewPrompt:
    def test_returns_string(self):
        prompt = build_review_prompt(FIXTURE, registry_summary="test")
        assert isinstance(prompt, str)

    def test_includes_registry(self):
        prompt = build_review_prompt(FIXTURE, registry_summary="## Server: connect-search")
        assert "connect-search" in prompt

    def test_includes_strategic_questions(self):
        prompt = build_review_prompt(FIXTURE, registry_summary="test")
        assert "highest-leverage" in prompt.lower()


class TestRunReview:
    @patch("orchestrator.reviewer.subprocess.run")
    def test_returns_string_on_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="## Analysis\nGreat session.")
        result = run_review(FIXTURE, "test registry")
        assert "Great session" in result

    @patch("orchestrator.reviewer.subprocess.run")
    def test_returns_none_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = run_review(FIXTURE, "test registry")
        assert result is None

    @patch("orchestrator.reviewer.subprocess.run")
    def test_returns_none_on_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=120)
        result = run_review(FIXTURE, "test registry")
        assert result is None


class TestSaveLoadReview:
    def test_round_trip(self, tmp_path):
        save_review(tmp_path, "session-1", "## Analysis\nGreat session.")
        loaded = load_review(tmp_path, "session-1")
        assert "Great session" in loaded

    def test_load_missing_returns_none(self, tmp_path):
        assert load_review(tmp_path, "nonexistent") is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_reviewer.py -v`
Expected: FAIL

- [ ] **Step 4: Implement reviewer module**

```python
# src/orchestrator/reviewer.py
"""AI strategic review of transcripts via claude -p."""
import subprocess
from pathlib import Path

import yaml

from orchestrator.prompts import load_prompt
from orchestrator.transcripts import read_transcript


def build_review_prompt(transcript_path: Path, registry_summary: str) -> str:
    """Build the review prompt using the same transcript rendering as analyze."""
    import json
    entries = read_transcript(transcript_path)

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
                            parts.append(f"TOOL CALL: {block['name']}({json.dumps(block.get('input', {}))})")

    transcript_text = "\n".join(parts)
    return load_prompt("review", registry_summary=registry_summary, transcript_text=transcript_text)


def run_review(
    transcript_path: Path,
    registry_summary: str,
    model: str = "sonnet",
    max_budget_usd: float = 1.00,
) -> str | None:
    """Run a strategic AI review. Returns markdown string or None on failure."""
    prompt = build_review_prompt(transcript_path, registry_summary)

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
        return None

    if result.returncode != 0:
        return None

    return result.stdout


def save_review(reviews_dir: Path, session_id: str, content: str) -> Path:
    """Save an AI review to disk."""
    reviews_dir.mkdir(parents=True, exist_ok=True)
    path = reviews_dir / f"{session_id}.yaml"
    with open(path, "w") as f:
        yaml.dump({"session_id": session_id, "content": content}, f,
                  default_flow_style=False, sort_keys=False)
    return path


def load_review(reviews_dir: Path, session_id: str) -> str | None:
    """Load an AI review from disk. Returns the markdown content or None."""
    path = reviews_dir / f"{session_id}.yaml"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        return data.get("content") if data else None
    except yaml.YAMLError:
        return None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_reviewer.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/orchestrator/prompts/review.md src/orchestrator/reviewer.py tests/test_reviewer.py
git commit -m "feat: add AI strategic review with product-thinking prompt"
```

---

### Task 5: HTTP Server and API

Build the server with JSON API endpoints.

**Files:**
- Create: `src/orchestrator/server.py`
- Create: `tests/test_server.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_server.py
import json
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from orchestrator.server import create_app, get_transcripts, save_label_data

FIXTURE = Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"


@pytest.fixture
def app_dirs(tmp_path):
    """Set up directory structure for the server."""
    projects_dir = tmp_path / "projects" / "-test-project"
    projects_dir.mkdir(parents=True)
    shutil.copy(FIXTURE, projects_dir / "test-session-001.jsonl")

    state_dir = tmp_path / "orchestrator"
    state_dir.mkdir()

    return {
        "projects_dir": tmp_path / "projects",
        "state_dir": state_dir,
        "registry_path": Path(__file__).parent / "fixtures" / "sample_registry.yaml",
    }


class TestCreateApp:
    def test_returns_handler_class(self, app_dirs):
        handler = create_app(**app_dirs)
        assert handler is not None


class TestGetTranscripts:
    def test_returns_list(self, app_dirs):
        result = get_transcripts(app_dirs["projects_dir"], app_dirs["state_dir"])
        assert isinstance(result, list)

    def test_finds_fixture_transcript(self, app_dirs):
        result = get_transcripts(app_dirs["projects_dir"], app_dirs["state_dir"])
        assert len(result) >= 1

    def test_transcript_has_metadata(self, app_dirs):
        result = get_transcripts(app_dirs["projects_dir"], app_dirs["state_dir"])
        t = result[0]
        assert "session_id" in t
        assert "lines" in t
        assert "user_msgs" in t
        assert "first_msg" in t


class TestSaveLabels:
    def test_save_and_retrieve(self, app_dirs):
        save_label_data(app_dirs["state_dir"], "test-session-001", {
            "quality": "had-friction",
            "use_case_tags": ["test"],
            "eval_candidate": True,
            "notes": "test note",
        })
        transcripts = get_transcripts(app_dirs["projects_dir"], app_dirs["state_dir"])
        t = [t for t in transcripts if t["session_id"] == "test-session-001"][0]
        assert t["label"]["quality"] == "had-friction"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_server.py -v`
Expected: FAIL

- [ ] **Step 3: Implement server module**

```python
# src/orchestrator/server.py
"""HTTP server with JSON API for the transcript browser."""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from orchestrator.labels import load_labels, save_label, get_label
from orchestrator.repo_map import load_repo_map, save_repo_mapping
from orchestrator.scanner import scan_all_transcripts, scan_transcript
from orchestrator.observations import (
    list_observations, create_observation, save_observation,
    find_matching_observation, merge_observation,
)
from orchestrator.proposals import list_proposals, create_proposal, save_proposal
from orchestrator.reviewer import load_review


def get_transcripts(projects_dir: Path, state_dir: Path) -> list[dict]:
    """Get all transcripts with labels and repo mapping."""
    labels = load_labels(state_dir / "labels.yaml")
    repo_map = load_repo_map(state_dir / "repo-map.yaml")
    return scan_all_transcripts(projects_dir, repo_map=repo_map, labels=labels)


def save_label_data(state_dir: Path, session_id: str, data: dict) -> None:
    """Save label data for a session."""
    save_label(
        state_dir / "labels.yaml",
        session_id,
        quality=data.get("quality"),
        use_case_tags=data.get("use_case_tags"),
        eval_candidate=data.get("eval_candidate"),
        notes=data.get("notes"),
    )


def create_app(
    projects_dir: Path,
    state_dir: Path,
    registry_path: Path,
):
    """Create an HTTP request handler class with the given configuration."""

    class AppHandler(BaseHTTPRequestHandler):

        def _get_transcripts(self):
            return get_transcripts(projects_dir, state_dir)

        def _save_label(self, session_id, data):
            save_label_data(state_dir, session_id, data)

        def _send_json(self, data, status=200):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data, default=str).encode())

        def _read_body(self):
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                return {}
            return json.loads(self.rfile.read(length))

        def _parse_path(self):
            return urlparse(self.path).path.rstrip("/")

        def do_GET(self):
            path = self._parse_path()

            if path == "" or path == "/":
                self._serve_static()
            elif path == "/api/transcripts":
                self._send_json(self._get_transcripts())
            elif path.startswith("/api/transcript/"):
                session_id = path.split("/")[-1]
                self._handle_get_transcript(session_id)
            else:
                self.send_error(404)

        def do_POST(self):
            path = self._parse_path()

            if path.startswith("/api/labels/"):
                session_id = path.split("/")[-1]
                data = self._read_body()
                self._save_label(session_id, data)
                self._send_json({"ok": True})
            elif path.startswith("/api/analyze/"):
                session_id = path.split("/")[-1]
                self._handle_analyze(session_id)
            elif path.startswith("/api/propose/"):
                session_id = path.split("/")[-1]
                self._handle_propose(session_id)
            elif path.startswith("/api/review/"):
                session_id = path.split("/")[-1]
                self._handle_review(session_id)
            elif path.startswith("/api/repo-map/"):
                project_key = path.split("/")[-1]
                data = self._read_body()
                save_repo_mapping(
                    state_dir / "repo-map.yaml",
                    project_key,
                    data.get("repo", ""),
                )
                self._send_json({"ok": True})
            else:
                self.send_error(404)

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def _serve_static(self):
            static_path = Path(__file__).parent / "static" / "index.html"
            if not static_path.exists():
                self.send_error(404, "index.html not found")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(static_path.read_bytes())

        def _handle_get_transcript(self, session_id):
            from orchestrator.transcripts import read_transcript
            # Find the transcript file
            for project_dir in projects_dir.iterdir():
                if not project_dir.is_dir():
                    continue
                for jsonl in project_dir.glob("*.jsonl"):
                    if jsonl.stem == session_id:
                        entries = read_transcript(jsonl)
                        self._send_json(entries)
                        return
            self.send_error(404, "Transcript not found")

        def _handle_analyze(self, session_id):
            from orchestrator.analyzer import analyze_transcript
            from orchestrator.registry import load_registry, format_for_skill

            transcript_path = self._find_transcript(session_id)
            if not transcript_path:
                self._send_json({"error": "Transcript not found"}, 404)
                return

            registry = load_registry(registry_path)
            registry_summary = format_for_skill(registry)
            observations = analyze_transcript(transcript_path, registry_summary)

            # Save observations with deduplication
            obs_dir = state_dir / "observations"
            existing = list_observations(obs_dir, status="pending")
            saved = []
            for obs_data in observations:
                obs = create_observation(
                    obs_type=obs_data.get("type", "gap"),
                    description=obs_data.get("description", ""),
                    severity=obs_data.get("severity", "medium"),
                    session_id=session_id,
                    related_servers=obs_data.get("related_servers", []),
                    lifecycle_stage=obs_data.get("lifecycle_stage"),
                )
                match = find_matching_observation(obs, existing)
                if match:
                    merged = merge_observation(match, session_id)
                    save_observation(merged, obs_dir)
                    saved.append(merged)
                else:
                    save_observation(obs, obs_dir)
                    existing.append(obs)
                    saved.append(obs)

            self._send_json(saved)

        def _handle_propose(self, session_id):
            from orchestrator.proposer import generate_proposals
            from orchestrator.registry import load_registry, format_for_skill

            # Find observations for this session
            obs_dir = state_dir / "observations"
            all_obs = list_observations(obs_dir, status="pending")
            session_obs = [o for o in all_obs if session_id in o.get("sessions", [])]

            if not session_obs:
                self._send_json({"error": "No observations found. Run Analyze first."}, 400)
                return

            registry = load_registry(registry_path)
            registry_summary = format_for_skill(registry)
            proposals_raw = generate_proposals(session_obs, registry_summary)

            proposals_dir = state_dir / "proposals"
            saved = []
            for p_data in proposals_raw:
                proposal = create_proposal(
                    proposal_type=p_data.get("type", "new_tool"),
                    action=p_data.get("action", ""),
                    target_repo=p_data.get("target_repo", ""),
                    ownership=p_data.get("ownership", "self"),
                    motivation=p_data.get("motivation", ""),
                    observation_id=p_data.get("observation_id", ""),
                    complexity=p_data.get("complexity", "medium"),
                    verification=p_data.get("verification"),
                )
                save_proposal(proposal, proposals_dir)
                saved.append(proposal)

            self._send_json(saved)

        def _handle_review(self, session_id):
            from orchestrator.reviewer import run_review, save_review
            from orchestrator.registry import load_registry, format_for_skill

            transcript_path = self._find_transcript(session_id)
            if not transcript_path:
                self._send_json({"error": "Transcript not found"}, 404)
                return

            registry = load_registry(registry_path)
            registry_summary = format_for_skill(registry)
            content = run_review(transcript_path, registry_summary)

            if content is None:
                self._send_json({"error": "Review failed"}, 500)
                return

            reviews_dir = state_dir / "ai-reviews"
            save_review(reviews_dir, session_id, content)
            self._send_json({"content": content})

        def _find_transcript(self, session_id):
            for project_dir in projects_dir.iterdir():
                if not project_dir.is_dir():
                    continue
                for jsonl in project_dir.glob("*.jsonl"):
                    if jsonl.stem == session_id:
                        return jsonl
            return None

        def log_message(self, format, *args):
            print(f"[server] {args[0] if args else ''}")

    return AppHandler


def run_server(
    projects_dir: Path,
    state_dir: Path,
    registry_path: Path,
    port: int = 8484,
):
    """Start the transcript browser server."""
    handler = create_app(projects_dir, state_dir, registry_path)
    server = HTTPServer(("127.0.0.1", port), handler)
    print(f"Transcript browser running at http://localhost:{port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.shutdown()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_server.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator/server.py tests/test_server.py
git commit -m "feat: add HTTP server with JSON API for transcript browser"
```

---

### Task 6: Frontend SPA

Build the single-page HTML/CSS/JS app that the server serves.

**Files:**
- Create: `src/orchestrator/static/index.html`

- [ ] **Step 1: Create the static directory**

```bash
mkdir -p src/orchestrator/static
```

- [ ] **Step 2: Create index.html**

This is a single HTML file with embedded CSS and JS. It calls the API endpoints
and renders the transcript list grouped by repo with expandable detail views.

The file should implement:
- Fetch `/api/transcripts` on load
- Group transcripts by `repo` field (null repos go to "Unmapped")
- Render collapsible repo groups with sessions listed newest-first
- Each session row shows: date, first message preview, line count, MCP info
- Clicking a row expands to show: stats, tool usage, actions (Analyze, AI Review), labels
- Analyze button POSTs to `/api/analyze/:id` and shows results inline
- AI Review button POSTs to `/api/review/:id` and shows results inline
- Label controls POST to `/api/labels/:id` on change
- Full Transcript button fetches `/api/transcript/:id` and renders chat log
- Filter bar: Has MCP | Labeled | Unlabeled
- Dark theme matching the GitHub dark style from the mockups
- Repo assignment for unmapped sessions via `/api/repo-map/:project_key`

The HTML file should be self-contained — all CSS and JS inline, no external
dependencies.

NOTE: This file will be large (500+ lines). The implementer should create a
complete, working SPA. Use the mockups from the brainstorm session
(`.superpowers/brainstorm/`) as visual reference for the dark theme styling.

- [ ] **Step 3: Test manually**

```bash
uv run orchestrator serve
```

Open http://localhost:8484 in a browser. Verify:
- Transcripts load and display grouped by repo
- Clicking a session expands the detail view
- Labels can be saved
- Filter bar works

- [ ] **Step 4: Commit**

```bash
git add src/orchestrator/static/index.html
git commit -m "feat: add frontend SPA for transcript browser"
```

---

### Task 7: CLI Integration

Add the `serve` command to the CLI.

**Files:**
- Modify: `src/orchestrator/cli.py`

- [ ] **Step 1: Add serve command**

Add to `src/orchestrator/cli.py`:

```python
from orchestrator.server import run_server

@main.command("serve")
@click.option("--port", default=8484, type=int, help="Port to serve on")
def serve(port):
    """Start the transcript browser web UI."""
    state_dir = Path.home() / ".claude" / "orchestrator"
    state_dir.mkdir(parents=True, exist_ok=True)
    projects_dir = Path.home() / ".claude" / "projects"

    try:
        registry_path = find_registry()
    except click.ClickException:
        raise

    run_server(
        projects_dir=projects_dir,
        state_dir=state_dir,
        registry_path=registry_path,
        port=port,
    )
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add src/orchestrator/cli.py
git commit -m "feat: add 'orchestrator serve' CLI command for transcript browser"
```

---

### Task 8: Update PostToolUse Hook for Repo Mapping

Capture `git remote get-url origin` on first MCP call per project.

**Files:**
- Modify: `hooks/post_tool_use.py`

- [ ] **Step 1: Read the existing hook**

Read `hooks/post_tool_use.py` to understand current structure.

- [ ] **Step 2: Add repo mapping logic**

After the existing MCP detection logic, add:

```python
# Capture repo mapping on first call per project
REPO_MAP_FILE = Path.home() / ".claude" / "orchestrator" / "repo-map.yaml"

def maybe_capture_repo(project_dir: str):
    """Capture git remote → repo mapping if not already known."""
    import subprocess
    try:
        import yaml
    except ImportError:
        return

    project_key = project_dir.lstrip("/").replace("/", "-")
    project_key = f"-{project_key}"

    # Check if already mapped
    repo_map = {}
    if REPO_MAP_FILE.exists():
        try:
            with open(REPO_MAP_FILE) as f:
                repo_map = yaml.safe_load(f) or {}
        except Exception:
            return

    if project_key in repo_map:
        return

    # Try to get git remote
    try:
        result = subprocess.run(
            ["git", "-C", project_dir, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode != 0:
            return
        url = result.stdout.strip()
    except Exception:
        return

    # Extract owner/repo
    import re
    match = re.search(r"github\.com[:/]([^/]+/[^/\s]+?)(?:\.git)?$", url)
    if not match:
        return

    repo_map[project_key] = match.group(1)
    REPO_MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REPO_MAP_FILE, "w") as f:
        yaml.dump(repo_map, f, default_flow_style=False, sort_keys=False)
```

Call `maybe_capture_repo(project_dir)` in `main()` before `append_log_entry()`.

- [ ] **Step 3: Run all tests**

Run: `uv run pytest -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add hooks/post_tool_use.py
git commit -m "feat: capture git repo mapping in PostToolUse hook"
```

---

### Task 9: Update CLAUDE.md and Smoke Test

**Files:**
- Modify: `.claude/CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md**

Add to Commands section:
```
- `orchestrator serve` — start transcript browser web UI on localhost:8484
```

Add to Key Files section:
```
- `src/orchestrator/server.py` — HTTP server for transcript browser
- `src/orchestrator/scanner.py` — transcript discovery and metadata extraction
- `src/orchestrator/labels.py` — transcript label storage
- `src/orchestrator/repo_map.py` — project-to-GitHub-repo mapping
- `src/orchestrator/reviewer.py` — AI strategic review via claude -p
- `src/orchestrator/static/index.html` — transcript browser frontend
```

- [ ] **Step 2: Run smoke test**

```bash
uv run orchestrator serve &
sleep 2
curl -s http://localhost:8484/api/transcripts | python3 -m json.tool | head -20
kill %1
```

Expected: JSON array of transcript metadata objects.

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest -v
```

Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add .claude/CLAUDE.md
git commit -m "docs: update CLAUDE.md with transcript browser commands and modules"
```
