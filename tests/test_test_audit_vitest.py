"""Tests for the vitest adapter and framework auto-detection.

These tests use inline file fixtures + mocked `subprocess.run` so they don't
require a node toolchain. The vitest_adapter logic that depends on real
vitest output (collect/run) is covered by mocking the JSON written to
`--outputFile`.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.test_audit.adapters.vitest_adapter import (
    VitestAdapter,
    _extract_test_body,
    _extract_mock_targets,
    _extract_source_calls,
    _flatten_list_payload,
    _find_matching_close,
    _locate_test,
)
from orchestrator.test_audit.framework import (
    FrameworkAdapter, _has_pytest, _has_vitest, detect_framework,
)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def test_detect_vitest_via_config_file(tmp_path: Path):
    (tmp_path / "vitest.config.ts").write_text("export default {}\n")
    assert _has_vitest(tmp_path) is True
    assert detect_framework(tmp_path).name == "vitest"


def test_detect_vitest_via_package_json_dep(tmp_path: Path):
    (tmp_path / "package.json").write_text(json.dumps({
        "devDependencies": {"vitest": "^1.0.0"}
    }))
    assert _has_vitest(tmp_path) is True
    assert detect_framework(tmp_path).name == "vitest"


def test_detect_pytest_via_pyproject(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    assert _has_pytest(tmp_path) is True
    assert detect_framework(tmp_path).name == "pytest"


def test_detect_explicit_override_wins(tmp_path: Path):
    # Repo looks like vitest, but caller asks for pytest.
    (tmp_path / "vitest.config.ts").write_text("export default {}\n")
    assert detect_framework(tmp_path, override="pytest").name == "pytest"


def test_detect_falls_back_to_pytest_for_unknown_repo(tmp_path: Path):
    assert detect_framework(tmp_path).name == "pytest"


def test_detect_unknown_framework_raises(tmp_path: Path):
    with pytest.raises(ValueError, match="unknown framework"):
        detect_framework(tmp_path, override="jest")


def test_adapter_satisfies_protocol():
    # Both concrete adapters should satisfy the runtime-checkable Protocol.
    from orchestrator.test_audit.adapters.pytest_adapter import PytestAdapter
    assert isinstance(VitestAdapter(), FrameworkAdapter)
    assert isinstance(PytestAdapter(), FrameworkAdapter)


# ---------------------------------------------------------------------------
# Body extraction (the brace-aware walker)
# ---------------------------------------------------------------------------

def test_find_matching_close_simple():
    src = "foo(bar(baz));"
    assert _find_matching_close(src, 3) == src.index(";") - 1


def test_find_matching_close_skips_strings():
    src = "f('he(llo' + \"wo)rld\")"
    # Open paren after f
    open_idx = src.index("(")
    close = _find_matching_close(src, open_idx)
    assert close is not None and src[close] == ")"
    # The matching close must be the very last char.
    assert close == len(src) - 1


def test_find_matching_close_skips_template_literals():
    src = "g(`a${nested(1)}b${other(2,3)}c`)"
    open_idx = src.index("(")
    close = _find_matching_close(src, open_idx)
    assert close == len(src) - 1


def test_find_matching_close_skips_line_comments():
    src = "h(\n  // ignore )\n  real\n)"
    open_idx = src.index("(")
    close = _find_matching_close(src, open_idx)
    assert close == src.rindex(")")


def test_extract_test_body_finds_test_call():
    src = '''import { it, expect } from 'vitest';
it('does X', () => {
  const x = compute(1, 2);
  expect(x).toBe(3);
});
'''
    body = _extract_test_body(src, line=2, leaf_name="does X")
    assert "expect(x).toBe(3)" in body
    assert "compute(1, 2)" in body


def test_extract_test_body_handles_multiline_test_name():
    src = '''it(
  'a multi-line test name',
  async () => {
    expect(true).toBe(true);
  },
);
'''
    body = _extract_test_body(src, line=1, leaf_name="a multi-line test name")
    assert "expect(true).toBe(true)" in body


# ---------------------------------------------------------------------------
# Static analysis
# ---------------------------------------------------------------------------

def test_extract_mock_targets_named_module():
    body = '''
vi.mock('../src/api');
vi.spyOn(repo, 'find');
vi.fn();
'''
    targets = _extract_mock_targets(body)
    assert "../src/api" in targets
    assert "find" in targets
    # vi.fn() with no args records the helper name itself
    assert "vi.fn" in targets


def test_extract_source_calls_drops_framework_noise():
    body = '''
expect(foo(1)).toBe(2);
describe('x', () => { Bar.do(); });
beforeEach(() => {});
console.log('z');
helper();
'''
    calls = _extract_source_calls(body)
    assert "foo" in calls
    assert "Bar.do" in calls
    assert "helper" in calls
    assert "expect" not in calls
    assert "describe" not in calls
    assert "console.log" not in calls


def test_analyze_counts_assertions_and_marks_real():
    body_file = (
        "import { it, expect, vi } from 'vitest';\n"
        "it('checks math', () => {\n"
        "  const r = sum(1, 2);\n"
        "  expect(r).toBe(3);\n"
        "  expect(r).toBeGreaterThan(0);\n"
        "  vi.mock('../math');\n"
        "});\n"
    )

    class FakeItem:
        nodeid = "x.test.ts::checks math"
        name = "checks math"
        line = 2
        file = None  # filled below
        classname = None

    fp = Path("/tmp/_vitest_analyze_test.ts")
    fp.write_text(body_file)
    FakeItem.file = fp
    try:
        result = VitestAdapter().analyze(FakeItem())
    finally:
        fp.unlink()

    assert result.assertion_count == 2
    assert result.has_real_assertion is True
    assert "../math" in result.mock_targets
    assert "sum" in result.source_funcs_referenced


# ---------------------------------------------------------------------------
# vitest list payload normalization
# ---------------------------------------------------------------------------

def test_flatten_list_top_level_array():
    data = [{"file": "a.test.ts", "name": "x"},
            {"file": "b.test.ts", "name": "y"}]
    assert _flatten_list_payload(data) == data


def test_flatten_list_jest_compatible_shape():
    data = {
        "testResults": [
            {
                "name": "/abs/foo.test.ts",
                "assertionResults": [
                    {"fullName": "outer > inner > does X", "status": "passed"},
                    {"title": "alone", "status": "passed"},
                ],
            }
        ]
    }
    out = _flatten_list_payload(data)
    assert {"file": "/abs/foo.test.ts", "name": "outer > inner > does X"} in out
    assert {"file": "/abs/foo.test.ts", "name": "alone"} in out


def test_flatten_list_task_tree():
    data = {
        "files": [
            {
                "filepath": "/abs/foo.test.ts",
                "type": "suite",
                "name": "",
                "tasks": [
                    {
                        "type": "suite",
                        "name": "outer",
                        "tasks": [
                            {"type": "test", "name": "leaf-a"},
                            {
                                "type": "suite",
                                "name": "inner",
                                "tasks": [
                                    {"type": "test", "name": "leaf-b"},
                                ],
                            },
                        ],
                    }
                ],
            }
        ]
    }
    out = _flatten_list_payload(data)
    names = {(d["file"], d["name"]) for d in out}
    assert ("/abs/foo.test.ts", "outer > leaf-a") in names
    assert ("/abs/foo.test.ts", "outer > inner > leaf-b") in names


# ---------------------------------------------------------------------------
# collect() — both list-output and fallback paths
# ---------------------------------------------------------------------------

def test_collect_via_vitest_list(tmp_path: Path):
    (tmp_path / "vitest.config.ts").write_text("export default {}\n")
    test_file = tmp_path / "math.test.ts"
    test_file.write_text(
        "import { it, expect } from 'vitest';\n"
        "describe('math', () => {\n"
        "  it('adds', () => { expect(1+1).toBe(2); });\n"
        "});\n"
    )

    listed = [{"file": str(test_file), "name": "math > adds"}]

    def fake_run(cmd, **kwargs):
        # Find the --outputFile=... arg and write the listed payload.
        for a in cmd:
            if a.startswith("--outputFile="):
                Path(a.split("=", 1)[1]).write_text(json.dumps(listed))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with patch("orchestrator.test_audit.adapters.vitest_adapter.subprocess.run",
               side_effect=fake_run):
        items = VitestAdapter().collect(tmp_path)

    assert len(items) == 1
    item = items[0]
    assert item.nodeid.endswith("math.test.ts::math::adds")
    assert item.name == "adds"
    assert item.line == 3  # the line where `it('adds', ...)` lives


def test_collect_falls_back_when_vitest_unavailable(tmp_path: Path):
    test_file = tmp_path / "demo.test.ts"
    test_file.write_text(
        "it('alpha', () => {});\n"
        "test('beta', () => {});\n"
    )

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("no npx")

    with patch("orchestrator.test_audit.adapters.vitest_adapter.subprocess.run",
               side_effect=fake_run):
        items = VitestAdapter().collect(tmp_path)

    names = {it.name for it in items}
    assert names == {"alpha", "beta"}


def test_collect_fallback_finds_tests_in_test_directory(tmp_path: Path):
    """Regression: fallback scan must walk into `test/`, `tests/`, `__tests__/`.

    Bug in canopy 0.2.84: `_fallback_scan` used `_SKIP_SRC_DIRS` (which
    skips `test`/`tests`/`__tests__`) instead of `_SKIP_TEST_DIRS` (which
    doesn't), silently missing co-located test directories — the standard
    JS/TS layout. Surfaced first time against a real repo (ACE).
    """
    (tmp_path / "test").mkdir()
    (tmp_path / "test" / "lib").mkdir()
    (tmp_path / "test" / "lib" / "alpha.test.ts").write_text(
        "it('in-test-lib', () => {});\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "beta.test.ts").write_text(
        "it('in-tests', () => {});\n"
    )
    (tmp_path / "__tests__").mkdir()
    (tmp_path / "__tests__" / "gamma.test.ts").write_text(
        "it('in-double-underscore', () => {});\n"
    )

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("no npx")

    with patch("orchestrator.test_audit.adapters.vitest_adapter.subprocess.run",
               side_effect=fake_run):
        items = VitestAdapter().collect(tmp_path)

    names = {it.name for it in items}
    assert names == {"in-test-lib", "in-tests", "in-double-underscore"}


# ---------------------------------------------------------------------------
# run() — JSON reporter parsing
# ---------------------------------------------------------------------------

def test_run_parses_jest_compatible_json(tmp_path: Path):
    (tmp_path / "vitest.config.ts").write_text("export default {}\n")
    test_file = tmp_path / "demo.test.ts"
    test_file.write_text("it('x', () => {});\n")

    payload = {
        "testResults": [
            {
                "name": str(test_file),
                "assertionResults": [
                    {
                        "fullName": "x",
                        "status": "passed",
                        "duration": 12.4,
                    },
                    {
                        "fullName": "y",
                        "status": "failed",
                        "duration": 0,
                        "failureMessages": ["expected 1 to be 2"],
                    },
                ],
            }
        ]
    }

    def fake_run(cmd, **kwargs):
        for a in cmd:
            if a.startswith("--outputFile="):
                Path(a.split("=", 1)[1]).write_text(json.dumps(payload))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with patch("orchestrator.test_audit.adapters.vitest_adapter.subprocess.run",
               side_effect=fake_run):
        results = VitestAdapter().run(tmp_path)

    keys = list(results.keys())
    assert any(k.endswith("::x") for k in keys)
    assert any(k.endswith("::y") for k in keys)
    failed = next(v for k, v in results.items() if k.endswith("::y"))
    assert failed.status == "failed"
    assert "expected 1" in (failed.error or "")


# ---------------------------------------------------------------------------
# apply_skip() / apply_delete()
# ---------------------------------------------------------------------------

def test_apply_skip_rewrites_test_call(tmp_path: Path):
    file = tmp_path / "demo.test.ts"
    file.write_text(
        "import { it, expect } from 'vitest';\n"
        "describe('x', () => {\n"
        "  it('does the thing', () => { expect(1).toBe(1); });\n"
        "});\n"
    )
    ok = VitestAdapter().apply_skip(file, "does the thing", "tautology")
    assert ok is True
    new = file.read_text()
    assert "it.skip('does the thing'" in new
    assert "// audit: tautology" in new


def test_apply_skip_handles_only_modifier(tmp_path: Path):
    file = tmp_path / "demo.test.ts"
    file.write_text("it.only('foo', () => {});\n")
    ok = VitestAdapter().apply_skip(file, "foo", "redundant")
    assert ok is True
    new = file.read_text()
    assert "it.skip('foo'" in new


def test_apply_skip_idempotent_on_already_skipped(tmp_path: Path):
    file = tmp_path / "demo.test.ts"
    file.write_text("it.skip('foo', () => {});\n")
    ok = VitestAdapter().apply_skip(file, "foo", "noop")
    assert ok is False
    assert file.read_text() == "it.skip('foo', () => {});\n"


def test_apply_skip_returns_false_when_test_not_found(tmp_path: Path):
    file = tmp_path / "demo.test.ts"
    file.write_text("it('other', () => {});\n")
    ok = VitestAdapter().apply_skip(file, "missing", "x")
    assert ok is False


def test_apply_delete_unsupported(tmp_path: Path):
    adapter = VitestAdapter()
    assert adapter.supports_delete() is False
    file = tmp_path / "demo.test.ts"
    file.write_text("it('x', () => {});\n")
    assert adapter.apply_delete(file, "x") is False


# ---------------------------------------------------------------------------
# module_inventory() — pairing src files with .test files
# ---------------------------------------------------------------------------

def test_module_inventory_pairs_by_name(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "math.ts").write_text(
        "export function sum(a: number, b: number) { return a + b; }\n"
        "export const product = (a: number, b: number) => a * b;\n"
    )
    (tmp_path / "src" / "lonely.ts").write_text(
        "export function noTest() { return 1; }\n"
    )
    (tmp_path / "src" / "math.test.ts").write_text(
        "import { sum } from './math';\n"
        "it('sums', () => { expect(sum(1,2)).toBe(3); });\n"
    )

    inv = VitestAdapter().module_inventory(tmp_path)
    by_name = {m.module_name: m for m in inv}
    assert "math" in by_name and by_name["math"].has_test_file is True
    assert "lonely" in by_name and by_name["lonely"].has_test_file is False
    # 2 named exports in math.ts
    assert by_name["math"].public_func_count == 2


def test_module_inventory_falls_back_to_import_match(tmp_path: Path):
    """A test file that imports the module by relative path should count."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "thing.ts").write_text("export function thing() { }\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "use-thing.test.ts").write_text(
        "import { thing } from '../src/thing';\n"
        "it('x', () => { thing(); });\n"
    )
    inv = VitestAdapter().module_inventory(tmp_path)
    by_name = {m.module_name: m for m in inv}
    assert by_name["thing"].has_test_file is True


# ---------------------------------------------------------------------------
# locate_test() leaf-name handling
# ---------------------------------------------------------------------------

def test_build_corpus_dispatches_to_vitest_adapter(tmp_path: Path):
    """End-to-end: corpus.build_corpus picks the vitest adapter when detected."""
    from orchestrator.test_audit.corpus import build_corpus

    (tmp_path / "vitest.config.ts").write_text("export default {}\n")
    test_file = tmp_path / "demo.test.ts"
    test_file.write_text(
        "import { it, expect } from 'vitest';\n"
        "it('checks', () => { expect(1).toBe(1); });\n"
    )

    listed = [{"file": str(test_file), "name": "checks"}]

    def fake_run(cmd, **kwargs):
        for a in cmd:
            if a.startswith("--outputFile="):
                Path(a.split("=", 1)[1]).write_text(json.dumps(listed))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with patch("orchestrator.test_audit.adapters.vitest_adapter.subprocess.run",
               side_effect=fake_run):
        corpus = build_corpus(tmp_path, run_tests=False)

    assert corpus["framework"] == "vitest"
    assert corpus["test_count"] == 1
    assert corpus["tests"][0]["name"] == "checks"


def test_apply_from_dir_reads_framework_from_corpus(tmp_path: Path):
    """apply_from_dir picks vitest when corpus.yaml says so, even if repo signal is absent."""
    import yaml
    from orchestrator.test_audit.applier import apply_from_dir

    # No vitest.config.ts and no package.json — pure-Python repo signal.
    test_file = tmp_path / "demo.test.ts"
    test_file.write_text("it('x', () => {});\n")

    stamp_dir = tmp_path / ".canopy" / "test-audits" / "20260101-000000"
    stamp_dir.mkdir(parents=True)
    (stamp_dir / "corpus.yaml").write_text(yaml.safe_dump({
        "framework": "vitest",
        "tests": [{"nodeid": "demo.test.ts::x", "file": "demo.test.ts",
                   "name": "x", "line": 1}],
    }))
    (stamp_dir / "verdicts.yaml").write_text(yaml.safe_dump({
        "verdicts": [{"nodeid": "demo.test.ts::x", "score": 1,
                      "verdict": "prune", "reason_code": "tautology",
                      "reason": "no real assert"}],
    }))

    result = apply_from_dir(stamp_dir, repo=tmp_path, dry_run=True)
    # Vitest doesn't support delete -> plan downgrades to skip.
    assert any(c.action == "skip" for c in result.changes)
    assert not any(c.action == "delete" for c in result.changes)


def test_locate_test_returns_line_of_it_call():
    src = (
        "import { it } from 'vitest';\n"
        "describe('outer', () => {\n"
        "  describe('inner', () => {\n"
        "    it('the leaf', () => {});\n"
        "  });\n"
        "});\n"
    )
    line, leaf = _locate_test(src, "outer > inner > the leaf")
    assert leaf == "the leaf"
    assert line == 4
