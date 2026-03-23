# Phase 2A: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the pipeline's current gaps and add the skill runner infrastructure that enables autonomous convergence with gstack/superpowers.

**Architecture:** Five foundational improvements to the existing pipeline: (1) wire the scanner into the pipeline for direct transcript discovery, (2) add circuit breaker to prevent runaway failures, (3) add rate limiting for API cost control, (4) capture literal test evidence in implementation results, (5) build the autonomous skill runner that invokes any Claude Code skill headlessly via slash commands.

**Tech Stack:** Python 3.11+, subprocess (for `claude -p`), existing orchestrator modules, no new dependencies

**Spec:** `docs/superpowers/specs/2026-03-22-autonomous-convergence-ceo-plan.md`

---

## File Structure

### New files

| File | Responsibility |
|---|---|
| `src/orchestrator/skill_runner.py` | Invoke any Claude Code skill headlessly via slash commands with auto-select |
| `src/orchestrator/circuit_breaker.py` | Track consecutive failures, stop after threshold, log why |
| `src/orchestrator/rate_limiter.py` | Track API calls per hour, enforce configurable limit |
| `tests/test_skill_runner.py` | Tests for skill runner |
| `tests/test_circuit_breaker.py` | Tests for circuit breaker |
| `tests/test_rate_limiter.py` | Tests for rate limiter |

### Modified files

| File | Change |
|---|---|
| `src/orchestrator/pipeline.py` | Wire scanner for discovery, add circuit breaker + rate limiter |
| `src/orchestrator/implementer.py` | Capture evidence (literal test output) in results |

---

### Task 1: Circuit Breaker

Track consecutive failures and stop the pipeline after a threshold.

**Files:**
- Create: `src/orchestrator/circuit_breaker.py`
- Create: `tests/test_circuit_breaker.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_circuit_breaker.py
import pytest
from orchestrator.circuit_breaker import CircuitBreaker


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(max_failures=3)
        assert cb.is_open is False

    def test_stays_closed_after_one_failure(self):
        cb = CircuitBreaker(max_failures=3)
        cb.record_failure("test error")
        assert cb.is_open is False

    def test_opens_after_max_failures(self):
        cb = CircuitBreaker(max_failures=3)
        cb.record_failure("error 1")
        cb.record_failure("error 2")
        cb.record_failure("error 3")
        assert cb.is_open is True

    def test_success_resets_counter(self):
        cb = CircuitBreaker(max_failures=3)
        cb.record_failure("error 1")
        cb.record_failure("error 2")
        cb.record_success()
        cb.record_failure("error 3")
        assert cb.is_open is False

    def test_tracks_failure_reasons(self):
        cb = CircuitBreaker(max_failures=3)
        cb.record_failure("timeout")
        cb.record_failure("parse error")
        assert len(cb.recent_failures) == 2
        assert "timeout" in cb.recent_failures

    def test_reason_when_open(self):
        cb = CircuitBreaker(max_failures=2)
        cb.record_failure("error A")
        cb.record_failure("error B")
        assert "error A" in cb.open_reason
        assert "error B" in cb.open_reason

    def test_consecutive_count(self):
        cb = CircuitBreaker(max_failures=3)
        cb.record_failure("a")
        cb.record_failure("b")
        assert cb.consecutive_failures == 2

    def test_reset(self):
        cb = CircuitBreaker(max_failures=2)
        cb.record_failure("a")
        cb.record_failure("b")
        cb.reset()
        assert cb.is_open is False
        assert cb.consecutive_failures == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_circuit_breaker.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement circuit breaker**

```python
# src/orchestrator/circuit_breaker.py
"""Circuit breaker: stops pipeline after consecutive failures."""


class CircuitBreaker:
    """Track consecutive failures and trip after threshold.

    Inspired by Citadel's pattern: after N consecutive failures,
    stop and try a different approach rather than retrying.
    """

    def __init__(self, max_failures: int = 3):
        self.max_failures = max_failures
        self.consecutive_failures = 0
        self.recent_failures: list[str] = []

    @property
    def is_open(self) -> bool:
        return self.consecutive_failures >= self.max_failures

    @property
    def open_reason(self) -> str:
        return "; ".join(self.recent_failures[-self.max_failures:])

    def record_failure(self, reason: str) -> None:
        self.consecutive_failures += 1
        self.recent_failures.append(reason)

    def record_success(self) -> None:
        self.consecutive_failures = 0

    def reset(self) -> None:
        self.consecutive_failures = 0
        self.recent_failures.clear()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_circuit_breaker.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator/circuit_breaker.py tests/test_circuit_breaker.py
git commit -m "feat: add circuit breaker — stops pipeline after consecutive failures"
```

---

### Task 2: Rate Limiter

Track API calls per hour and enforce a configurable limit.

**Files:**
- Create: `src/orchestrator/rate_limiter.py`
- Create: `tests/test_rate_limiter.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_rate_limiter.py
import time
import pytest
from orchestrator.rate_limiter import RateLimiter


class TestRateLimiter:
    def test_allows_first_call(self):
        rl = RateLimiter(max_calls_per_hour=10)
        assert rl.can_proceed() is True

    def test_tracks_calls(self):
        rl = RateLimiter(max_calls_per_hour=10)
        rl.record_call()
        assert rl.calls_this_hour == 1

    def test_blocks_after_limit(self):
        rl = RateLimiter(max_calls_per_hour=3)
        rl.record_call()
        rl.record_call()
        rl.record_call()
        assert rl.can_proceed() is False

    def test_remaining(self):
        rl = RateLimiter(max_calls_per_hour=5)
        rl.record_call()
        rl.record_call()
        assert rl.remaining == 3

    def test_old_calls_expire(self):
        rl = RateLimiter(max_calls_per_hour=2)
        # Manually inject an old timestamp
        rl._timestamps.append(time.time() - 3700)  # > 1 hour ago
        rl._cleanup()
        assert rl.calls_this_hour == 0

    def test_summary(self):
        rl = RateLimiter(max_calls_per_hour=10)
        rl.record_call()
        summary = rl.summary()
        assert "1" in summary
        assert "10" in summary
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rate_limiter.py -v`
Expected: FAIL

- [ ] **Step 3: Implement rate limiter**

```python
# src/orchestrator/rate_limiter.py
"""Rate limiter: caps API calls per hour to prevent runaway spend."""
import time


class RateLimiter:
    """Track API calls and enforce a per-hour limit.

    Inspired by Super-Ralph's rate limiting pattern.
    """

    def __init__(self, max_calls_per_hour: int = 30):
        self.max_calls_per_hour = max_calls_per_hour
        self._timestamps: list[float] = []

    def _cleanup(self) -> None:
        """Remove timestamps older than 1 hour."""
        cutoff = time.time() - 3600
        self._timestamps = [t for t in self._timestamps if t > cutoff]

    @property
    def calls_this_hour(self) -> int:
        self._cleanup()
        return len(self._timestamps)

    @property
    def remaining(self) -> int:
        return max(0, self.max_calls_per_hour - self.calls_this_hour)

    def can_proceed(self) -> bool:
        return self.calls_this_hour < self.max_calls_per_hour

    def record_call(self) -> None:
        self._timestamps.append(time.time())

    def summary(self) -> str:
        return f"{self.calls_this_hour}/{self.max_calls_per_hour} calls this hour ({self.remaining} remaining)"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rate_limiter.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator/rate_limiter.py tests/test_rate_limiter.py
git commit -m "feat: add rate limiter — caps API calls per hour"
```

---

### Task 3: Evidence-Based Verification

Update the implementer to capture literal test output (not just exit codes).

**Files:**
- Modify: `src/orchestrator/implementer.py`
- Modify: `tests/test_implementer.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_implementer.py`:

```python
class TestEvidenceCapture:
    @patch("orchestrator.implementer.subprocess.run")
    def test_success_result_includes_evidence(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="All 15 tests passed\n\nImplementation complete.",
            stderr="",
        )
        result = run_implementation(
            proposal={"type": "new_tool", "action": "test", "target_repo": str(tmp_path), "ownership": "self"},
            observation={"type": "gap", "description": "test"},
            registry_summary="test",
        )
        assert "evidence" in result
        assert "15 tests passed" in result["evidence"]

    @patch("orchestrator.implementer.subprocess.run")
    def test_failure_result_includes_evidence(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="3 tests failed:\n  test_foo FAILED\n  test_bar FAILED",
            stderr="Error: tests did not pass",
        )
        result = run_implementation(
            proposal={"type": "new_tool", "action": "test", "target_repo": str(tmp_path), "ownership": "self"},
            observation={"type": "gap", "description": "test"},
            registry_summary="test",
        )
        assert "evidence" in result
        assert "3 tests failed" in result["evidence"]

    @patch("orchestrator.implementer.subprocess.run")
    def test_evidence_captures_test_output_pattern(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="lots of output\n====== 8 passed in 0.5s ======\nDone.",
            stderr="",
        )
        result = run_implementation(
            proposal={"type": "new_tool", "action": "test", "target_repo": str(tmp_path), "ownership": "self"},
            observation={"type": "gap", "description": "test"},
            registry_summary="test",
        )
        assert "8 passed" in result["evidence"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_implementer.py::TestEvidenceCapture -v`
Expected: FAIL — `KeyError: 'evidence'`

- [ ] **Step 3: Update implementer to capture evidence**

In `src/orchestrator/implementer.py`, update `run_implementation` to extract
test evidence from stdout. Add this function:

```python
def extract_evidence(stdout: str, stderr: str) -> str:
    """Extract test result evidence from subprocess output.

    Looks for common test output patterns (pytest, unittest, etc.)
    and returns the most relevant lines. If no test pattern found,
    returns the last 5 lines of output.
    """
    import re
    lines = stdout.split("\n")

    # Look for pytest-style summary: "X passed", "X failed"
    for line in reversed(lines):
        if re.search(r"\d+ passed", line) or re.search(r"\d+ failed", line):
            return line.strip()

    # Look for "tests passed" / "tests failed" patterns
    for line in reversed(lines):
        if "test" in line.lower() and ("pass" in line.lower() or "fail" in line.lower()):
            return line.strip()

    # Fallback: last non-empty lines
    non_empty = [l.strip() for l in lines if l.strip()]
    return "\n".join(non_empty[-3:]) if non_empty else stderr[:200]
```

Update the return dict in `run_implementation` to include `"evidence"`:

```python
    return {
        "success": result.returncode == 0,
        "output": result.stdout,
        "error": result.stderr if result.returncode != 0 else None,
        "evidence": extract_evidence(result.stdout, result.stderr),
    }
```

Also update the timeout and external-skip returns to include `"evidence": ""`.

**Note:** The Super-Ralph "dual-condition exit gate" (require BOTH tests pass
AND explicit completion marker) is deferred to Phase 2B. This task adds
evidence capture; the gate logic that consumes the evidence comes later.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_implementer.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator/implementer.py tests/test_implementer.py
git commit -m "feat: capture literal test evidence in implementation results"
```

---

### Task 4: Scanner-Based Transcript Discovery

Wire the scanner module into the pipeline so it discovers transcripts directly
from `~/.claude/projects/` instead of depending on the session log.

**Files:**
- Modify: `src/orchestrator/pipeline.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_pipeline.py`:

```python
class TestRunCycleScannerDiscovery:
    """Test that the pipeline uses the scanner for transcript discovery."""

    @patch("orchestrator.pipeline.analyze_transcript")
    @patch("orchestrator.pipeline.scan_all_transcripts")
    def test_uses_scanner_when_no_session_log(self, mock_scan, mock_analyze, tmp_path):
        state_dir = tmp_path / "orchestrator"
        state_dir.mkdir()
        # No session-log.jsonl — scanner should still find transcripts

        mock_scan.return_value = [{
            "session_id": "scan-1",
            "path": str(Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"),
            "project_key": "-test-project",
            "lines": 100,
            "user_msgs": 10,
            "first_msg": "test",
            "first_ts": "2026-03-20T10:00:00",
            "last_ts": "2026-03-20T11:00:00",
            "mcp_servers": [],
            "mcp_call_count": 0,
            "repo": None,
            "label": {"quality": "unlabeled", "use_case_tags": [], "eval_candidate": False, "notes": ""},
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pipeline.py::TestRunCycleScannerDiscovery -v`
Expected: FAIL

- [ ] **Step 3: Update existing pipeline tests for scanner migration**

The existing tests (`TestRunCycleNoData`, `TestRunCycleObserveOnly`,
`TestRunCycleDryRun`) patch `find_completed_transcripts`. After migration they
must patch `scan_all_transcripts` instead, and the mock return format changes
from `{"transcript_path": ..., "project": ...}` to the scanner dict format
with `"path"` key.

Update `tests/test_pipeline.py`:

- `TestRunCycleNoData`: add `@patch("orchestrator.pipeline.scan_all_transcripts", return_value=[])`
- `TestRunCycleObserveOnly`: change `@patch("orchestrator.pipeline.find_completed_transcripts")`
  to `@patch("orchestrator.pipeline.scan_all_transcripts")` and update mock return value to use
  `"path"` instead of `"transcript_path"`, and add scanner metadata fields (`project_key`,
  `lines`, `user_msgs`, `first_msg`, `first_ts`, `last_ts`, `mcp_servers`, `mcp_call_count`,
  `repo`, `label`)
- `TestRunCycleDryRun`: same changes as above

- [ ] **Step 4: Update pipeline to use scanner**

In `src/orchestrator/pipeline.py`:

Remove the old import:
```python
# REMOVE: from orchestrator.transcripts import find_completed_transcripts
```

Add new import:
```python
from orchestrator.scanner import scan_all_transcripts
```

Replace the transcript collection section (steps 1) with:

```python
    # 1. Collect transcripts — use scanner for direct discovery
    projects_dir = Path.home() / ".claude" / "projects"
    last_ts = get_last_run_ts(runs_dir)
    processed = {
        s for r in (runs_dir.glob("run-*.yaml") if runs_dir.exists() else [])
        for s in _load_processed_sessions(r)
    }

    all_transcripts = scan_all_transcripts(projects_dir)

    # Filter: unprocessed, completed (not too recent), since last run
    transcripts = []
    for t in all_transcripts:
        sid = t["session_id"]
        if sid in processed:
            continue
        # Skip if last timestamp is too recent (might still be active)
        if t.get("last_ts") and last_ts and t["last_ts"] < last_ts:
            continue
        transcripts.append(t)

    transcripts = transcripts[:config.max_transcripts]
```

Update the analyze loop to use `t["path"]` instead of `t["transcript_path"]`:
```python
    for t in transcripts:
        observations = analyze_transcript(
            Path(t["path"]),
            registry_summary,
            model=config.model,
            max_budget_usd=config.analysis_budget,
        )
        run["processed_sessions"].append(t["session_id"])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: All PASS

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/orchestrator/pipeline.py tests/test_pipeline.py
git commit -m "feat: wire scanner into pipeline for direct transcript discovery"
```

---

### Task 5: Skill Runner

Build the module that invokes any Claude Code skill headlessly via slash commands.

**Files:**
- Create: `src/orchestrator/skill_runner.py`
- Create: `tests/test_skill_runner.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_skill_runner.py
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from orchestrator.skill_runner import (
    build_skill_prompt,
    run_skill,
    SkillResult,
)


class TestBuildSkillPrompt:
    def test_includes_slash_command(self):
        prompt = build_skill_prompt("/review", context="Check this code")
        assert "/review" in prompt

    def test_includes_context(self):
        prompt = build_skill_prompt("/review", context="Check src/foo.py")
        assert "src/foo.py" in prompt

    def test_includes_auto_select_instruction(self):
        prompt = build_skill_prompt("/review", context="test")
        assert "recommended" in prompt.lower()

    def test_includes_autonomous_instruction(self):
        prompt = build_skill_prompt("/qa", context="test")
        assert "autonomous" in prompt.lower() or "auto" in prompt.lower()


class TestSkillResult:
    def test_success(self):
        r = SkillResult(success=True, output="All good", skill="/review")
        assert r.success is True

    def test_failure(self):
        r = SkillResult(success=False, output="", error="Failed", skill="/review")
        assert r.success is False


class TestRunSkill:
    @patch("orchestrator.skill_runner.subprocess.run")
    def test_returns_result_on_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Review complete. No issues.", stderr="")
        result = run_skill("/review", context="Check this code")
        assert result.success is True
        assert "Review complete" in result.output

    @patch("orchestrator.skill_runner.subprocess.run")
    def test_returns_result_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Skill not found")
        result = run_skill("/review", context="test")
        assert result.success is False

    @patch("orchestrator.skill_runner.subprocess.run")
    def test_handles_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=120)
        result = run_skill("/review", context="test")
        assert result.success is False
        assert "timeout" in result.error.lower()

    @patch("orchestrator.skill_runner.subprocess.run")
    def test_runs_in_specified_cwd(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="Done", stderr="")
        run_skill("/review", context="test", cwd=tmp_path)
        call_kwargs = mock_run.call_args
        assert call_kwargs[1].get("cwd") == tmp_path

    @patch("orchestrator.skill_runner.subprocess.run")
    def test_respects_model_override(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Done", stderr="")
        run_skill("/review", context="test", model="opus")
        cmd = mock_run.call_args[0][0]
        assert "opus" in cmd

    @patch("orchestrator.skill_runner.subprocess.run")
    def test_respects_budget(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Done", stderr="")
        run_skill("/review", context="test", max_budget_usd=5.0)
        cmd = mock_run.call_args[0][0]
        assert "5.0" in cmd
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_skill_runner.py -v`
Expected: FAIL

- [ ] **Step 3: Implement skill runner**

```python
# src/orchestrator/skill_runner.py
"""Invoke any Claude Code skill headlessly via slash commands.

The skill runner sends slash commands to `claude -p` with an instruction
to auto-select recommended options for any interactive decisions.
Plugin-agnostic: works with gstack, superpowers, canopy, or any skill.
"""
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


AUTO_SELECT_INSTRUCTION = """
IMPORTANT: You are running autonomously as part of an automated improvement
pipeline. For ANY interactive question, menu, or decision prompt:
- Always select the RECOMMENDED option
- If no option is marked as recommended, select the first option
- Do NOT wait for human input
- Do NOT use AskUserQuestion — make the decision and proceed
- Complete the full workflow without pausing
"""


@dataclass
class SkillResult:
    """Result from running a skill."""
    success: bool
    output: str
    skill: str
    error: str | None = None


def build_skill_prompt(
    skill_command: str,
    context: str,
) -> str:
    """Build the prompt for headless skill invocation.

    Args:
        skill_command: The slash command (e.g., "/review", "/qa", "/plan-eng-review")
        context: The context to pass to the skill (e.g., what to review, what to test)
    """
    return f"""{AUTO_SELECT_INSTRUCTION}

Run the following skill command:
{skill_command} {context}
"""


def run_skill(
    skill_command: str,
    context: str,
    cwd: Path | None = None,
    model: str = "sonnet",
    max_budget_usd: float = 2.00,
    timeout: int = 300,
) -> SkillResult:
    """Run a Claude Code skill headlessly.

    Args:
        skill_command: The slash command (e.g., "/review")
        context: Context for the skill
        cwd: Working directory for the skill invocation
        model: Model to use
        max_budget_usd: Budget cap for the invocation
        timeout: Timeout in seconds

    Returns:
        SkillResult with success status and output
    """
    prompt = build_skill_prompt(skill_command, context)

    cmd = [
        "claude", "-p", prompt,
        "--model", model,
        "--max-budget-usd", str(max_budget_usd),
        "--no-session-persistence",
    ]

    kwargs = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
    }
    if cwd:
        kwargs["cwd"] = cwd

    try:
        result = subprocess.run(cmd, **kwargs)
    except subprocess.TimeoutExpired:
        return SkillResult(
            success=False,
            output="",
            skill=skill_command,
            error=f"Timeout after {timeout}s",
        )

    return SkillResult(
        success=result.returncode == 0,
        output=result.stdout,
        skill=skill_command,
        error=result.stderr if result.returncode != 0 else None,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_skill_runner.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator/skill_runner.py tests/test_skill_runner.py
git commit -m "feat: add skill runner — invoke any Claude Code skill headlessly"
```

---

### Task 6: Wire Circuit Breaker + Rate Limiter into Pipeline

Integrate the circuit breaker and rate limiter into the pipeline's implementation loop.

**Files:**
- Modify: `src/orchestrator/pipeline.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Update CycleConfig**

Add to `CycleConfig` in `pipeline.py`:

```python
    max_failures: int = 3          # circuit breaker threshold
    max_calls_per_hour: int = 30   # rate limiter cap
```

- [ ] **Step 2: Add circuit breaker and rate limiter imports**

```python
from orchestrator.circuit_breaker import CircuitBreaker
from orchestrator.rate_limiter import RateLimiter
```

- [ ] **Step 3: Wire into run_cycle**

At the start of `run_cycle`, after creating the run entry:

```python
    breaker = CircuitBreaker(max_failures=config.max_failures)
    limiter = RateLimiter(max_calls_per_hour=config.max_calls_per_hour)
```

Before each `analyze_transcript` call, add:

```python
        if breaker.is_open:
            run["errors"].append(f"Circuit breaker open: {breaker.open_reason}")
            break
        if not limiter.can_proceed():
            run["errors"].append(f"Rate limit reached: {limiter.summary()}")
            break
        limiter.record_call()
```

Wrap `analyze_transcript` in try/except. The circuit breaker fires on
exceptions (subprocess failure, parse error), NOT on empty observations
(a clean session with no friction is a valid result):

```python
        try:
            observations = analyze_transcript(
                Path(t["path"]),
                registry_summary,
                model=config.model,
                max_budget_usd=config.analysis_budget,
            )
            breaker.record_success()
        except Exception as e:
            breaker.record_failure(f"Analysis error for {t['session_id']}: {e}")
            observations = []
```

Same pattern around `generate_proposals` and `run_implementation`:

```python
        # Before implementation
        if breaker.is_open or not limiter.can_proceed():
            break
        limiter.record_call()

        # After implementation
        if result["success"]:
            breaker.record_success()
        else:
            breaker.record_failure(result.get("error", "Unknown"))
```

- [ ] **Step 4: Update run log entry**

Add to the run entry at the end:

```python
    run["circuit_breaker_tripped"] = breaker.is_open
    run["rate_limit_summary"] = limiter.summary()
```

- [ ] **Step 5: Write test for circuit breaker in pipeline**

Add to `tests/test_pipeline.py`:

```python
class TestRunCycleCircuitBreaker:
    @patch("orchestrator.pipeline.analyze_transcript")
    @patch("orchestrator.pipeline.scan_all_transcripts")
    def test_stops_after_consecutive_failures(self, mock_scan, mock_analyze, tmp_path):
        state_dir = tmp_path / "orchestrator"
        state_dir.mkdir()

        # Return 5 transcripts but analyzer always raises (real failure)
        mock_scan.return_value = [
            {"session_id": f"s{i}", "path": str(Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"),
             "project_key": "-test", "lines": 100, "user_msgs": 10, "first_msg": "test",
             "first_ts": "2026-03-20T10:00:00", "last_ts": "2026-03-20T11:00:00",
             "mcp_servers": [], "mcp_call_count": 0, "repo": None,
             "label": {"quality": "unlabeled", "use_case_tags": [], "eval_candidate": False, "notes": ""}}
            for i in range(5)
        ]
        mock_analyze.side_effect = RuntimeError("API error")  # Real failure

        result = run_cycle(
            state_dir=state_dir,
            registry_path=Path(__file__).parent / "fixtures" / "sample_registry.yaml",
            config=CycleConfig(observe_only=True, max_failures=3),
        )
        assert result.get("circuit_breaker_tripped") is True
        # Errors should be logged
        assert len(result.get("errors", [])) > 0
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: All PASS

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/orchestrator/pipeline.py tests/test_pipeline.py
git commit -m "feat: wire circuit breaker and rate limiter into pipeline"
```

---

### Task 7: Update CLAUDE.md and Smoke Test

**Files:**
- Modify: `.claude/CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md**

Add to Key Files:
```
- `src/orchestrator/skill_runner.py` — headless skill invocation (any plugin)
- `src/orchestrator/circuit_breaker.py` — stops pipeline after consecutive failures
- `src/orchestrator/rate_limiter.py` — caps API calls per hour
```

- [ ] **Step 2: Run full test suite**

```bash
uv run pytest -v
```

Expected: All PASS

- [ ] **Step 3: Run smoke test**

```bash
uv run orchestrator improve --observe-only
```

Expected: Runs without errors. Should now discover transcripts via the scanner.

- [ ] **Step 4: Commit**

```bash
git add .claude/CLAUDE.md
git commit -m "docs: update CLAUDE.md with Phase 2A modules"
```
