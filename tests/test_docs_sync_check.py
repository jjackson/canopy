"""Unit tests for the docs-sync CI gate.

Covers the pure `check_docs_sync` logic — no subprocess, no gh. The CLI/gh
plumbing is exercised on real PRs (this one's own check, deliberately
sync-failed once during landing verification).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# The script lives under .github/scripts/, which isn't a Python package. Load
# it directly via importlib so we don't have to restructure for tests.
# Register in sys.modules BEFORE exec_module so dataclass's forward-ref
# resolver can find the module by name (otherwise CheckResult's "TriggerMiss"
# forward ref blows up at class-creation time).
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT_PATH = _REPO_ROOT / ".github" / "scripts" / "docs_sync_check.py"

_spec = importlib.util.spec_from_file_location("docs_sync_check", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
docs_sync_check = importlib.util.module_from_spec(_spec)
sys.modules["docs_sync_check"] = docs_sync_check
_spec.loader.exec_module(docs_sync_check)

check_docs_sync = docs_sync_check.check_docs_sync
has_opt_out_marker = docs_sync_check.has_opt_out_marker
TRIGGER_PATHS = docs_sync_check.TRIGGER_PATHS


# -----------------------------------------------------------------------------
# has_opt_out_marker
# -----------------------------------------------------------------------------


class TestOptOutMarker:
    def test_no_body_no_marker(self):
        assert has_opt_out_marker(None) == (False, None)
        assert has_opt_out_marker("") == (False, None)

    def test_marker_with_reason(self):
        body = "Some description.\n\nDocs-not-needed: pure refactor with no API change\n"
        assert has_opt_out_marker(body) == (
            True,
            "pure refactor with no API change",
        )

    def test_marker_empty_reason(self):
        body = "Docs-not-needed:"
        present, reason = has_opt_out_marker(body)
        assert present is True
        assert reason == "(no reason given)"

    def test_marker_must_be_at_line_start_after_strip(self):
        # Embedded in prose — doesn't trigger.
        body = "We said Docs-not-needed: nope earlier but actually do."
        assert has_opt_out_marker(body) == (False, None)

    def test_marker_indented_still_works(self):
        # Leading whitespace shouldn't defeat the marker — authors will paste
        # it into a markdown bullet sometimes.
        body = "  Docs-not-needed: indented but valid"
        assert has_opt_out_marker(body) == (True, "indented but valid")


# -----------------------------------------------------------------------------
# check_docs_sync — required scenarios from the spec
# -----------------------------------------------------------------------------


class TestCheckDocsSync:
    def test_models_only_change_fails_listing_both_skill_mds(self):
        # New Action verb shipped without touching either spec or walkthrough.
        result = check_docs_sync(
            changed=["scripts/ddd/schemas/models.py"],
            pr_body="No opt-out here.",
        )
        assert result.failed
        assert len(result.missing) == 1
        miss = result.missing[0]
        assert miss.trigger == "scripts/ddd/schemas/models.py"
        assert sorted(miss.missing_docs) == sorted(
            [
                "plugins/canopy/skills/ddd-spec/SKILL.md",
                "plugins/canopy/skills/walkthrough/SKILL.md",
            ]
        )

    def test_models_plus_ddd_spec_only_lists_walkthrough(self):
        # Author updated one of two — gate fails listing only the still-missing one.
        result = check_docs_sync(
            changed=[
                "scripts/ddd/schemas/models.py",
                "plugins/canopy/skills/ddd-spec/SKILL.md",
            ],
            pr_body="",
        )
        assert result.failed
        assert len(result.missing) == 1
        assert result.missing[0].missing_docs == [
            "plugins/canopy/skills/walkthrough/SKILL.md"
        ]

    def test_models_plus_both_skill_mds_passes(self):
        result = check_docs_sync(
            changed=[
                "scripts/ddd/schemas/models.py",
                "plugins/canopy/skills/ddd-spec/SKILL.md",
                "plugins/canopy/skills/walkthrough/SKILL.md",
            ],
            pr_body="",
        )
        assert result.passed
        assert result.missing == []
        assert result.opt_out_reason is None

    def test_models_only_with_opt_out_passes_with_reason(self):
        result = check_docs_sync(
            changed=["scripts/ddd/schemas/models.py"],
            pr_body="Refactor of Pydantic model imports.\n\nDocs-not-needed: pure import reorganization\n",
        )
        assert result.passed
        assert result.opt_out_reason == "pure import reorganization"
        # The misses are still recorded so the workflow log can show which
        # triggers were opted out of.
        assert len(result.missing) == 1
        assert result.missing[0].trigger == "scripts/ddd/schemas/models.py"

    def test_rubric_change_without_concept_eval_skill_fails(self):
        result = check_docs_sync(
            changed=["plugins/canopy/skills/ddd-concept-eval/rubric.yaml"],
            pr_body="",
        )
        assert result.failed
        assert len(result.missing) == 1
        miss = result.missing[0]
        assert miss.trigger == "plugins/canopy/skills/ddd-concept-eval/rubric.yaml"
        assert miss.missing_docs == ["plugins/canopy/skills/ddd-concept-eval/SKILL.md"]

    def test_unrelated_change_passes_silently(self):
        # PR touches only non-trigger files — gate is a no-op.
        result = check_docs_sync(
            changed=[
                "README.md",
                "tests/test_something_unrelated.py",
                "scripts/walkthrough/_lib/results.py",  # NOT in TRIGGER_PATHS (telemetry shape, not author surface)
            ],
            pr_body="",
        )
        assert result.passed
        assert result.missing == []
        assert result.opt_out_reason is None

    def test_empty_pr_passes(self):
        # Defensive — empty PR (somehow) shouldn't crash the gate.
        result = check_docs_sync(changed=[], pr_body="")
        assert result.passed
        assert result.missing == []


# -----------------------------------------------------------------------------
# Recorder + record_video flag triggers — extra coverage for the other two
# categories in the spec.
# -----------------------------------------------------------------------------


class TestRecorderAndRecordVideoTriggers:
    def test_recorder_change_requires_both_skill_mds(self):
        result = check_docs_sync(
            changed=["scripts/walkthrough/_lib/recorder.py"],
            pr_body="",
        )
        assert result.failed
        miss = result.missing[0]
        assert sorted(miss.missing_docs) == sorted(
            [
                "plugins/canopy/skills/ddd-spec/SKILL.md",
                "plugins/canopy/skills/walkthrough/SKILL.md",
            ]
        )

    def test_record_video_cli_change_requires_ddd_run(self):
        # CLI flag landed without telling the orchestrator skill — fail.
        result = check_docs_sync(
            changed=["scripts/walkthrough/record_video.py"],
            pr_body="",
        )
        assert result.failed
        miss = result.missing[0]
        assert miss.trigger == "scripts/walkthrough/record_video.py"
        assert miss.missing_docs == ["plugins/canopy/skills/ddd-run/SKILL.md"]

    def test_multi_trigger_change_reports_all_misses(self):
        # Touches two triggers — both should appear in result.missing.
        result = check_docs_sync(
            changed=[
                "scripts/walkthrough/record_video.py",
                "plugins/canopy/skills/ddd-concept-eval/rubric.yaml",
            ],
            pr_body="",
        )
        assert result.failed
        assert len(result.missing) == 2
        triggers = {m.trigger for m in result.missing}
        assert triggers == {
            "scripts/walkthrough/record_video.py",
            "plugins/canopy/skills/ddd-concept-eval/rubric.yaml",
        }


# -----------------------------------------------------------------------------
# Smoke test: the failure message string contains the structured info the spec
# requires — trigger paths, missing docs, the "Why this matters" rationale,
# and the opt-out marker syntax.
# -----------------------------------------------------------------------------


class TestFailureMessage:
    def test_message_includes_required_pieces(self):
        result = check_docs_sync(
            changed=["scripts/ddd/schemas/models.py"],
            pr_body="",
        )
        assert result.failed
        msg = docs_sync_check.format_failure_message(result)
        # Trigger path called out.
        assert "scripts/ddd/schemas/models.py" in msg
        # Missing doc enumerated.
        assert "plugins/canopy/skills/ddd-spec/SKILL.md" in msg
        assert "plugins/canopy/skills/walkthrough/SKILL.md" in msg
        # Rationale cites the prior gap PRs.
        assert "#100" in msg and "#115" in msg
        # Opt-out marker syntax taught.
        assert "Docs-not-needed:" in msg


# -----------------------------------------------------------------------------
# TRIGGER_PATHS sanity: every key and value points at a real file in the repo
# right now. If someone renames a path without updating the mapping, this
# test fails loudly (vs the gate silently no-opping in CI).
# -----------------------------------------------------------------------------


class TestTriggerPathsAreReal:
    @pytest.mark.parametrize("trigger", list(TRIGGER_PATHS.keys()))
    def test_trigger_path_exists(self, trigger: str):
        path = _REPO_ROOT / trigger
        assert path.exists(), (
            f"TRIGGER_PATHS key {trigger!r} doesn't exist in the repo —"
            " the gate will silently no-op for this trigger. Update the"
            " mapping in .github/scripts/docs_sync_check.py to match the"
            " renamed source path."
        )

    @pytest.mark.parametrize(
        "doc",
        sorted({d for docs in TRIGGER_PATHS.values() for d in docs}),
    )
    def test_required_doc_exists(self, doc: str):
        path = _REPO_ROOT / doc
        assert path.exists(), (
            f"TRIGGER_PATHS value {doc!r} doesn't exist in the repo — the"
            " gate would fail every PR that touches the trigger because the"
            " required doc can't be updated. Update the mapping."
        )
