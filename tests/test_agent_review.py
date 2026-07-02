"""Tests for the agent self-improvement lens (deterministic friction extraction; no LLM)."""
import json

from orchestrator.agent_review import (
    FRICTION_TYPES,
    build_review_prompt,
    find_turn_transcripts,
    friction_signals,
    parse_findings,
    resolve_agent_repo,
)
from orchestrator.agent_factory import AgentSpec, create_agent


def _write_transcript(path, cwd, calls):
    """calls: list of (tool, input_dict, result_str). Writes a minimal Claude jsonl."""
    lines = []
    for i, (tool, inp, result) in enumerate(calls):
        tid = f"t{i}"
        lines.append({
            "type": "assistant", "cwd": cwd,
            "message": {"content": [
                {"type": "tool_use", "id": tid, "name": tool, "input": inp},
            ]},
        })
        lines.append({
            "type": "user",
            "message": {"content": [
                {"type": "tool_result", "tool_use_id": tid, "content": result},
            ]},
        })
    path.write_text("\n".join(json.dumps(l) for l in lines) + "\n")


def test_friction_signals_detects_failures_blocks_retries_auth(tmp_path):
    t = tmp_path / "turn.jsonl"
    _write_transcript(t, str(tmp_path), [
        ("Bash", {"command": "gog gmail send --to a@b.c"}, "BLOCKED: use the wrapper. exit code 2"),
        ("Bash", {"command": "gog gmail search"}, "People API has not been used... 403"),
        ("Bash", {"command": "gog gmail search"}, "ok, 3 messages"),   # retry of a failed tool
        ("Read", {"file_path": "/x"}, "file contents fine"),
    ])
    s = friction_signals(t)
    assert len(s["gating_blocks"]) == 1
    assert any("403" in f["evidence"] or "API" in f["evidence"] for f in s["failures"])
    assert s["auth_friction"], "the 403/API-not-enabled line should flag auth friction"
    assert "Bash" in s["retry_loops"], "a failed tool re-tried should be a retry loop"


def test_friction_signals_flags_checklist_gaps(tmp_path):
    t = tmp_path / "turn.jsonl"
    # A turn that does none of the expected steps -> all gaps.
    _write_transcript(t, str(tmp_path), [("Read", {"file_path": "/x"}, "ok")])
    gaps = set(friction_signals(t)["checklist_gaps"])
    assert {"preflight", "self-review", "skill-self-check", "workspace-refresh"} <= gaps


def test_friction_signals_credits_steps_that_ran(tmp_path):
    t = tmp_path / "turn.jsonl"
    _write_transcript(t, str(tmp_path), [
        ("Bash", {"command": "python3 bin/echo_preflight.py"}, "ready"),
        ("Bash", {"command": "canopy agent-publish skills"}, "ok"),
    ])
    gaps = set(friction_signals(t)["checklist_gaps"])
    assert "preflight" not in gaps          # preflight marker present
    assert "workspace-refresh" not in gaps  # agent-publish marker present


def test_clean_turn_has_no_friction(tmp_path):
    t = tmp_path / "turn.jsonl"
    _write_transcript(t, str(tmp_path), [("Read", {"file_path": "/x"}, "all good here")])
    s = friction_signals(t)
    assert s["failures"] == [] and s["gating_blocks"] == [] and s["retry_loops"] == []


def test_find_turn_transcripts_matches_by_cwd(tmp_path):
    repo = tmp_path / "repositories" / "echo"
    repo.mkdir(parents=True)
    projects = tmp_path / "projects"
    # A matching project dir (name carries the slug) with a turn run inside the repo.
    d = projects / "-Users-x-emdash-repositories-echo"
    d.mkdir(parents=True)
    _write_transcript(d / "a.jsonl", str(repo), [("Read", {"file_path": "/x"}, "ok")])
    # A non-matching project dir (different repo) should be ignored.
    other = projects / "-Users-x-emdash-repositories-other"
    other.mkdir(parents=True)
    _write_transcript(other / "b.jsonl", str(tmp_path / "other"), [("Read", {}, "ok")])

    found = find_turn_transcripts(repo, hours=99999, projects_dir=projects)
    assert len(found) == 1
    assert found[0].name == "a.jsonl"


def test_resolve_agent_repo_by_path(tmp_path):
    repo = tmp_path / "echo"
    create_agent(AgentSpec(slug="echo", display_name="Echo", mandate="x."), repo)
    assert resolve_agent_repo(str(repo)) == repo


def test_build_review_prompt_and_parse_findings(tmp_path):
    repo = tmp_path / "echo"
    create_agent(AgentSpec(slug="echo", display_name="Echo", mandate="x."), repo)
    prompt = build_review_prompt(repo, [{"session_id": "s", "failures": []}])
    for ftype in FRICTION_TYPES:
        assert ftype in prompt
    # parse_findings tolerates fenced YAML and non-list junk
    yaml_out = "```yaml\n- title: Fix auth\n  friction_type: auth_friction\n  confidence: high\n```"
    parsed = parse_findings(yaml_out)
    assert parsed and parsed[0]["title"] == "Fix auth"
    assert parse_findings("not a list") == []


def test_pr_status_output_is_not_a_gating_block_or_failure(tmp_path):
    # Hal's 2026-07 review: `gh pr view` output ("mergeable: MERGEABLE/BLOCKED",
    # "blocked only on required review") was misread as gating friction / failures.
    t = tmp_path / "turn.jsonl"
    _write_transcript(t, str(tmp_path), [
        ("Bash", {"command": "gh pr view 1253"},
         "title: fix(mobile)\nmergeable: MERGEABLE/BLOCKED  +47/-5\nreview=REVIEW_REQUIRED"),
        ("AskUserQuestion", {"questions": []},
         'Your questions have been answered: "#1253 is green, blocked only on required review"'),
    ])
    s = friction_signals(t)
    assert s["gating_blocks"] == []
    assert s["failures"] == []
    assert s["retry_loops"] == []


def test_read_of_hook_source_is_not_a_gating_block(tmp_path):
    # Reading the gating hook's own source contains "permissionDecision" — a Read can't be gated.
    t = tmp_path / "turn.jsonl"
    _write_transcript(t, str(tmp_path), [
        ("Read", {"file_path": "/repo/hooks/gating_guard.py"},
         'print(json.dumps({"hookSpecificOutput": {"permissionDecision": "ask"}}))'),
    ])
    assert friction_signals(t)["gating_blocks"] == []


def test_cat_of_gating_config_is_not_a_gating_block(tmp_path):
    # `cat config/gating.json` output carries "BLOCKED:" deep in the deny message — a real hook
    # block IS the whole result, so the marker must appear at the head to count.
    t = tmp_path / "turn.jsonl"
    _write_transcript(t, str(tmp_path), [
        ("Bash", {"command": "cat config/gating.json"},
         "=== config/gating.json ===\n" + '{"_doc": "' + "policy prose " * 30 + '",\n'
         '"deny": [{"message": "BLOCKED: raw gog gmail send bypasses the wrapper."}]}'),
    ])
    assert friction_signals(t)["gating_blocks"] == []


def test_hook_ask_modal_counts_as_gating_block(tmp_path):
    t = tmp_path / "turn.jsonl"
    _write_transcript(t, str(tmp_path), [
        ("Bash", {"command": "gog gmail send --to a@b.c"},
         '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", '
         '"permissionDecisionReason": "APPROVE Hal -> gog gmail send"}}'),
    ])
    s = friction_signals(t)
    assert len(s["gating_blocks"]) == 1
    assert s["failures"] == []


def test_retry_loop_requires_similar_subject_not_just_tool_reuse(tmp_path):
    # A failed Bash call followed by UNRELATED Bash calls is not a retry loop...
    t = tmp_path / "turn.jsonl"
    _write_transcript(t, str(tmp_path), [
        ("Bash", {"command": "cat /nope/missing.json"}, "Exit code 1\ncat: not found"),
        ("Bash", {"command": "git status --short"}, "clean"),
        ("Bash", {"command": "ls -la /tmp"}, "total 0"),
    ])
    assert friction_signals(t)["retry_loops"] == []
    # ...but the same command re-run right after failing IS.
    t2 = tmp_path / "turn2.jsonl"
    _write_transcript(t2, str(tmp_path), [
        ("Bash", {"command": "cat /nope/missing.json"}, "Exit code 1\ncat: not found"),
        ("Bash", {"command": "cat /nope/missing.json || true"}, "ok"),
    ])
    assert friction_signals(t2)["retry_loops"] == ["Bash"]


def test_human_corrections_catches_safety_override_and_confusion():
    from orchestrator.agent_review import human_corrections
    entries = [
        {"type": "user", "message": {"content": "take a turn on what came in"}},
        {"type": "user", "message": {"content": "I'm lost, why are you asking me about 1) then showing 2?"}},
        {"type": "user", "message": {"content": "your submission skill should NEVER EVER submit directly without human review"}},
        {"type": "user", "message": {"content": "go ahead"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}},
    ]
    cor = human_corrections(entries)
    quotes = " ".join(c["quote"] for c in cor)
    assert "NEVER EVER submit" in quotes          # the safety override is caught
    assert "I'm lost" in quotes                    # the confusion is caught
    allkinds = {k for c in cor for k in c["kinds"]}
    assert "safety_override" in allkinds and "confusion" in allkinds and "emphasis" in allkinds
    assert "go ahead" not in quotes and "take a turn" not in quotes   # neutral msgs ignored
