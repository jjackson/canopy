"""Integration test — full flow from registry to corpus."""

from pathlib import Path
from orchestrator.registry import load_registry, format_for_skill, get_all_servers
from orchestrator.capture import append_log_entry, read_session_log, group_by_session, classify_sessions
from orchestrator.corpus import create_corpus_entry, save_corpus_entry, load_corpus_entry

FIXTURES = Path(__file__).parent / "fixtures"


def test_full_flow(tmp_path):
    """Test: load registry, log a session, classify it, create corpus entry."""
    # 1. Load registry
    reg = load_registry(FIXTURES / "sample_registry.yaml")
    servers = get_all_servers(reg)
    assert len(servers) == 2

    # 2. Format for skill context
    skill_context = format_for_skill(reg)
    assert "commcare-hq" in skill_context
    assert "create-solicitation" in skill_context

    # 3. Simulate a multi-server session
    log_file = tmp_path / "session-log.jsonl"
    append_log_entry(log_file, {
        "ts": "2026-03-20T14:32:01Z",
        "session_id": "integration-test",
        "project": "connect-labs",
        "server": "commcare-hq",
        "tool": "get_app_structure",
        "input_summary": {"app_id": "test"},
        "success": True,
    })
    append_log_entry(log_file, {
        "ts": "2026-03-20T14:32:15Z",
        "session_id": "integration-test",
        "project": "connect-labs",
        "server": "solicitations",
        "tool": "create_solicitation",
        "input_summary": {"program_id": 1},
        "success": True,
    })

    # 4. Read and classify
    entries = read_session_log(log_file)
    assert len(entries) == 2

    groups = group_by_session(entries)
    classified = classify_sessions(groups)
    assert "integration-test" in classified["multi_server"]

    # 5. Create corpus entry
    corpus_dir = tmp_path / "corpus"
    entry = create_corpus_entry(
        entry_id="test-solicitation",
        domain="connect",
        goal="Create a test solicitation",
        initial_prompt="Create a solicitation for test program",
        expected_servers=["commcare-hq", "solicitations"],
        expected_tool_sequence=[
            {"server": "commcare-hq", "tool": "get_app_structure", "mock_response": "{}"},
            {"server": "solicitations", "tool": "create_solicitation", "is_write": True, "mock_response": "{}"},
        ],
        tags=["test"],
    )

    path = save_corpus_entry(entry, corpus_dir)
    assert path.exists()

    loaded = load_corpus_entry(path)
    assert loaded["id"] == "test-solicitation"
    assert loaded["complexity"] == "multi-server"
