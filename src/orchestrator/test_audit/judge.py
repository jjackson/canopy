"""Per-test LLM judge: scores 5 dimensions and produces a verdict.

The judge is dispatched in parallel via ThreadPoolExecutor. Each call goes
through `claude -p` (subprocess) with a focused rubric grounded in
superpowers TDD principles. The response is a YAML block we parse.

Designed for testability: the LLM call is encapsulated in `_invoke_llm`,
which can be monkeypatched / replaced with a stub for tests.
"""
from __future__ import annotations

import logging
import subprocess
import textwrap
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable

import yaml

from orchestrator.test_audit.collector import TestItem
from orchestrator.test_audit.parser import StaticAnalysis
from orchestrator.test_audit.runner import TestResult
from orchestrator.rate_limiter import RateLimiter
from orchestrator.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

VALID_VERDICTS = {"keep", "refactor", "prune", "investigate"}


@dataclass
class Verdict:
    nodeid: str
    score: int  # 0-10, higher = healthier
    verdict: str  # keep | refactor | prune | investigate
    reason_code: str  # short slug
    reason: str  # one-line human description
    dimensions: dict[str, int] = field(default_factory=dict)
    cites: list[str] = field(default_factory=list)
    error: str | None = None


RUBRIC = textwrap.dedent("""
    You are auditing a single pytest test for whether it pulls its weight.

    Score these 5 dimensions 0-10 (10 = excellent):

    1. meaningful_assertion: Does the test actually verify something? (assert True / no assertion = 0)
    2. behavior_vs_implementation: Does it test behavior (what) rather than implementation (how)?
    3. mock_discipline: Does it avoid mocking the code under test? (Mocking deps is OK; mocking CUT is not)
    4. name_match: Does the test name describe what it actually verifies?
    5. clarity: Could a new reader understand the test's purpose in <30s?

    Then assign:
    - score: 0-10 overall (weighted average, weighted by your judgment)
    - verdict: one of [keep, refactor, prune, investigate]
        * keep: score >= 7 OR test is fine as-is
        * refactor: score 4-6 with clear improvement path (mention in reason)
        * prune: score <= 3 OR redundant / no real value
        * investigate: status=failed/error in runtime data with unclear root cause
    - reason_code: short slug like 'env-fragile', 'no-meaningful-assertion',
      'mock-of-cut', 'name-mismatch', 'redundant-with-sibling', 'tautology', 'ok'
    - reason: one sentence explaining the verdict

    Special cases:
    - If runtime status is 'error' AND error mentions 'no module' / 'fixture not found'
      / 'setUp' / Docker / env: reason_code='env-fragile', verdict='prune'
      (the applier will skip-mark these, not delete).
    - If runtime status is 'failed' but the assertion itself is meaningful: verdict='investigate'.

    Respond with ONLY a YAML block, no prose:

    ```yaml
    score: <0-10>
    verdict: <keep|refactor|prune|investigate>
    reason_code: <slug>
    reason: <one sentence>
    dimensions:
      meaningful_assertion: <0-10>
      behavior_vs_implementation: <0-10>
      mock_discipline: <0-10>
      name_match: <0-10>
      clarity: <0-10>
    ```
""").strip()


def build_prompt(item: TestItem, static: StaticAnalysis,
                 runtime: TestResult | None) -> str:
    runtime_block = "no runtime data (--no-run)"
    if runtime is not None:
        runtime_block = (
            f"status: {runtime.status}\n"
            f"duration_ms: {runtime.duration_ms}\n"
            f"flake_count: {runtime.flake_count}\n"
            f"error: {runtime.error or 'none'}"
        )
    return textwrap.dedent(f"""
        {RUBRIC}

        ---
        Test nodeid: {item.nodeid}
        Test name: {item.name}

        Source:
        ```python
        {static.body_source}
        ```

        Static facts:
        - assertion_count: {static.assertion_count}
        - has_real_assertion: {static.has_real_assertion}
        - mock_targets: {static.mock_targets}
        - fixtures_used: {static.fixtures_used}
        - source_funcs_referenced: {static.source_funcs_referenced}
        - line_count: {static.line_count}

        Runtime:
        {runtime_block}
    """).strip()


def _invoke_llm(prompt: str, model: str = "haiku", timeout: int = 60) -> str:
    """Call `claude -p` with the prompt, return stdout. Override in tests."""
    cmd = ["claude", "-p", prompt, "--model", model, "--no-session-persistence"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            raise RuntimeError(f"claude -p exit {r.returncode}: {r.stderr[:200]}")
        return r.stdout
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"claude -p timeout ({timeout}s)")


def _parse_verdict(nodeid: str, raw: str) -> Verdict:
    # Find the YAML block.
    text = raw
    if "```yaml" in raw:
        text = raw.split("```yaml", 1)[1].split("```", 1)[0]
    elif "```" in raw:
        text = raw.split("```", 1)[1].split("```", 1)[0]
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        return Verdict(nodeid=nodeid, score=0, verdict="investigate",
                       reason_code="parse-error", reason=f"YAML parse failed: {e}",
                       error=str(e))
    verdict = str(data.get("verdict", "investigate")).strip().lower()
    if verdict not in VALID_VERDICTS:
        verdict = "investigate"
    return Verdict(
        nodeid=nodeid,
        score=int(data.get("score", 0)),
        verdict=verdict,
        reason_code=str(data.get("reason_code", "unknown")),
        reason=str(data.get("reason", "")).strip(),
        dimensions={k: int(v) for k, v in (data.get("dimensions") or {}).items()},
        cites=list(data.get("cites") or []),
    )


def judge_one(item: TestItem, static: StaticAnalysis,
              runtime: TestResult | None,
              invoke: Callable[[str], str] | None = None,
              model: str = "haiku") -> Verdict:
    """Score a single test. `invoke` defaults to `_invoke_llm`; override for tests."""
    invoker = invoke or (lambda p: _invoke_llm(p, model=model))
    prompt = build_prompt(item, static, runtime)
    try:
        raw = invoker(prompt)
    except Exception as e:
        return Verdict(nodeid=item.nodeid, score=0, verdict="investigate",
                       reason_code="judge-error", reason=str(e)[:200], error=str(e))
    return _parse_verdict(item.nodeid, raw)


def judge_all(
    items: list[TestItem],
    statics: dict[str, StaticAnalysis],
    runtimes: dict[str, TestResult],
    invoke: Callable[[str], str] | None = None,
    parallelism: int = 4,
    rate_limiter: RateLimiter | None = None,
    breaker: CircuitBreaker | None = None,
    model: str = "haiku",
) -> dict[str, Verdict]:
    """Judge all tests in parallel.

    `rate_limiter` caps API calls per hour; `breaker` aborts after N consecutive
    failures.
    """
    out: dict[str, Verdict] = {}
    rl = rate_limiter or RateLimiter(max_calls_per_hour=2000)
    cb = breaker or CircuitBreaker(max_failures=5)

    def _do(item: TestItem) -> Verdict:
        if cb.is_open:
            return Verdict(nodeid=item.nodeid, score=0, verdict="investigate",
                           reason_code="circuit-open",
                           reason=f"circuit breaker tripped: {cb.open_reason}")
        if not rl.can_proceed():
            return Verdict(nodeid=item.nodeid, score=0, verdict="investigate",
                           reason_code="rate-limited",
                           reason=f"rate limit: {rl.summary()}")
        rl.record_call()
        v = judge_one(item, statics[item.nodeid], runtimes.get(item.nodeid),
                      invoke=invoke, model=model)
        if v.error:
            cb.record_failure(v.error)
        else:
            cb.record_success()
        return v

    with ThreadPoolExecutor(max_workers=parallelism) as pool:
        futures = {pool.submit(_do, it): it for it in items if it.nodeid in statics}
        for fut in as_completed(futures):
            it = futures[fut]
            try:
                out[it.nodeid] = fut.result()
            except Exception as e:
                logger.exception("Judge crashed for %s", it.nodeid)
                out[it.nodeid] = Verdict(
                    nodeid=it.nodeid, score=0, verdict="investigate",
                    reason_code="judge-crashed", reason=str(e)[:200], error=str(e),
                )
    return out
