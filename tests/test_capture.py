"""Tests for orchestrator.capture module."""

import json
from pathlib import Path

import pytest

from orchestrator.capture import (
    append_log_entry,
    classify_sessions,
    find_transcript_path,
    group_by_session,
    read_session_log,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_LOG = FIXTURES_DIR / "sample_session_log.jsonl"


# ---------------------------------------------------------------------------
# append_log_entry
# ---------------------------------------------------------------------------


class TestAppendLogEntry:
    def test_creates_file_if_missing(self, tmp_path):
        log_file = tmp_path / "logs" / "session.jsonl"
        append_log_entry(log_file, {"session_id": "s1", "tool": "foo"})
        assert log_file.exists()

    def test_creates_parent_dirs(self, tmp_path):
        log_file = tmp_path / "a" / "b" / "c" / "log.jsonl"
        append_log_entry(log_file, {"session_id": "s1"})
        assert log_file.exists()

    def test_appended_entry_is_valid_json(self, tmp_path):
        log_file = tmp_path / "log.jsonl"
        entry = {"session_id": "s1", "tool": "get_app_structure", "success": True}
        append_log_entry(log_file, entry)
        line = log_file.read_text().strip()
        parsed = json.loads(line)
        assert parsed == entry

    def test_multiple_appends_produce_multiple_lines(self, tmp_path):
        log_file = tmp_path / "log.jsonl"
        append_log_entry(log_file, {"session_id": "s1", "seq": 1})
        append_log_entry(log_file, {"session_id": "s1", "seq": 2})
        append_log_entry(log_file, {"session_id": "s2", "seq": 3})
        lines = [l for l in log_file.read_text().splitlines() if l.strip()]
        assert len(lines) == 3

    def test_each_line_is_independent_json(self, tmp_path):
        log_file = tmp_path / "log.jsonl"
        entries = [{"seq": i, "val": f"v{i}"} for i in range(5)]
        for e in entries:
            append_log_entry(log_file, e)
        lines = [l for l in log_file.read_text().splitlines() if l.strip()]
        parsed = [json.loads(l) for l in lines]
        assert parsed == entries

    def test_non_serializable_value_uses_str_default(self, tmp_path):
        log_file = tmp_path / "log.jsonl"
        from datetime import datetime
        entry = {"ts": datetime(2026, 3, 20, 14, 0, 0), "tool": "foo"}
        # Should not raise
        append_log_entry(log_file, entry)
        line = log_file.read_text().strip()
        parsed = json.loads(line)
        assert parsed["tool"] == "foo"
        assert isinstance(parsed["ts"], str)

    def test_appends_to_existing_file(self, tmp_path):
        log_file = tmp_path / "log.jsonl"
        log_file.write_text('{"existing": true}\n')
        append_log_entry(log_file, {"new": True})
        lines = [l for l in log_file.read_text().splitlines() if l.strip()]
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"existing": True}
        assert json.loads(lines[1]) == {"new": True}


# ---------------------------------------------------------------------------
# read_session_log
# ---------------------------------------------------------------------------


class TestReadSessionLog:
    def test_returns_empty_list_for_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.jsonl"
        result = read_session_log(missing)
        assert result == []

    def test_reads_sample_fixture(self):
        entries = read_session_log(SAMPLE_LOG)
        assert len(entries) == 3

    def test_entries_are_dicts(self):
        entries = read_session_log(SAMPLE_LOG)
        for entry in entries:
            assert isinstance(entry, dict)

    def test_first_entry_session_id(self):
        entries = read_session_log(SAMPLE_LOG)
        assert entries[0]["session_id"] == "test-session-1"

    def test_last_entry_success_false(self):
        entries = read_session_log(SAMPLE_LOG)
        assert entries[-1]["success"] is False

    def test_reads_all_fields(self):
        entries = read_session_log(SAMPLE_LOG)
        first = entries[0]
        assert first["server"] == "commcare-hq"
        assert first["tool"] == "get_app_structure"
        assert first["project"] == "connect-labs"

    def test_ignores_blank_lines(self, tmp_path):
        log_file = tmp_path / "log.jsonl"
        log_file.write_text('{"a": 1}\n\n{"b": 2}\n\n')
        entries = read_session_log(log_file)
        assert len(entries) == 2

    def test_empty_file_returns_empty_list(self, tmp_path):
        log_file = tmp_path / "log.jsonl"
        log_file.write_text("")
        result = read_session_log(log_file)
        assert result == []

    def test_roundtrip_with_append(self, tmp_path):
        log_file = tmp_path / "log.jsonl"
        entries_in = [
            {"session_id": "s1", "tool": "foo", "success": True},
            {"session_id": "s2", "tool": "bar", "success": False},
        ]
        for e in entries_in:
            append_log_entry(log_file, e)
        entries_out = read_session_log(log_file)
        assert entries_out == entries_in


# ---------------------------------------------------------------------------
# group_by_session
# ---------------------------------------------------------------------------


class TestGroupBySession:
    def test_groups_two_sessions(self):
        entries = read_session_log(SAMPLE_LOG)
        groups = group_by_session(entries)
        assert set(groups.keys()) == {"test-session-1", "test-session-2"}

    def test_session_1_has_two_entries(self):
        entries = read_session_log(SAMPLE_LOG)
        groups = group_by_session(entries)
        assert len(groups["test-session-1"]) == 2

    def test_session_2_has_one_entry(self):
        entries = read_session_log(SAMPLE_LOG)
        groups = group_by_session(entries)
        assert len(groups["test-session-2"]) == 1

    def test_empty_entries_returns_empty_dict(self):
        assert group_by_session([]) == {}

    def test_missing_session_id_goes_to_unknown(self):
        entries = [{"tool": "foo"}, {"tool": "bar"}]
        groups = group_by_session(entries)
        assert "unknown" in groups
        assert len(groups["unknown"]) == 2

    def test_single_session_all_entries_grouped(self):
        entries = [{"session_id": "s1", "tool": f"tool{i}"} for i in range(5)]
        groups = group_by_session(entries)
        assert list(groups.keys()) == ["s1"]
        assert len(groups["s1"]) == 5

    def test_preserves_entry_order_within_group(self):
        entries = [
            {"session_id": "s1", "seq": 1},
            {"session_id": "s2", "seq": 2},
            {"session_id": "s1", "seq": 3},
        ]
        groups = group_by_session(entries)
        assert [e["seq"] for e in groups["s1"]] == [1, 3]


# ---------------------------------------------------------------------------
# classify_sessions
# ---------------------------------------------------------------------------


class TestClassifySessions:
    def test_sample_log_classifies_correctly(self):
        entries = read_session_log(SAMPLE_LOG)
        grouped = group_by_session(entries)
        result = classify_sessions(grouped)
        assert "test-session-1" in result["multi_server"]
        assert "test-session-2" in result["single_server"]

    def test_result_has_both_keys(self):
        result = classify_sessions({})
        assert "single_server" in result
        assert "multi_server" in result

    def test_empty_grouped_returns_empty_lists(self):
        result = classify_sessions({})
        assert result["single_server"] == []
        assert result["multi_server"] == []

    def test_single_server_session(self):
        grouped = {
            "s1": [
                {"server": "commcare-hq", "tool": "foo"},
                {"server": "commcare-hq", "tool": "bar"},
            ]
        }
        result = classify_sessions(grouped)
        assert "s1" in result["single_server"]
        assert "s1" not in result["multi_server"]

    def test_multi_server_session(self):
        grouped = {
            "s1": [
                {"server": "commcare-hq", "tool": "foo"},
                {"server": "solicitations", "tool": "bar"},
            ]
        }
        result = classify_sessions(grouped)
        assert "s1" in result["multi_server"]
        assert "s1" not in result["single_server"]



    def test_multiple_sessions_mixed(self):
        grouped = {
            "single": [{"server": "x"}, {"server": "x"}],
            "multi": [{"server": "x"}, {"server": "y"}],
        }
        result = classify_sessions(grouped)
        assert "single" in result["single_server"]
        assert "multi" in result["multi_server"]

    def test_missing_server_key_treated_as_none(self):
        grouped = {"s1": [{"tool": "foo"}, {"tool": "bar"}]}
        result = classify_sessions(grouped)
        # Both entries have server=None, so it's single_server
        assert "s1" in result["single_server"]


# ---------------------------------------------------------------------------
# find_transcript_path
# ---------------------------------------------------------------------------


class TestFindTranscriptPath:

    def test_path_ends_with_session_jsonl(self):
        result = find_transcript_path("my-session-id", "/some/project")
        assert result.name == "my-session-id.jsonl"

    def test_path_under_home_claude_projects(self):
        result = find_transcript_path("sid", "/foo/bar")
        assert result.parts[-4] == ".claude"
        assert result.parts[-3] == "projects"


    def test_slashes_replaced_with_dashes(self):
        result = find_transcript_path("sid", "/foo/bar/baz")
        parent_dir = result.parent.name
        assert parent_dir == "-foo-bar-baz"

    def test_simple_path(self):
        result = find_transcript_path("s1", "/Users/jjackson/projects/myapp")
        parent_dir = result.parent.name
        assert parent_dir == "-Users-jjackson-projects-myapp"

    def test_under_home_directory(self):
        result = find_transcript_path("s1", "/Users/jjackson/projects/myapp")
        assert result.parent.parent.name == "projects"
        assert result.parent.parent.parent.name == ".claude"
        assert result.parent.parent.parent.parent == Path.home()

    def test_session_id_preserved_exactly(self):
        session_id = "some-uuid-1234-abcd"
        result = find_transcript_path(session_id, "/any/path")
        assert result.stem == session_id
