"""Tests for repo_map.infer_repo_from_project_key + resolve_repo.

Surfaced when a strict `repo == 'jjackson/ace'` session-review filter found
only 2 of 8 known ace worktree sessions because the others' worktrees had
been deleted before the post_tool_use hook ever fired for them. The hook
captures the right thing live; these helpers cover the past-or-deleted case
by inferring `owner/repo` from the emdash path convention and
cross-referencing against existing repo_map values.
"""
from orchestrator.repo_map import (
    infer_repo_from_project_key,
    resolve_repo,
)


class TestInferRepoFromProjectKey:
    def test_worktree_path_simple(self):
        repo_map = {"-Users-jon-emdash-worktrees-ace-emdash-current": "jjackson/ace"}
        # A different worktree of the same repo, not in the map yet
        result = infer_repo_from_project_key(
            "-Users-jon-emdash-worktrees-ace-emdash-deleted-branch",
            repo_map,
        )
        assert result == "jjackson/ace"

    def test_worktree_path_with_hyphenated_repo_name(self):
        # Repo names with hyphens (ace-web, canopy-web) must round-trip cleanly.
        repo_map = {
            "-Users-jon-emdash-worktrees-ace-web-emdash-current": "jjackson/ace-web",
        }
        result = infer_repo_from_project_key(
            "-Users-jon-emdash-worktrees-ace-web-emdash-new-feature-xyz",
            repo_map,
        )
        assert result == "jjackson/ace-web"

    def test_repositories_path(self):
        # Main checkouts (rarely used directly, but should still work)
        repo_map = {"-Users-jon-emdash-worktrees-ace-emdash-current": "jjackson/ace"}
        result = infer_repo_from_project_key(
            "-Users-jon-emdash-repositories-ace",
            repo_map,
        )
        assert result == "jjackson/ace"

    def test_unknown_short_name_returns_none(self):
        # If no existing entry matches the short name, we don't guess.
        repo_map = {"-Users-jon-emdash-worktrees-ace-emdash-current": "jjackson/ace"}
        result = infer_repo_from_project_key(
            "-Users-jon-emdash-worktrees-totally-unknown-emdash-x",
            repo_map,
        )
        assert result is None

    def test_ambiguous_short_name_returns_none(self):
        # Two different owners both have a repo called "scout" — refuse to guess.
        repo_map = {
            "-Users-jon-emdash-worktrees-scout-emdash-a": "owner1/scout",
            "-Users-jon-emdash-worktrees-scout-emdash-b": "owner2/scout",
        }
        result = infer_repo_from_project_key(
            "-Users-jon-emdash-worktrees-scout-emdash-other",
            repo_map,
        )
        assert result is None

    def test_non_emdash_path_returns_none(self):
        # Non-emdash conventions (project keys outside ~/emdash/) yield nothing.
        repo_map = {"-Users-jon-emdash-worktrees-ace-emdash-current": "jjackson/ace"}
        result = infer_repo_from_project_key(
            "-Users-jon-Documents-ace",
            repo_map,
        )
        assert result is None

    def test_empty_repo_map(self):
        # No reference values to cross-check against.
        result = infer_repo_from_project_key(
            "-Users-jon-emdash-worktrees-ace-emdash-current",
            {},
        )
        assert result is None

    def test_short_name_substring_does_not_falsely_match(self):
        # An existing "owner/ace-web" must NOT satisfy a lookup for short="ace".
        repo_map = {"-Users-jon-emdash-worktrees-ace-web-emdash-x": "jjackson/ace-web"}
        result = infer_repo_from_project_key(
            "-Users-jon-emdash-worktrees-ace-emdash-deleted",
            repo_map,
        )
        assert result is None  # only "ace-web" exists; "ace" is unknown


class TestResolveRepo:
    def test_direct_hit_wins(self):
        # Direct lookups take precedence over inference (the hook is truth).
        repo_map = {
            "-Users-jon-emdash-worktrees-ace-emdash-x": "jjackson/ace-fork",
            "-Users-jon-emdash-worktrees-ace-emdash-y": "jjackson/ace",
        }
        assert resolve_repo(repo_map, "-Users-jon-emdash-worktrees-ace-emdash-x") == "jjackson/ace-fork"

    def test_falls_back_to_inference_when_missing(self):
        repo_map = {"-Users-jon-emdash-worktrees-ace-emdash-current": "jjackson/ace"}
        # Different (deleted) worktree of the same repo
        result = resolve_repo(repo_map, "-Users-jon-emdash-worktrees-ace-emdash-gone")
        assert result == "jjackson/ace"

    def test_returns_none_when_neither_path_works(self):
        repo_map = {"-Users-jon-emdash-worktrees-ace-emdash-x": "jjackson/ace"}
        result = resolve_repo(repo_map, "-Users-jon-some-random-path")
        assert result is None
