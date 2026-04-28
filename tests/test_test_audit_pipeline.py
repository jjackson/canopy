"""End-to-end smoke test against the synthetic_suite fixture, judge stubbed."""
import shutil
from pathlib import Path

from orchestrator.test_audit import run_audit, AuditConfig

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_suite"


# Per-test stubbed verdicts — keyed by test name.
EXPECTED = {
    "test_add_returns_sum":     ("keep", 8, "ok"),
    "test_add_with_negatives":  ("keep", 7, "ok"),
    "test_always_passes":       ("prune", 1, "tautology"),
    "test_no_assertion":        ("prune", 0, "no-meaningful-assertion"),
    "test_env_fragile":         ("prune", 6, "env-fragile"),
    "test_subtraction_works":   ("refactor", 4, "name-mismatch"),
    "test_add_with_mock_of_cut":("prune", 2, "mock-of-cut"),
}


def _stub(prompt: str) -> str:
    # Pull the test name out of the prompt to decide which canned response.
    for name, (verdict, score, code) in EXPECTED.items():
        if f"Test name: {name}" in prompt:
            return (
                "```yaml\n"
                f"score: {score}\n"
                f"verdict: {verdict}\n"
                f"reason_code: {code}\n"
                f"reason: stubbed for test\n"
                "dimensions:\n"
                "  meaningful_assertion: 5\n"
                "  behavior_vs_implementation: 5\n"
                "  mock_discipline: 5\n"
                "  name_match: 5\n"
                "  clarity: 5\n"
                "```"
            )
    return "```yaml\nscore: 5\nverdict: keep\nreason_code: unknown\nreason: x\n```"


def test_pipeline_classifies_synthetic_suite_correctly(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copytree(FIXTURE, repo / "tests")

    cfg = AuditConfig(
        repo=repo,
        run_tests=False,  # don't actually run pytest in this isolated tmp repo
        apply=False,
        invoke_override=_stub,
        parallelism=2,
    )
    result = run_audit(cfg)

    by_name = {nid.split("::")[-1]: v for nid, v in result.summary.verdicts.items()}
    for name, (expected_verdict, _, expected_code) in EXPECTED.items():
        v = by_name[name]
        assert v.verdict == expected_verdict, f"{name}: {v.verdict} != {expected_verdict}"
        assert v.reason_code == expected_code, f"{name}: {v.reason_code} != {expected_code}"

    # env_fragile bucket is populated.
    assert any("test_env_fragile" in nid for nid in result.summary.env_fragile)

    # Two add_* tests cluster as redundant (both reference `add` with similar shape).
    cluster_keepers = [c.keeper.split("::")[-1] for c in result.summary.clusters]
    assert any("test_add" in k for k in cluster_keepers)


def test_pipeline_writes_report_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copytree(FIXTURE, repo / "tests")
    cfg = AuditConfig(repo=repo, run_tests=False, apply=False,
                      invoke_override=_stub, parallelism=2)
    result = run_audit(cfg)
    for key in ("report", "verdicts", "summary"):
        assert result.files[key].exists()
        assert result.files[key].read_text(encoding="utf-8")
