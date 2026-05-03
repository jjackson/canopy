"""Tests for `canopy sessions list --project <name>`.

The flag must filter precisely by `repo` suffix `/<name>` — it must NOT
substring-match on project_key. Surfaced when a session-review run with
`project ace` returned 18 sessions because the agent did its own
substring filter and caught both jjackson/ace and jjackson/ace-web; the
user wanted only the ace plugin.
"""
import json
from unittest.mock import patch

from click.testing import CliRunner

from orchestrator.cli import main


def _stub_sessions():
    """Three sessions across three different repos sharing the substring 'ace'."""
    return [
        {
            "session_id": "aaa",
            "path": "/x/aaa.jsonl",
            "project_key": "-Users-x-emdash-worktrees-ace-emdash-feat",
            "repo": "jjackson/ace",
            "first_msg": "ace plugin work",
            "user_msgs": 5,
            "first_ts": "2026-05-02T00:00:00Z",
            "last_ts": "2026-05-02T12:00:00Z",
            "lines": 100,
            "mcp_servers": [],
            "mcp_call_count": 0,
            "label": {"quality": "unlabeled", "use_case_tags": [],
                      "eval_candidate": False, "notes": ""},
        },
        {
            "session_id": "bbb",
            "path": "/x/bbb.jsonl",
            "project_key": "-Users-x-emdash-worktrees-ace-web-emdash-feat",
            "repo": "jjackson/ace-web",
            "first_msg": "ace-web work",
            "user_msgs": 5,
            "first_ts": "2026-05-02T00:00:00Z",
            "last_ts": "2026-05-02T12:00:00Z",
            "lines": 100,
            "mcp_servers": [],
            "mcp_call_count": 0,
            "label": {"quality": "unlabeled", "use_case_tags": [],
                      "eval_candidate": False, "notes": ""},
        },
        {
            "session_id": "ccc",
            "path": "/x/ccc.jsonl",
            "project_key": "-Users-x-emdash-worktrees-canopy-emdash-feat",
            "repo": "jjackson/canopy",
            "first_msg": "canopy work",
            "user_msgs": 5,
            "first_ts": "2026-05-02T00:00:00Z",
            "last_ts": "2026-05-02T12:00:00Z",
            "lines": 100,
            "mcp_servers": [],
            "mcp_call_count": 0,
            "label": {"quality": "unlabeled", "use_case_tags": [],
                      "eval_candidate": False, "notes": ""},
        },
    ]


@patch("orchestrator.cli.scan_all_transcripts" if False else "orchestrator.scanner.scan_all_transcripts")
class TestSessionsListProjectFilter:
    def test_no_filter_returns_all(self, mock_scan):
        mock_scan.return_value = _stub_sessions()
        runner = CliRunner()
        result = runner.invoke(main, ["sessions", "list", "--hours", "168", "--json-output"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert {s["session_id"] for s in data} == {"aaa", "bbb", "ccc"}

    def test_project_ace_excludes_ace_web(self, mock_scan):
        # The bug we are fixing: `project ace` must NOT include ace-web.
        mock_scan.return_value = _stub_sessions()
        runner = CliRunner()
        result = runner.invoke(main, [
            "sessions", "list", "--hours", "168", "--json-output",
            "--project", "ace",
        ])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert {s["session_id"] for s in data} == {"aaa"}, (
            f"Expected only the jjackson/ace session, got {data}"
        )

    def test_project_ace_web_finds_only_ace_web(self, mock_scan):
        mock_scan.return_value = _stub_sessions()
        runner = CliRunner()
        result = runner.invoke(main, [
            "sessions", "list", "--hours", "168", "--json-output",
            "--project", "ace-web",
        ])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert {s["session_id"] for s in data} == {"bbb"}

    def test_project_unknown_returns_empty(self, mock_scan):
        mock_scan.return_value = _stub_sessions()
        runner = CliRunner()
        result = runner.invoke(main, [
            "sessions", "list", "--hours", "168", "--json-output",
            "--project", "totally-unknown",
        ])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data == []

    def test_project_filter_skips_sessions_with_null_repo(self, mock_scan):
        # If repo couldn't be resolved (no map entry, no inference), the
        # session is excluded — better to under-include than misclassify.
        sessions = _stub_sessions()
        sessions.append({**sessions[0], "session_id": "ddd", "repo": None})
        mock_scan.return_value = sessions
        runner = CliRunner()
        result = runner.invoke(main, [
            "sessions", "list", "--hours", "168", "--json-output",
            "--project", "ace",
        ])
        data = json.loads(result.output)
        assert {s["session_id"] for s in data} == {"aaa"}  # not ddd
