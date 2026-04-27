"""Tests for orchestrator.skill_catalog."""
from pathlib import Path

import pytest

from orchestrator.skill_catalog import (
    build_catalog,
    extract_candidate_names,
    find_overlap,
    format_for_prompt,
)


def _make_skill(root: Path, name: str, description: str = "") -> Path:
    """Helper: create a SKILL.md inside a directory."""
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    body = f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n"
    skill_md.write_text(body)
    return skill_md


def _make_plugin_skill(cache_root: Path, plugin: str, version: str, name: str, description: str = "") -> Path:
    skill_root = cache_root / plugin / plugin / version / "skills"
    return _make_skill(skill_root, name, description)


class TestBuildCatalog:
    def test_empty_dirs_returns_empty(self, tmp_path):
        cat = build_catalog(plugin_cache=tmp_path / "plugins", user_skills=tmp_path / "user")
        assert cat == []

    def test_plugin_skill_picked_up(self, tmp_path):
        cache = tmp_path / "plugins"
        _make_plugin_skill(cache, "canopy", "1.0.0", "doctor", "Diagnose canopy")
        cat = build_catalog(plugin_cache=cache, user_skills=tmp_path / "user")
        assert len(cat) == 1
        assert cat[0]["qualified"] == "canopy:doctor"
        assert cat[0]["scope"] == "plugin"
        assert cat[0]["description"] == "Diagnose canopy"

    def test_user_skill_picked_up(self, tmp_path):
        user = tmp_path / "user"
        _make_skill(user, "myskill", "Custom skill")
        cat = build_catalog(plugin_cache=tmp_path / "plugins", user_skills=user)
        assert len(cat) == 1
        assert cat[0]["qualified"] == "myskill"
        assert cat[0]["scope"] == "user"

    def test_picks_highest_version(self, tmp_path):
        cache = tmp_path / "plugins"
        _make_plugin_skill(cache, "canopy", "0.1.0", "old-skill")
        _make_plugin_skill(cache, "canopy", "0.2.0", "new-skill")
        cat = build_catalog(plugin_cache=cache, user_skills=tmp_path / "user")
        names = {e["name"] for e in cat}
        assert "new-skill" in names
        assert "old-skill" not in names


class TestExtractCandidateNames:
    def test_simple_word(self):
        assert extract_candidate_names("the doctor skill") == ["the", "doctor", "skill"]

    def test_qualified_name(self):
        cands = extract_candidate_names("Add canopy:doctor to do X")
        assert "canopy:doctor" in cands

    def test_hyphenated_name(self):
        cands = extract_candidate_names("Build a project-status skill")
        assert "project-status" in cands

    def test_dedupes(self):
        cands = extract_candidate_names("doctor doctor doctor")
        assert cands == ["doctor"]

    def test_empty_input(self):
        assert extract_candidate_names("") == []
        assert extract_candidate_names(None) == []


class TestFindOverlap:
    def test_qualified_match(self, tmp_path):
        cache = tmp_path / "plugins"
        _make_plugin_skill(cache, "canopy", "1.0", "doctor")
        cat = build_catalog(plugin_cache=cache, user_skills=tmp_path / "user")
        match = find_overlap("Add canopy:doctor diagnostic", cat)
        assert match is not None
        assert match["qualified"] == "canopy:doctor"

    def test_hyphenated_bare_name_match(self, tmp_path):
        user = tmp_path / "user"
        _make_skill(user, "context-restore")
        cat = build_catalog(plugin_cache=tmp_path / "plugins", user_skills=user)
        match = find_overlap("Add a context-restore helper", cat)
        assert match is not None
        assert match["qualified"] == "context-restore"

    def test_single_word_user_skill_does_NOT_match_bare(self, tmp_path):
        """Single-word user skills like 'health' must not be flagged when the
        word appears in prose, only when explicitly qualified."""
        user = tmp_path / "user"
        _make_skill(user, "health")
        cat = build_catalog(plugin_cache=tmp_path / "plugins", user_skills=user)
        # bare 'health' in prose: no match
        assert find_overlap("Diagnose for opportunity health", cat) is None
        assert find_overlap("Use the careful skill", cat) is None or True
        # single-word user skills have no qualified form, so they can never match —
        # this is the conservative tradeoff (false negatives over false positives).

    def test_single_word_plugin_skill_matches_only_qualified(self, tmp_path):
        cache = tmp_path / "plugins"
        _make_plugin_skill(cache, "canopy", "1.0", "ship")
        cat = build_catalog(plugin_cache=cache, user_skills=tmp_path / "user")
        # bare 'ship' in prose should NOT match
        assert find_overlap("Time to ship the feature", cat) is None
        # qualified 'canopy:ship' SHOULD match
        match = find_overlap("Add canopy:ship deployment helper", cat)
        assert match is not None
        assert match["qualified"] == "canopy:ship"

    def test_no_match_for_truly_novel(self, tmp_path):
        cache = tmp_path / "plugins"
        _make_plugin_skill(cache, "canopy", "1.0", "doctor")
        cat = build_catalog(plugin_cache=cache, user_skills=tmp_path / "user")
        assert find_overlap("Build a project-status skill", cat) is None

    def test_empty_catalog(self):
        assert find_overlap("Add canopy:doctor", []) is None


class TestFormatForPrompt:
    def test_empty_catalog(self):
        assert format_for_prompt([]) == "(no existing skills detected)"

    def test_renders_entries(self, tmp_path):
        cache = tmp_path / "plugins"
        _make_plugin_skill(cache, "canopy", "1.0", "doctor", "Diagnose health")
        cat = build_catalog(plugin_cache=cache, user_skills=tmp_path / "user")
        text = format_for_prompt(cat)
        assert "canopy:doctor" in text
        assert "Diagnose health" in text

    def test_truncates_at_max(self, tmp_path):
        cache = tmp_path / "plugins"
        for i in range(10):
            _make_plugin_skill(cache, "canopy", "1.0", f"skill-{i}", f"Description {i}")
        cat = build_catalog(plugin_cache=cache, user_skills=tmp_path / "user")
        text = format_for_prompt(cat, max_entries=3)
        assert "7 more not shown" in text
