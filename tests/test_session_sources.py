"""Tests for the session-source seam (`orchestrator.session_sources`).

This is the fix for the cross-user blind spot: `agent_coverage` used to scan
only `Path.home() / ".claude" / "projects"` — the CURRENT user's home. JJ
alternates macOS accounts (acedimagi + jjackson); a skill that only ever fired
on the OTHER account read as `never_live`, inverting the report's conclusion
(see `session_sources.py`'s module docstring for the full hal/architect story).
These tests prove the seam itself: N typed sources, one adapter per `kind`, a
configured-but-unadapted `kind` degrades LOUD instead of being dropped, and
`harvest.user_session_roots` still returns its original shape.
"""
import json

from orchestrator.harvest import user_session_roots
from orchestrator.session_sources import (
    SessionSource,
    corpus_confidence,
    discover_local_sources,
    local_transcript_dirs,
    session_sources,
)


def _fake_home(tmp_path, user, readable=True):
    home = tmp_path / user
    projects = home / ".claude" / "projects"
    projects.mkdir(parents=True)
    if not readable:
        projects.chmod(0o000)
    return home


def test_discover_local_sources_finds_every_user_with_a_projects_dir(tmp_path):
    _fake_home(tmp_path, "jjackson")
    _fake_home(tmp_path, "acedimagi")
    (tmp_path / "Shared").mkdir()  # no .claude/projects -- must be skipped

    sources = discover_local_sources(users_root=str(tmp_path))
    names = sorted(s.name for s in sources)
    assert names == ["local:acedimagi", "local:jjackson"]
    assert all(s.kind == "local" and s.readable for s in sources)


def test_discover_local_sources_flags_unreadable_dir(tmp_path):
    _fake_home(tmp_path, "jjackson")
    home = _fake_home(tmp_path, "acedimagi", readable=False)
    try:
        sources = discover_local_sources(users_root=str(tmp_path))
        by = {s.name: s for s in sources}
        assert by["local:acedimagi"].readable is False
        assert by["local:acedimagi"].reason
        assert by["local:jjackson"].readable is True
    finally:
        (home / ".claude" / "projects").chmod(0o755)  # let tmp_path cleanup work


def test_session_sources_auto_discovers_when_no_config(tmp_path):
    _fake_home(tmp_path, "jjackson")
    missing_config = tmp_path / "no-such-config.json"
    sources = session_sources(config_path=missing_config, users_root=str(tmp_path))
    assert [s.name for s in sources] == ["local:jjackson"]


def test_session_sources_config_wins_over_auto_discovery(tmp_path):
    _fake_home(tmp_path, "jjackson")  # would be auto-discovered if config absent
    other = tmp_path / "elsewhere"
    other.mkdir()
    config = tmp_path / "session-sources.json"
    config.write_text(json.dumps({"sources": [
        {"name": "local:configured", "kind": "local", "location": str(other)},
    ]}))
    sources = session_sources(config_path=config, users_root=str(tmp_path))
    assert [s.name for s in sources] == ["local:configured"]
    assert sources[0].readable is True


def test_session_sources_unknown_kind_is_not_dropped(tmp_path):
    """A configured source whose kind has no registered adapter must come back
    readable=False with a non-empty reason -- NEVER silently dropped. That's
    the forward-compat property: configuring a cloud runtime before its
    adapter exists degrades the report LOUD instead of quietly under-reporting."""
    config = tmp_path / "session-sources.json"
    config.write_text(json.dumps({"sources": [
        {"name": "cloud:hal-runtime", "kind": "cloud", "location": "s3://hal-sessions/"},
    ]}))
    sources = session_sources(config_path=config, users_root=str(tmp_path))
    assert len(sources) == 1
    assert sources[0].readable is False
    assert "cloud" in sources[0].reason
    assert sources[0].name == "cloud:hal-runtime"


def test_session_sources_unreadable_configured_local_source(tmp_path):
    home = _fake_home(tmp_path, "jjackson", readable=False)
    config = tmp_path / "session-sources.json"
    projects = home / ".claude" / "projects"
    config.write_text(json.dumps({"sources": [
        {"name": "local:jjackson", "kind": "local", "location": str(projects)},
    ]}))
    try:
        sources = session_sources(config_path=config, users_root=str(tmp_path))
        assert sources[0].readable is False
        assert sources[0].reason
    finally:
        projects.chmod(0o755)


def test_local_transcript_dirs_filters_to_readable_local_only():
    sources = [
        SessionSource(name="local:a", kind="local", location="/a", readable=True),
        SessionSource(name="local:b", kind="local", location="/b", readable=False, reason="x"),
        SessionSource(name="cloud:c", kind="cloud", location="s3://c", readable=True),
    ]
    dirs = local_transcript_dirs(sources)
    assert [str(d) for d in dirs] == ["/a"]


def test_corpus_confidence_whole_corpus_when_all_readable():
    sources = [
        SessionSource(name="local:a", kind="local", location="/a", readable=True),
        SessionSource(name="local:b", kind="local", location="/b", readable=True),
    ]
    assert corpus_confidence(sources) == "whole-corpus"


def test_corpus_confidence_half_blind_when_any_unreadable():
    sources = [
        SessionSource(name="local:a", kind="local", location="/a", readable=True),
        SessionSource(name="local:b", kind="local", location="/b", readable=False, reason="x"),
    ]
    assert corpus_confidence(sources) == "half-blind"


def test_harvest_user_session_roots_shape_unchanged(tmp_path):
    """harvest.user_session_roots is now a thin delegating wrapper over
    session_sources.discover_local_sources -- its return shape (list of
    {"user", "path", "readable"} dicts) must be byte-for-byte what it was
    before the extraction, since existing callers/tests depend on it."""
    _fake_home(tmp_path, "jjackson")
    _fake_home(tmp_path, "acedimagi")
    roots = user_session_roots(users_root=str(tmp_path))
    assert sorted(r["user"] for r in roots) == ["acedimagi", "jjackson"]
    for r in roots:
        assert set(r.keys()) == {"user", "path", "readable"}
        assert r["readable"] is True
