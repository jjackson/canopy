"""Tests for orchestrator.corpus module."""

from pathlib import Path

import pytest

from orchestrator.corpus import (
    create_corpus_entry,
    list_corpus_entries,
    load_corpus_entry,
    save_corpus_entry,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_entry(
    entry_id: str = "entry-001",
    domain: str = "connect",
    expected_servers: list[str] | None = None,
    **kwargs,
) -> dict:
    if expected_servers is None:
        expected_servers = ["commcare-hq"]
    return create_corpus_entry(
        entry_id=entry_id,
        domain=domain,
        goal="Test goal",
        initial_prompt="Do a thing",
        expected_servers=expected_servers,
        expected_tool_sequence=[{"server": s, "tool": "some_tool"} for s in expected_servers],
        **kwargs,
    )


# ---------------------------------------------------------------------------
# create_corpus_entry — complexity field
# ---------------------------------------------------------------------------


class TestCreateCorpusEntryComplexity:
    def test_multi_server_complexity_for_two_servers(self):
        entry = _make_entry(expected_servers=["commcare-hq", "solicitations"])
        assert entry["complexity"] == "multi-server"

    def test_multi_server_complexity_for_three_servers(self):
        entry = _make_entry(expected_servers=["srv-a", "srv-b", "srv-c"])
        assert entry["complexity"] == "multi-server"

    def test_single_server_complexity_for_one_server(self):
        entry = _make_entry(expected_servers=["commcare-hq"])
        assert entry["complexity"] == "single-server"

    def test_single_server_complexity_explicitly(self):
        entry = create_corpus_entry(
            entry_id="e1",
            domain="test",
            goal="G",
            initial_prompt="P",
            expected_servers=["only-server"],
            expected_tool_sequence=[],
        )
        assert entry["complexity"] == "single-server"


# ---------------------------------------------------------------------------
# create_corpus_entry — field correctness
# ---------------------------------------------------------------------------


class TestCreateCorpusEntryFields:
    def test_id_is_preserved(self):
        entry = _make_entry(entry_id="my-id-123")
        assert entry["id"] == "my-id-123"

    def test_domain_is_preserved(self):
        entry = _make_entry(domain="finance")
        assert entry["domain"] == "finance"

    def test_goal_is_preserved(self):
        entry = create_corpus_entry(
            entry_id="e1", domain="d", goal="My specific goal",
            initial_prompt="P", expected_servers=["s"], expected_tool_sequence=[],
        )
        assert entry["goal"] == "My specific goal"

    def test_initial_prompt_preserved(self):
        entry = create_corpus_entry(
            entry_id="e1", domain="d", goal="G",
            initial_prompt="My prompt text",
            expected_servers=["s"], expected_tool_sequence=[],
        )
        assert entry["initial_prompt"] == "My prompt text"

    def test_default_outcome_is_success(self):
        entry = _make_entry()
        assert entry["outcome"] == "success"

    def test_custom_outcome_preserved(self):
        entry = _make_entry(outcome="failure")
        assert entry["outcome"] == "failure"

    def test_failure_reason_defaults_none(self):
        entry = _make_entry()
        assert entry["failure_reason"] is None

    def test_failure_reason_preserved(self):
        entry = _make_entry(failure_reason="Timeout")
        assert entry["failure_reason"] == "Timeout"

    def test_tags_defaults_to_empty_list(self):
        entry = _make_entry()
        assert entry["tags"] == []

    def test_custom_tags_preserved(self):
        entry = _make_entry(tags=["regression", "smoke"])
        assert entry["tags"] == ["regression", "smoke"]

    def test_prompts_defaults_to_list_with_initial(self):
        entry = create_corpus_entry(
            entry_id="e1", domain="d", goal="G",
            initial_prompt="My prompt",
            expected_servers=["s"], expected_tool_sequence=[],
        )
        assert entry["prompts"] == ["My prompt"]

    def test_custom_prompts_preserved(self):
        entry = create_corpus_entry(
            entry_id="e1", domain="d", goal="G",
            initial_prompt="P",
            expected_servers=["s"], expected_tool_sequence=[],
            prompts=["first", "second"],
        )
        assert entry["prompts"] == ["first", "second"]

    def test_expected_servers_preserved(self):
        servers = ["srv-a", "srv-b"]
        entry = _make_entry(expected_servers=servers)
        assert entry["expected_servers"] == servers

    def test_expected_tool_sequence_preserved(self):
        seq = [{"server": "s", "tool": "t"}]
        entry = create_corpus_entry(
            entry_id="e1", domain="d", goal="G",
            initial_prompt="P",
            expected_servers=["s"], expected_tool_sequence=seq,
        )
        assert entry["expected_tool_sequence"] == seq

    def test_created_date_is_string(self):
        entry = _make_entry()
        assert isinstance(entry["created"], str)

    def test_eval_results_defaults_empty(self):
        entry = _make_entry()
        assert entry["eval_results"] == []

    def test_expected_outcome_type_is_task_completed(self):
        entry = _make_entry()
        assert entry["expected_outcome"]["type"] == "task_completed"


# ---------------------------------------------------------------------------
# save_corpus_entry / load_corpus_entry round-trip
# ---------------------------------------------------------------------------


class TestSaveLoadRoundTrip:
    def test_saved_file_exists(self, tmp_path):
        entry = _make_entry(domain="connect")
        path = save_corpus_entry(entry, tmp_path)
        assert path.exists()

    def test_saved_file_in_domain_subdirectory(self, tmp_path):
        entry = _make_entry(domain="connect")
        path = save_corpus_entry(entry, tmp_path)
        assert path.parent.name == "connect"

    def test_saved_filename_matches_entry_id(self, tmp_path):
        entry = _make_entry(entry_id="my-entry-id", domain="connect")
        path = save_corpus_entry(entry, tmp_path)
        assert path.stem == "my-entry-id"

    def test_saved_file_has_yaml_extension(self, tmp_path):
        entry = _make_entry(domain="connect")
        path = save_corpus_entry(entry, tmp_path)
        assert path.suffix == ".yaml"

    def test_round_trip_id(self, tmp_path):
        entry = _make_entry(entry_id="round-trip-001")
        path = save_corpus_entry(entry, tmp_path)
        loaded = load_corpus_entry(path)
        assert loaded["id"] == "round-trip-001"

    def test_round_trip_domain(self, tmp_path):
        entry = _make_entry(domain="finance")
        path = save_corpus_entry(entry, tmp_path)
        loaded = load_corpus_entry(path)
        assert loaded["domain"] == "finance"

    def test_round_trip_complexity(self, tmp_path):
        entry = _make_entry(expected_servers=["a", "b"])
        path = save_corpus_entry(entry, tmp_path)
        loaded = load_corpus_entry(path)
        assert loaded["complexity"] == "multi-server"

    def test_round_trip_tags(self, tmp_path):
        entry = _make_entry(tags=["foo", "bar"])
        path = save_corpus_entry(entry, tmp_path)
        loaded = load_corpus_entry(path)
        assert loaded["tags"] == ["foo", "bar"]

    def test_round_trip_expected_servers(self, tmp_path):
        servers = ["srv-1", "srv-2"]
        entry = _make_entry(expected_servers=servers)
        path = save_corpus_entry(entry, tmp_path)
        loaded = load_corpus_entry(path)
        assert loaded["expected_servers"] == servers

    def test_save_creates_parent_dirs(self, tmp_path):
        corpus_dir = tmp_path / "nested" / "corpus"
        entry = _make_entry(domain="connect")
        path = save_corpus_entry(entry, corpus_dir)
        assert path.exists()

    def test_returns_path_object(self, tmp_path):
        entry = _make_entry()
        result = save_corpus_entry(entry, tmp_path)
        assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# list_corpus_entries
# ---------------------------------------------------------------------------


class TestListCorpusEntries:
    def _populate(self, tmp_path: Path) -> Path:
        """Create a small corpus with two domains."""
        for domain, entry_id in [("connect", "e1"), ("connect", "e2"), ("finance", "e3")]:
            entry = _make_entry(entry_id=entry_id, domain=domain)
            save_corpus_entry(entry, tmp_path)
        return tmp_path

    def test_returns_all_entries(self, tmp_path):
        corpus_dir = self._populate(tmp_path)
        paths = list_corpus_entries(corpus_dir)
        assert len(paths) == 3

    def test_all_paths_are_yaml(self, tmp_path):
        corpus_dir = self._populate(tmp_path)
        paths = list_corpus_entries(corpus_dir)
        for p in paths:
            assert p.suffix == ".yaml"

    def test_returns_path_objects(self, tmp_path):
        corpus_dir = self._populate(tmp_path)
        paths = list_corpus_entries(corpus_dir)
        for p in paths:
            assert isinstance(p, Path)

    def test_domain_filter_returns_only_matching(self, tmp_path):
        corpus_dir = self._populate(tmp_path)
        paths = list_corpus_entries(corpus_dir, domain="connect")
        assert len(paths) == 2
        for p in paths:
            assert p.parent.name == "connect"

    def test_domain_filter_finance(self, tmp_path):
        corpus_dir = self._populate(tmp_path)
        paths = list_corpus_entries(corpus_dir, domain="finance")
        assert len(paths) == 1
        assert paths[0].stem == "e3"

    def test_nonexistent_domain_returns_empty(self, tmp_path):
        corpus_dir = self._populate(tmp_path)
        paths = list_corpus_entries(corpus_dir, domain="does-not-exist")
        assert paths == []

    def test_empty_corpus_returns_empty(self, tmp_path):
        paths = list_corpus_entries(tmp_path)
        assert paths == []

    def test_results_are_sorted(self, tmp_path):
        corpus_dir = self._populate(tmp_path)
        paths = list_corpus_entries(corpus_dir)
        names = [p.stem for p in paths]
        assert names == sorted(names)

    def test_no_domain_filter_spans_all_domains(self, tmp_path):
        corpus_dir = self._populate(tmp_path)
        paths = list_corpus_entries(corpus_dir)
        domains = {p.parent.name for p in paths}
        assert "connect" in domains
        assert "finance" in domains
