"""Tests for `canopy agent coverage` — bring-up lens (declared surface vs. actual firing)."""
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from orchestrator.agent_coverage import (
    _parse_ts,
    burst_of,
    classify,
    compute_bursts,
    declared_skills,
    evidence_from_entries,
    parent_of,
    persona_info,
    scan_evidence,
    skill_git_facts,
)

NOW = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)


def _ts(day, hour=9, sid="s1"):
    return (datetime(2026, 7, day, hour, 0, 0, tzinfo=timezone.utc), sid)


def _assistant(content, ts="2026-07-09T09:00:00Z"):
    return {"type": "assistant", "timestamp": ts, "message": {"content": content}}


def _user_text(text, ts="2026-07-09T09:00:00Z"):
    return {"type": "user", "timestamp": ts,
            "message": {"content": [{"type": "text", "text": text}]}}


def test_compute_bursts_merges_consecutive_days_and_splits_on_gap():
    # The real eva timeline: 07-01,02 | (6 dark days) | 07-09,10 | (2 dark) | 07-13,14,15
    stamps = [
        _ts(1, sid="a"), _ts(2, sid="b"),
        _ts(9, sid="c"), _ts(10, sid="d"),
        _ts(13, sid="e"), _ts(14, sid="f"), _ts(15, sid="g"),
    ]
    bursts = compute_bursts(stamps, gap_days=2)
    assert [(b["id"], b["start"], b["end"], b["active_days"]) for b in bursts] == [
        (1, "2026-07-01", "2026-07-02", 2),
        (2, "2026-07-09", "2026-07-10", 2),
        (3, "2026-07-13", "2026-07-15", 3),
    ]


def test_compute_bursts_counts_distinct_sessions():
    stamps = [_ts(1, 9, "a"), _ts(1, 10, "a"), _ts(1, 11, "b"), _ts(2, 9, "b")]
    bursts = compute_bursts(stamps, gap_days=2)
    assert len(bursts) == 1
    assert bursts[0]["sessions"] == 2  # a, b — not 4 entries
    assert bursts[0]["active_days"] == 2


def test_compute_bursts_gap_boundary_is_inclusive():
    # gap_days=2 means: a >=2-day gap splits. 07-01 -> 07-02 is contiguous (gap 1).
    assert len(compute_bursts([_ts(1), _ts(2)], gap_days=2)) == 1
    # 07-01 -> 07-03 is a 2-day gap: splits.
    assert len(compute_bursts([_ts(1), _ts(3)], gap_days=2)) == 2


def test_compute_bursts_empty():
    assert compute_bursts([], gap_days=2) == []


def test_evidence_counts_skill_tool_call():
    entries = [_assistant([
        {"type": "tool_use", "name": "Skill", "input": {"skill": "eva:lead-outreach"}}])]
    ev = evidence_from_entries(entries, "eva", ["lead-outreach"])
    assert len(ev["lead-outreach"]) == 1
    assert ev["lead-outreach"][0]["kind"] == "skill_tool_call"


def test_evidence_counts_skill_md_read():
    entries = [_assistant([
        {"type": "tool_use", "name": "Read",
         "input": {"file_path": "/Users/j/emdash/repositories/eva/skills/turn/SKILL.md"}}])]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert len(ev["turn"]) == 1
    assert ev["turn"][0]["kind"] == "skill_md_read"


def test_evidence_counts_slash_invocation_in_text():
    entries = [_user_text("go do /eva:turn now please")]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert ev["turn"][0]["kind"] == "slash_invocation"


def test_bare_mention_in_tool_result_is_not_evidence():
    """THE false-positive guard: `ls skills/` output and git diffs must not count."""
    entries = [
        {"type": "user", "timestamp": "2026-07-09T09:00:00Z", "message": {"content": [
            {"type": "tool_result",
             "content": "skills/cea-botec/SKILL.md\nskills/reviewer/SKILL.md"}]}},
        {"type": "user", "timestamp": "2026-07-09T09:00:00Z", "message": {"content": [
            {"type": "tool_result",
             "content": "diff --git a/skills/cea-botec/SKILL.md b/skills/cea-botec/SKILL.md"}]}},
    ]
    ev = evidence_from_entries(entries, "eva", ["cea-botec", "reviewer"])
    assert ev == {}


def test_evidence_does_not_confuse_similar_skill_names():
    entries = [_assistant([
        {"type": "tool_use", "name": "Read",
         "input": {"file_path": "/Users/j/emdash/repositories/eva/skills/turn-review/SKILL.md"}}])]
    ev = evidence_from_entries(entries, "eva", ["turn", "turn-review"])
    assert "turn" not in ev
    assert len(ev["turn-review"]) == 1


def test_scan_evidence_tags_transcript_path():
    entries = [_assistant([
        {"type": "tool_use", "name": "Skill", "input": {"skill": "eva:turn"}}])]
    ev = scan_evidence([Path("/tmp/a.jsonl")], "eva", ["turn"], reader=lambda p: entries)
    assert ev["turn"][0]["transcript"] == "/tmp/a.jsonl"


# --- FINDING 1: cross-agent false "live" ------------------------------------

def test_skill_md_read_matches_owning_agent_repo_layout():
    entries = [_assistant([
        {"type": "tool_use", "name": "Read",
         "input": {"file_path": "/Users/j/emdash/repositories/eva/skills/turn/SKILL.md"}}])]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert len(ev["turn"]) == 1


def test_skill_md_read_matches_owning_agent_worktree_layout():
    entries = [_assistant([
        {"type": "tool_use", "name": "Read",
         "input": {"file_path":
                   "/Users/j/emdash/worktrees/eva/emdash/feat-x/skills/turn/SKILL.md"}}])]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert len(ev["turn"]) == 1


def test_skill_md_read_does_not_match_foreign_agent_path():
    """eva's transcript reading ace's turn skill must NOT count as eva's turn firing."""
    entries = [_assistant([
        {"type": "tool_use", "name": "Read",
         "input": {"file_path": "/Users/j/emdash/repositories/ace/skills/turn/SKILL.md"}}])]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert ev == {}


def test_skill_tool_call_accepts_bare_skill_name():
    entries = [_assistant([
        {"type": "tool_use", "name": "Skill", "input": {"skill": "turn"}}])]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert len(ev["turn"]) == 1


def test_skill_tool_call_accepts_own_namespace():
    entries = [_assistant([
        {"type": "tool_use", "name": "Skill", "input": {"skill": "eva:turn"}}])]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert len(ev["turn"]) == 1


def test_skill_tool_call_rejects_foreign_namespace():
    """A Skill call with input.skill='ace:turn' must not count as eva's turn firing."""
    entries = [_assistant([
        {"type": "tool_use", "name": "Skill", "input": {"skill": "ace:turn"}}])]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert ev == {}


# --- FINDING 2: _parse_ts must return aware datetimes -----------------------

def test_parse_ts_naive_string_returns_aware_datetime():
    dt = _parse_ts("2026-07-09T09:00:00")
    assert dt is not None
    assert dt.tzinfo is not None


def test_parse_ts_z_suffixed_string_stays_utc_and_unchanged():
    dt = _parse_ts("2026-07-09T09:00:00Z")
    assert dt == datetime(2026, 7, 9, 9, 0, 0, tzinfo=timezone.utc)


# --- FINDING 3: unparseable timestamp must not produce ts=None evidence -----

def test_entry_with_unparseable_timestamp_yields_no_evidence():
    entries = [_assistant(
        [{"type": "tool_use", "name": "Skill", "input": {"skill": "turn"}}],
        ts="not-a-timestamp",
    )]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert ev == {}


# --- FINDING A: coincidental path-segment slug must not match ------------------

def test_skill_md_read_does_not_match_fixture_with_coincidental_slug():
    """eva's transcript reading a fixture that happens to have /eva/ in its path
    must NOT count as eva's turn firing (NEW false-positive case from canopy fixtures)."""
    entries = [_assistant([
        {"type": "tool_use", "name": "Read",
         "input": {"file_path":
                   "/Users/j/emdash/repositories/canopy/tests/fixtures/eva/skills/turn/SKILL.md"}}])]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert ev == {}


def test_skill_md_read_matches_worktree_shallow_layout():
    """Worktree layouts vary in depth; /worktrees/eva/feat-x/skills/... must match."""
    entries = [_assistant([
        {"type": "tool_use", "name": "Read",
         "input": {"file_path":
                   "/Users/j/emdash/worktrees/eva/feat-x/skills/turn/SKILL.md"}}])]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert len(ev["turn"]) == 1


# --- FINDING B: slash_invocation must reject foreign namespaces ----------------

def test_slash_invocation_rejects_foreign_namespace():
    """Scanning eva for skill turn, the text "go run /ace:turn now" yields no evidence."""
    entries = [_user_text("go run /ace:turn now")]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert ev == {}


def test_slash_invocation_accepts_own_namespace():
    """Scanning eva for skill turn, the text "go run /eva:turn now" yields evidence."""
    entries = [_user_text("go run /eva:turn now")]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert len(ev["turn"]) == 1
    assert ev["turn"][0]["kind"] == "slash_invocation"


# --- Task 3: declared surface -----------------------------------------------


def _mkrepo(tmp_path, skills, persona=None):
    for s in skills:
        d = tmp_path / "skills" / s
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\nname: {s}\n---\n# {s}\n")
    if persona is not None:
        (tmp_path / "persona.md").write_text(persona)
    return tmp_path


def test_declared_skills_lists_only_dirs_with_skill_md(tmp_path):
    repo = _mkrepo(tmp_path, ["turn", "task-tracker"])
    (repo / "skills" / "not-a-skill").mkdir()
    assert declared_skills(repo) == ["task-tracker", "turn"]


def test_declared_skills_empty_when_no_skills_dir(tmp_path):
    assert declared_skills(tmp_path) == []


def test_parent_of_groups_eval_and_qa_under_existing_parent():
    names = {"idea-to-pdd", "idea-to-pdd-eval", "idea-to-pdd-qa", "reviewer"}
    assert parent_of("idea-to-pdd-eval", names) == "idea-to-pdd"
    assert parent_of("idea-to-pdd-qa", names) == "idea-to-pdd"
    assert parent_of("idea-to-pdd", names) is None
    assert parent_of("reviewer", names) is None


def test_parent_of_does_not_group_when_parent_absent():
    # `deck-judge` has no `deck` parent -- it is a real skill, not a sub-skill.
    assert parent_of("standalone-eval", {"standalone-eval"}) is None


def test_persona_info_present_and_missing(tmp_path):
    repo = _mkrepo(tmp_path, ["turn"], persona="# Eva\nsells things\n")
    info = persona_info(repo)
    assert info["present"] is True and info["bytes"] > 0
    # echo has 23 skills and NO persona.md -- that is a fact, not an error
    bare = _mkrepo(tmp_path / "bare", ["turn"])
    assert persona_info(bare) == {"present": False, "path": None, "bytes": 0}


def test_skill_git_facts_reads_add_and_touch(tmp_path):
    repo = _mkrepo(tmp_path, ["turn"])
    run = lambda *a, **k: subprocess.run(*a, **k, cwd=repo, capture_output=True, text=True)
    run(["git", "init", "-q"])
    run(["git", "config", "user.email", "t@t.t"])
    run(["git", "config", "user.name", "t"])
    run(["git", "add", "-A"])
    run(["git", "commit", "-q", "-m", "add turn",
         "--date", "2026-07-01T09:00:00Z"], )
    facts = skill_git_facts(repo, "turn", NOW)
    assert facts["commits"] == 1
    assert facts["age_days"] is not None and facts["age_days"] > 13
    assert facts["added_at"].startswith("2026-07-01")


def test_skill_git_facts_ungit_repo_is_none_not_crash(tmp_path):
    repo = _mkrepo(tmp_path, ["turn"])
    facts = skill_git_facts(repo, "turn", NOW)
    assert facts == {"added_at": None, "age_days": None,
                     "last_touched_days": None, "commits": 0}


def test_skill_git_facts_follows_rename_to_original_creation_date(tmp_path):
    """FINDING 1: a `git mv` must not reset added_at to the rename date, and the
    pre-rename history must still be counted in `commits`."""
    repo = _mkrepo(tmp_path, ["oldname"])
    run = lambda *a, **k: subprocess.run(*a, **k, cwd=repo, capture_output=True, text=True)
    run(["git", "init", "-q"])
    run(["git", "config", "user.email", "t@t.t"])
    run(["git", "config", "user.name", "t"])
    run(["git", "add", "-A"])
    run(["git", "commit", "-q", "-m", "add oldname",
         "--date", "2026-01-01T09:00:00Z"])

    run(["git", "mv", "skills/oldname", "skills/newname"])
    run(["git", "commit", "-q", "-m", "rename oldname to newname",
         "--date", "2026-07-10T09:00:00Z"])

    (repo / "skills" / "newname" / "SKILL.md").write_text("---\nname: newname\n---\n# edited\n")
    run(["git", "add", "-A"])
    run(["git", "commit", "-q", "-m", "edit after rename",
         "--date", "2026-07-12T09:00:00Z"])

    facts = skill_git_facts(repo, "newname", NOW)
    assert facts["added_at"].startswith("2026-01-01")
    assert facts["commits"] == 3
    # post-rename-only history would be 2 commits (rename + edit) -- the real
    # count must include the pre-rename "add" commit too.
    assert facts["commits"] > 2


def test_skill_git_facts_deleted_then_readded_keeps_original_creation_date(tmp_path):
    """FINDING 2: a deleted-then-re-added skill must report its ORIGINAL creation
    date (overstating age is the safe direction -- it surfaces the skill for a
    human to judge rather than silently under-crediting its opportunity)."""
    repo = _mkrepo(tmp_path, ["x"])
    run = lambda *a, **k: subprocess.run(*a, **k, cwd=repo, capture_output=True, text=True)
    run(["git", "init", "-q"])
    run(["git", "config", "user.email", "t@t.t"])
    run(["git", "config", "user.name", "t"])
    run(["git", "add", "-A"])
    run(["git", "commit", "-q", "-m", "add x",
         "--date", "2026-01-01T09:00:00Z"])

    run(["git", "rm", "-q", "skills/x/SKILL.md"])
    run(["git", "commit", "-q", "-m", "remove x",
         "--date", "2026-03-01T09:00:00Z"])

    (repo / "skills" / "x").mkdir(parents=True, exist_ok=True)
    (repo / "skills" / "x" / "SKILL.md").write_text("---\nname: x\n---\n# x again\n")
    run(["git", "add", "-A"])
    run(["git", "commit", "-q", "-m", "re-add x",
         "--date", "2026-05-01T09:00:00Z"])

    facts = skill_git_facts(repo, "x", NOW)
    assert facts["added_at"].startswith("2026-01-01")
    assert facts["commits"] >= 1


# --- Task 4: Bucket classification ------------------------------------------

BURSTS = [
    {"id": 1, "start": "2026-07-01", "end": "2026-07-02", "active_days": 2, "sessions": 2},
    {"id": 2, "start": "2026-07-09", "end": "2026-07-10", "active_days": 2, "sessions": 2},
    {"id": 3, "start": "2026-07-13", "end": "2026-07-15", "active_days": 3, "sessions": 3},
]


def test_burst_of_maps_timestamp_into_its_burst():
    assert burst_of(datetime(2026, 7, 9, 11, tzinfo=timezone.utc), BURSTS) == 2
    assert burst_of(datetime(2026, 7, 14, 11, tzinfo=timezone.utc), BURSTS) == 3
    assert burst_of(datetime(2026, 7, 5, 11, tzinfo=timezone.utc), BURSTS) is None
    assert burst_of(None, BURSTS) is None


def test_classify_sub_skill_wins_first():
    assert classify(parent="idea-to-pdd", used_bursts=[], opportunity_bursts=[1, 2, 3],
                    corpus_adequate=True) == "sub_skill"


def test_classify_no_opportunity_below_min_bursts():
    # A trough is not a finding: too few bursts of opportunity -> suppressed.
    assert classify(parent=None, used_bursts=[], opportunity_bursts=[3],
                    corpus_adequate=True, min_bursts=2) == "no_opportunity"


def test_classify_never_live_for_five_day_old_skill_that_sat_out_two_bursts():
    """The regression that motivated the burst model.

    eva's agent-turn-review is 5 days old -- a wall-clock age gate would suppress
    it as 'too new'. But it sat out bursts 2 and 3 (~650 sessions) without firing.
    Burst-counting judges it; that is the whole point.
    """
    assert classify(parent=None, used_bursts=[], opportunity_bursts=[2, 3],
                    corpus_adequate=True, min_bursts=2) == "never_live"


def test_classify_live_when_fired_in_latest_opportunity_burst():
    assert classify(parent=None, used_bursts=[1, 3], opportunity_bursts=[1, 2, 3],
                    corpus_adequate=True) == "live"


def test_classify_decayed_when_fired_earlier_then_stopped():
    # The headline bucket: burst of usage, then it stops sticking.
    assert classify(parent=None, used_bursts=[1], opportunity_bursts=[1, 2, 3],
                    corpus_adequate=True, decay_bursts=1) == "decayed"


def test_classify_insufficient_evidence_on_thin_corpus():
    # Absence of evidence is not evidence of absence.
    assert classify(parent=None, used_bursts=[], opportunity_bursts=[1, 2, 3],
                    corpus_adequate=False) == "insufficient_evidence"


def test_classify_live_survives_thin_corpus():
    # A positive sighting is valid on ANY corpus size -- only negatives degrade.
    assert classify(parent=None, used_bursts=[3], opportunity_bursts=[1, 2, 3],
                    corpus_adequate=False) == "live"


# --- FINDING 1: positive evidence must short-circuit ALL negative gates -----

def test_classify_live_when_built_and_used_in_same_burst():
    # A skill built and used within the same burst of activity: used_bursts=[3]
    # is proof it fired, even though opportunity_bursts=[3] is below min_bursts.
    # This must NOT be suppressed as no_opportunity.
    assert classify(parent=None, used_bursts=[3], opportunity_bursts=[3],
                    corpus_adequate=True, min_bursts=2) == "live"


def test_classify_live_when_fired_despite_thin_opportunity_and_thin_corpus():
    # Positive evidence short-circuits BOTH negative gates at once: thin
    # opportunity-burst count AND thin corpus must not suppress a real firing.
    assert classify(parent=None, used_bursts=[1], opportunity_bursts=[1],
                    corpus_adequate=False) == "live"


# --- FINDING 2: decay_bursts edge cases --------------------------------------

def test_classify_decay_bursts_zero_means_nothing_is_recent():
    # decay_bursts=0 -> an empty recent-window, so a skill that fired earlier
    # is decayed, never live. Guards against "simplifying" the
    # `if decay_bursts else set()` guard to a bare slice (`[-0:]` returns the
    # WHOLE list, which would wrongly make this `live`).
    result = classify(parent=None, used_bursts=[1], opportunity_bursts=[1, 2, 3],
                      corpus_adequate=True, decay_bursts=0)
    assert result == "decayed"
    assert result != "live"


def test_classify_decay_bursts_larger_than_opportunity_bursts_covers_whole_list():
    # decay_bursts=5 > len(opportunity_bursts)=2 -> the whole list is the
    # recent window, so firing in burst 1 counts as live.
    assert classify(parent=None, used_bursts=[1], opportunity_bursts=[1, 2],
                    corpus_adequate=True, decay_bursts=5) == "live"
