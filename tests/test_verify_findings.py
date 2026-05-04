"""Tests for verify_findings — covers the deterministic parts (load, group,
update YAML, parse LLM output) without making real claude -p calls.
"""
import subprocess
from pathlib import Path
from unittest.mock import patch

import yaml

from orchestrator import verify_findings as vf


def _write_proposal(dir_: Path, pid: str, **fields) -> Path:
    """Helper: create a proposal YAML in the given directory."""
    dir_.mkdir(parents=True, exist_ok=True)
    base = {
        "id": pid,
        "type": "tool_improvement",
        "action": "Some action mentioning `some_symbol`",
        "target_repo": "ace",
        "status": "pending",
        "created": "2026-05-01",
    }
    base.update(fields)
    path = dir_ / f"{pid}.yaml"
    path.write_text(yaml.dump(base, default_flow_style=False, sort_keys=False))
    return path


class TestLoadProposals:
    def test_loads_by_prefix(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vf, "PROPOSALS_DIR", tmp_path)
        _write_proposal(tmp_path, "abc12345abcd")
        _write_proposal(tmp_path, "xyz98765xyzz")
        result = vf.load_proposals(["abc12345"], all_pending=False)
        assert len(result) == 1
        assert result[0]["id"] == "abc12345abcd"

    def test_short_prefixes_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vf, "PROPOSALS_DIR", tmp_path)
        _write_proposal(tmp_path, "abc12345abcd")
        result = vf.load_proposals(["abc"], all_pending=False)  # < 8 chars
        assert result == []

    def test_all_pending_filters_status(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vf, "PROPOSALS_DIR", tmp_path)
        _write_proposal(tmp_path, "aaaaaaaaaaaa", status="pending")
        _write_proposal(tmp_path, "bbbbbbbbbbbb", status="implemented")
        _write_proposal(tmp_path, "cccccccccccc", status="obsolete")
        result = vf.load_proposals(None, all_pending=True)
        assert {p["id"] for p in result} == {"aaaaaaaaaaaa"}

    def test_includes_path_for_writeback(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vf, "PROPOSALS_DIR", tmp_path)
        path = _write_proposal(tmp_path, "abc12345abcd")
        result = vf.load_proposals(["abc12345"], all_pending=False)
        assert result[0]["_path"] == str(path)

    def test_empty_dir_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vf, "PROPOSALS_DIR", tmp_path)
        assert vf.load_proposals(["abcdefgh"], all_pending=False) == []
        assert vf.load_proposals(None, all_pending=True) == []


class TestExtractSymbols:
    def test_extracts_backtick_quoted(self):
        proposals = [
            {"action": "Update `setup.py` to call `resolve_repo_path`", "motivation": ""},
        ]
        symbols = vf._extract_symbols(proposals)
        assert "setup.py" in symbols
        assert "resolve_repo_path" in symbols

    def test_dedups_across_proposals(self):
        proposals = [
            {"action": "Use `foo` here", "motivation": ""},
            {"action": "Also use `foo` there", "motivation": ""},
        ]
        symbols = vf._extract_symbols(proposals)
        assert symbols.count("foo") == 1

    def test_caps_at_30(self):
        proposals = [{"action": " ".join(f"`sym{i}`" for i in range(50)), "motivation": ""}]
        symbols = vf._extract_symbols(proposals)
        assert len(symbols) <= 30

    def test_handles_missing_fields(self):
        # No action / motivation — should not raise
        symbols = vf._extract_symbols([{}])
        assert symbols == []


class TestParseVerdictOutput:
    def test_strips_code_fences(self):
        output = "```yaml\n- id: abc\n  verdict: shipped\n  evidence: cite\n```"
        result = vf._parse_verdict_output(output)
        assert result == [{"id": "abc", "verdict": "shipped", "evidence": "cite"}]

    def test_handles_unfenced(self):
        output = "- id: abc\n  verdict: open\n  evidence: ''\n"
        result = vf._parse_verdict_output(output)
        assert len(result) == 1
        assert result[0]["verdict"] == "open"

    def test_returns_empty_on_unparseable(self):
        assert vf._parse_verdict_output("this is not yaml: {{{") == []

    def test_returns_empty_on_non_list(self):
        # A dict, not a list — caller expects a list per proposal
        assert vf._parse_verdict_output("id: abc\nverdict: shipped") == []


class TestUpdateProposalYaml:
    def test_shipped_flips_status_to_obsolete(self, tmp_path):
        path = _write_proposal(tmp_path, "abcdefghijkl")
        proposal = yaml.safe_load(path.read_text())
        proposal["_path"] = str(path)
        verdict = {
            "id": "abcdefghijkl",
            "verdict": "shipped",
            "evidence": "0.10.99 (abc1234)",
            "shipped_at": "abc1234",
            "shipped_in_version": "0.10.99",
        }
        assert vf.update_proposal_yaml(proposal, verdict) is True
        d = yaml.safe_load(path.read_text())
        assert d["status"] == "obsolete"
        assert d["verified"]["shipped_at"] == "abc1234"
        assert d["verified"]["shipped_in_version"] == "0.10.99"
        assert d["verified"]["evidence"] == "0.10.99 (abc1234)"
        assert d["verified"]["by"] == "verify-findings"

    def test_partial_does_not_mutate(self, tmp_path):
        path = _write_proposal(tmp_path, "abcdefghijkl")
        proposal = yaml.safe_load(path.read_text())
        proposal["_path"] = str(path)
        verdict = {"id": "abcdefghijkl", "verdict": "partial", "evidence": "x"}
        assert vf.update_proposal_yaml(proposal, verdict) is False
        d = yaml.safe_load(path.read_text())
        assert d["status"] == "pending"
        assert "verified" not in d

    def test_open_does_not_mutate(self, tmp_path):
        path = _write_proposal(tmp_path, "abcdefghijkl")
        proposal = yaml.safe_load(path.read_text())
        proposal["_path"] = str(path)
        verdict = {"id": "abcdefghijkl", "verdict": "open", "evidence": "x"}
        assert vf.update_proposal_yaml(proposal, verdict) is False

    def test_missing_path_returns_false(self):
        proposal = {"id": "x", "_path": "/totally/missing/path.yaml"}
        verdict = {"id": "x", "verdict": "shipped", "evidence": "x"}
        assert vf.update_proposal_yaml(proposal, verdict) is False


class TestVerifyEndToEnd:
    def test_unresolved_target_short_circuits(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vf, "PROPOSALS_DIR", tmp_path)
        # Use a target_repo that won't resolve anywhere.
        _write_proposal(tmp_path, "abcdefghijkl",
                        target_repo="totally-fake-repo-name")
        # Force resolve_repo_path to return None for this short name.
        with patch("orchestrator.verify_findings.resolve_repo_path", return_value=None):
            result = vf.verify(id_prefixes=["abcdefgh"], all_pending=False)
        assert result["summary"]["unverifiable"] == 1
        assert result["summary"]["shipped"] == 0
        assert "not on this machine" in result["verdicts"][0]["evidence"]

    def test_resolved_repo_uses_llm_verdicts(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vf, "PROPOSALS_DIR", tmp_path)
        _write_proposal(tmp_path, "aaaaaaaaaaaa", target_repo="ace")
        _write_proposal(tmp_path, "bbbbbbbbbbbb", target_repo="ace")

        fake_repo = tmp_path / "fake-ace"
        fake_repo.mkdir()
        (fake_repo / ".git").mkdir()  # so it looks like a git dir to repo_paths

        with patch("orchestrator.verify_findings.resolve_repo_path",
                   return_value=fake_repo), \
             patch("orchestrator.verify_findings.subprocess.run") as run_mock, \
             patch("orchestrator.verify_findings._git_log_recent",
                   return_value="abc123 2026-05-02 some commit"), \
             patch("orchestrator.verify_findings._changelog_head",
                   return_value="## 1.0\n- did stuff"), \
             patch("orchestrator.verify_findings._grep_repo",
                   return_value="(no hits)"), \
             patch("orchestrator.verify_findings.call_llm_for_verdicts",
                   return_value=[
                       {"id": "aaaaaaaaaaaa", "verdict": "shipped",
                        "evidence": "abc123 lands it",
                        "shipped_at": "abc123", "shipped_in_version": "1.0"},
                       {"id": "bbbbbbbbbbbb", "verdict": "open",
                        "evidence": "no commit references it",
                        "shipped_at": None, "shipped_in_version": None},
                   ]):
            result = vf.verify(id_prefixes=["aaaaaaaa", "bbbbbbbb"],
                               all_pending=False)

        assert result["summary"]["shipped"] == 1
        assert result["summary"]["open"] == 1
        # The shipped one should have been written back to the YAML.
        a_path = tmp_path / "aaaaaaaaaaaa.yaml"
        a_data = yaml.safe_load(a_path.read_text())
        assert a_data["status"] == "obsolete"
        # The open one stays pending.
        b_path = tmp_path / "bbbbbbbbbbbb.yaml"
        b_data = yaml.safe_load(b_path.read_text())
        assert b_data["status"] == "pending"

    def test_llm_skips_proposal_returns_unverifiable(self, tmp_path, monkeypatch):
        # If the LLM grades only some proposals, the rest must default to
        # `unverifiable` instead of silently disappearing.
        monkeypatch.setattr(vf, "PROPOSALS_DIR", tmp_path)
        _write_proposal(tmp_path, "aaaaaaaaaaaa", target_repo="ace")
        _write_proposal(tmp_path, "bbbbbbbbbbbb", target_repo="ace")

        fake_repo = tmp_path / "fake-ace"
        fake_repo.mkdir()
        (fake_repo / ".git").mkdir()

        with patch("orchestrator.verify_findings.resolve_repo_path",
                   return_value=fake_repo), \
             patch("orchestrator.verify_findings.subprocess.run"), \
             patch("orchestrator.verify_findings._git_log_recent", return_value=""), \
             patch("orchestrator.verify_findings._changelog_head", return_value=""), \
             patch("orchestrator.verify_findings._grep_repo", return_value=""), \
             patch("orchestrator.verify_findings.call_llm_for_verdicts",
                   return_value=[
                       {"id": "aaaaaaaaaaaa", "verdict": "open", "evidence": "x"},
                       # bbbbbbbbbbbb missing → must show up as unverifiable
                   ]):
            result = vf.verify(id_prefixes=["aaaaaaaa", "bbbbbbbb"],
                               all_pending=False)

        assert result["summary"]["total"] == 2
        assert result["summary"]["unverifiable"] == 1
        b_verdict = next(v for v in result["verdicts"] if v["id"] == "bbbbbbbbbbbb")
        assert b_verdict["verdict"] == "unverifiable"
        assert "did not grade" in b_verdict["evidence"]

    def test_no_proposals_short_circuits(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vf, "PROPOSALS_DIR", tmp_path)
        result = vf.verify(id_prefixes=["zzzzzzzz"], all_pending=False)
        assert result["summary"]["total"] == 0
        assert result["verdicts"] == []
