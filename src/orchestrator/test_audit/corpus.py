"""Build the audit corpus: per-test inventory + source + static facts + runtime data.

The corpus is what the calling agent reads. Everything the agent needs to
reason about the suite lives in `corpus.yaml`. No fan-out, no per-test LLM
calls — the agent does the judging in its own context.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from dataclasses import asdict

from orchestrator.test_audit.collector import collect
from orchestrator.test_audit.parser import analyze
from orchestrator.test_audit.runner import run_pytest
from orchestrator.test_audit.architecture import (
    module_inventory, mock_density_by_file, slow_tests,
)


def build_corpus(repo: Path, run_tests: bool = True, reruns: int = 0) -> dict[str, Any]:
    """Return the corpus dict for `repo`. Pure data; no I/O beyond reading source."""
    repo = repo.resolve()
    items = collect(repo)
    statics = {it.nodeid: analyze(it) for it in items}
    runtimes = run_pytest(repo, reruns=reruns) if run_tests else {}

    tests: list[dict[str, Any]] = []
    for it in items:
        st = statics[it.nodeid]
        rt = runtimes.get(it.nodeid)
        try:
            rel = str(it.file.relative_to(repo))
        except ValueError:
            rel = str(it.file)
        tests.append({
            "nodeid": it.nodeid,
            "file": rel,
            "name": it.name,
            "line": it.line,
            "classname": it.classname,
            "source": st.body_source,
            "static": {
                "assertion_count": st.assertion_count,
                "has_real_assertion": st.has_real_assertion,
                "mock_targets": st.mock_targets,
                "fixtures_used": st.fixtures_used,
                "source_funcs_referenced": st.source_funcs_referenced,
                "line_count": st.line_count,
            },
            "runtime": (
                {
                    "status": rt.status,
                    "duration_ms": rt.duration_ms,
                    "flake_count": rt.flake_count,
                    "error": rt.error,
                }
                if rt is not None else None
            ),
        })

    # Architectural grist for the agent's suite-level review pass.
    inv = module_inventory(repo)
    densities = mock_density_by_file(items, statics)
    slow = slow_tests(runtimes) if run_tests else []
    architecture = {
        "modules": [asdict(m) for m in inv],
        "untested_modules": [m.module_name for m in inv if not m.has_test_file],
        "mock_density": [asdict(d) | {"is_overmocked": d.is_overmocked} for d in densities],
        "overmocked_files": [d.file for d in densities if d.is_overmocked],
        "slow_tests": [asdict(s) for s in slow],
    }

    return {
        "repo": str(repo),
        "test_count": len(tests),
        "ran_pytest": run_tests,
        "reruns": reruns,
        "architecture": architecture,
        "tests": tests,
    }


def write_corpus(repo: Path, out_dir: Path, run_tests: bool = True,
                 reruns: int = 0) -> tuple[Path, dict[str, Any]]:
    """Build + write `corpus.yaml` to `out_dir`. Returns (path, corpus)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    corpus = build_corpus(repo, run_tests=run_tests, reruns=reruns)
    path = out_dir / "corpus.yaml"
    path.write_text(yaml.safe_dump(corpus, sort_keys=False), encoding="utf-8")
    return path, corpus
