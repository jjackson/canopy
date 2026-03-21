"""Tests for hooks/post_tool_use.py."""

import importlib
import io
import json
import sys
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HOOK_PATH = Path(__file__).parent.parent / "hooks" / "post_tool_use.py"


def _load_hook():
    """Import the hook module fresh each time (it lives outside the package)."""
    spec = importlib.util.spec_from_file_location("post_tool_use", HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_main(hook_module, stdin_data: str, log_file: Path, env: dict | None = None):
    """Run hook_module.main() with mocked stdin and LOG_FILE."""
    with (
        mock.patch.object(hook_module, "LOG_FILE", log_file),
        mock.patch("sys.stdin", io.StringIO(stdin_data)),
        mock.patch.dict("os.environ", env or {}, clear=False),
    ):
        hook_module.main()


def _read_log(log_file: Path) -> list[dict]:
    if not log_file.exists():
        return []
    lines = [l.strip() for l in log_file.read_text().splitlines() if l.strip()]
    return [json.loads(l) for l in lines]


# ---------------------------------------------------------------------------
# Basic MCP call handling
# ---------------------------------------------------------------------------


class TestMainMcpToolCall:
    def test_writes_entry_for_valid_mcp_call(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        data = json.dumps({
            "tool_name": "mcp__my-server__my_tool",
            "session_id": "sess-1",
            "tool_input": {"param": "value"},
        })
        _run_main(hook, data, log)
        entries = _read_log(log)
        assert len(entries) == 1

    def test_entry_has_correct_server(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        data = json.dumps({
            "tool_name": "mcp__my-server__my_tool",
            "session_id": "sess-1",
            "tool_input": {},
        })
        _run_main(hook, data, log)
        entry = _read_log(log)[0]
        assert entry["server"] == "my-server"

    def test_entry_has_correct_tool(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        data = json.dumps({
            "tool_name": "mcp__my-server__my_tool",
            "session_id": "sess-1",
            "tool_input": {},
        })
        _run_main(hook, data, log)
        entry = _read_log(log)[0]
        assert entry["tool"] == "my_tool"

    def test_entry_has_session_id(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        data = json.dumps({
            "tool_name": "mcp__srv__tool",
            "session_id": "my-session-abc",
            "tool_input": {},
        })
        _run_main(hook, data, log)
        entry = _read_log(log)[0]
        assert entry["session_id"] == "my-session-abc"

    def test_entry_has_ts_field(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        data = json.dumps({"tool_name": "mcp__srv__tool", "tool_input": {}})
        _run_main(hook, data, log)
        entry = _read_log(log)[0]
        assert "ts" in entry
        assert isinstance(entry["ts"], str)

    def test_success_true_when_no_error(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        data = json.dumps({"tool_name": "mcp__srv__tool", "tool_input": {}})
        _run_main(hook, data, log)
        entry = _read_log(log)[0]
        assert entry["success"] is True

    def test_success_false_when_tool_error(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        data = json.dumps({
            "tool_name": "mcp__srv__tool",
            "tool_input": {},
            "tool_error": "something went wrong",
        })
        _run_main(hook, data, log)
        entry = _read_log(log)[0]
        assert entry["success"] is False

    def test_project_from_env(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        data = json.dumps({"tool_name": "mcp__srv__tool", "tool_input": {}})
        _run_main(hook, data, log, env={"CLAUDE_PROJECT_DIR": "/my/project"})
        entry = _read_log(log)[0]
        assert entry["project"] == "/my/project"

    def test_project_unknown_when_env_not_set(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        data = json.dumps({"tool_name": "mcp__srv__tool", "tool_input": {}})
        env_without_project = {k: v for k, v in mock.patch.dict("os.environ", {}).start().items()
                               if k != "CLAUDE_PROJECT_DIR"}
        with (
            mock.patch.object(hook, "LOG_FILE", log),
            mock.patch("sys.stdin", io.StringIO(data)),
            mock.patch.dict("os.environ", {}, clear=True),
        ):
            hook.main()
        entry = _read_log(log)[0]
        assert entry["project"] == "unknown"


# ---------------------------------------------------------------------------
# Non-MCP tool call is ignored
# ---------------------------------------------------------------------------


class TestNonMcpToolCallIgnored:
    def test_non_mcp_tool_not_written(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        data = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
        _run_main(hook, data, log)
        assert not log.exists()

    def test_read_tool_not_written(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        data = json.dumps({"tool_name": "Read", "tool_input": {}})
        _run_main(hook, data, log)
        assert not log.exists()

    def test_empty_tool_name_not_written(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        data = json.dumps({"tool_name": "", "tool_input": {}})
        _run_main(hook, data, log)
        assert not log.exists()

    def test_missing_tool_name_not_written(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        data = json.dumps({"tool_input": {}})
        _run_main(hook, data, log)
        assert not log.exists()


# ---------------------------------------------------------------------------
# Tool name splitting: mcp__server__tool
# ---------------------------------------------------------------------------


class TestToolNameSplitting:
    def test_splits_server_and_tool_correctly(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        data = json.dumps({
            "tool_name": "mcp__commcare-hq__get_app_structure",
            "tool_input": {},
        })
        _run_main(hook, data, log)
        entry = _read_log(log)[0]
        assert entry["server"] == "commcare-hq"
        assert entry["tool"] == "get_app_structure"

    def test_malformed_mcp_only_two_parts_not_written(self, tmp_path):
        """mcp__server with no tool part should be ignored."""
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        data = json.dumps({"tool_name": "mcp__server", "tool_input": {}})
        _run_main(hook, data, log)
        assert not log.exists()

    def test_tool_name_with_extra_underscores_preserved(self, tmp_path):
        """mcp__server__tool__extra splits at first two __ only."""
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        data = json.dumps({
            "tool_name": "mcp__my-server__my_tool__extra",
            "tool_input": {},
        })
        _run_main(hook, data, log)
        entry = _read_log(log)[0]
        assert entry["server"] == "my-server"
        assert entry["tool"] == "my_tool__extra"


# ---------------------------------------------------------------------------
# Malformed JSON input
# ---------------------------------------------------------------------------


class TestMalformedJsonInput:
    def test_plain_text_does_not_crash(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        _run_main(hook, "this is not json", log)
        assert not log.exists()

    def test_empty_string_does_not_crash(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        _run_main(hook, "", log)
        assert not log.exists()

    def test_partial_json_does_not_crash(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        _run_main(hook, '{"tool_name": "mcp__s__t"', log)
        assert not log.exists()

    def test_null_json_no_log_written(self, tmp_path):
        """JSON 'null' parses successfully but main() raises AttributeError on .get().
        The outer __main__ guard catches it; calling main() directly surfaces the error.
        Either way, no JSONL entry should be written."""
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        try:
            _run_main(hook, "null", log)
        except AttributeError:
            pass  # expected — main() has no guard for non-dict JSON
        assert not log.exists()


# ---------------------------------------------------------------------------
# Long string truncation
# ---------------------------------------------------------------------------


class TestLongStringTruncation:
    def test_long_value_truncated_to_100_chars(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        long_str = "x" * 200
        data = json.dumps({
            "tool_name": "mcp__srv__tool",
            "tool_input": {"query": long_str},
        })
        _run_main(hook, data, log)
        entry = _read_log(log)[0]
        assert len(entry["input_summary"]["query"]) == 103  # 100 + "..."

    def test_long_value_ends_with_ellipsis(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        data = json.dumps({
            "tool_name": "mcp__srv__tool",
            "tool_input": {"query": "a" * 200},
        })
        _run_main(hook, data, log)
        entry = _read_log(log)[0]
        assert entry["input_summary"]["query"].endswith("...")

    def test_short_value_not_truncated(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        data = json.dumps({
            "tool_name": "mcp__srv__tool",
            "tool_input": {"query": "short"},
        })
        _run_main(hook, data, log)
        entry = _read_log(log)[0]
        assert entry["input_summary"]["query"] == "short"

    def test_exactly_100_chars_not_truncated(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        exact = "y" * 100
        data = json.dumps({
            "tool_name": "mcp__srv__tool",
            "tool_input": {"query": exact},
        })
        _run_main(hook, data, log)
        entry = _read_log(log)[0]
        assert entry["input_summary"]["query"] == exact

    def test_non_string_value_not_truncated(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        data = json.dumps({
            "tool_name": "mcp__srv__tool",
            "tool_input": {"count": 42, "flag": True},
        })
        _run_main(hook, data, log)
        entry = _read_log(log)[0]
        assert entry["input_summary"]["count"] == 42
        assert entry["input_summary"]["flag"] is True


# ---------------------------------------------------------------------------
# JSONL output correctness
# ---------------------------------------------------------------------------


class TestJsonlOutput:
    def test_output_is_valid_json(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        data = json.dumps({"tool_name": "mcp__srv__tool", "tool_input": {}})
        _run_main(hook, data, log)
        line = log.read_text().strip()
        parsed = json.loads(line)
        assert isinstance(parsed, dict)

    def test_multiple_calls_produce_multiple_lines(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        for i in range(3):
            data = json.dumps({
                "tool_name": f"mcp__srv__tool{i}",
                "tool_input": {},
            })
            _run_main(hook, data, log)
        entries = _read_log(log)
        assert len(entries) == 3

    def test_entry_keys_present(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "session-log.jsonl"
        data = json.dumps({"tool_name": "mcp__srv__tool", "tool_input": {}})
        _run_main(hook, data, log)
        entry = _read_log(log)[0]
        for key in ("ts", "session_id", "project", "server", "tool", "input_summary", "success"):
            assert key in entry, f"Missing key: {key}"

    def test_log_file_parent_dirs_created(self, tmp_path):
        hook = _load_hook()
        log = tmp_path / "deep" / "nested" / "dir" / "session-log.jsonl"
        data = json.dumps({"tool_name": "mcp__srv__tool", "tool_input": {}})
        _run_main(hook, data, log)
        assert log.exists()
