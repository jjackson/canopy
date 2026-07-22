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
    # A turn (it loaded skills/turn) that does none of the expected steps -> all gaps.
    _write_transcript(t, str(tmp_path), [
        ("Read", {"file_path": "/repo/skills/turn/SKILL.md"}, "Hal's turn loop..."),
        ("Read", {"file_path": "/x"}, "ok"),
    ])
    gaps = set(friction_signals(t)["checklist_gaps"])
    assert {"preflight", "self-review", "skill-self-check", "workspace-refresh"} <= gaps


def test_non_turn_session_not_graded_against_turn_steps(tmp_path):
    # An `architect ddd` / harvest session is NOT a turn — grading it against the turn-step
    # checklist flagged every one as a 4-gap "failure storm" (hal's 2026-07 review). No turn
    # marker anywhere -> no checklist gaps.
    t = tmp_path / "architect.jsonl"
    _write_transcript(t, str(tmp_path), [
        ("Bash", {"command": "canopy harvest map ddd --full"}, "331 sessions, whole-corpus"),
        ("Write", {"file_path": "/repo/ledgers/ddd.md"}, "File created successfully"),
    ])
    assert friction_signals(t)["checklist_gaps"] == []


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


def test_auth_marker_does_not_fire_on_successful_write(tmp_path):
    # hal's 2026-07 review: a SUCCESSFUL Write of a memory file named
    # `email-oauth-not-minted.md` was flagged as auth_friction because "oauth" is in the path.
    # A completed file write is never runtime friction.
    t = tmp_path / "turn.jsonl"
    _write_transcript(t, str(tmp_path), [
        ("Write", {"file_path": "/repo/memory/email-oauth-not-minted.md"},
         "File created successfully at: /repo/memory/email-oauth-not-minted.md"),
    ])
    s = friction_signals(t)
    assert s["auth_friction"] == [], "a successful write is not auth friction"
    assert s["failures"] == []


def test_skill_collision_flags_loading_another_plugins_same_named_skill(tmp_path):
    # hal's 2026-07 review: "do a turn" loaded `ace:turn` (ACE's turn loop) instead of hal's own
    # skills/turn — a silent wrong-skill load the mechanical signals were blind to.
    t = tmp_path / "turn.jsonl"
    _write_transcript(t, str(tmp_path), [
        ("Skill", {"skill": "ace:turn"}, "ACE's turn skill loaded"),
        ("Skill", {"skill": "canopy:improve"}, "improve skill loaded"),   # not owned -> fine
        ("Skill", {"skill": "architect"}, "own bare skill -> fine"),
    ])
    s = friction_signals(t, own_skills=frozenset({"turn", "architect", "self-review"}))
    cols = s["skill_collisions"]
    assert len(cols) == 1
    assert cols[0]["invoked"] == "ace:turn" and cols[0]["own_skill"] == "turn"
    assert "skill_collision" in FRICTION_TYPES


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

def test_run_review_surfaces_stdout_error_and_sane_budget(tmp_path, monkeypatch):
    # Echo's 2026-07 review: claude -p exited 1 with "Error: Exceeded USD budget (0.5)"
    # on STDOUT (stderr empty), so the report said 'claude -p failed: ' — undiagnosable.
    # Pin both fixes: (a) stdout errors surface, (b) the default budget clears $0.50,
    # which a real 7-turn corpus empirically exceeds.
    import subprocess as sp
    from orchestrator import agent_review as ar

    repo = tmp_path / "repositories" / "echo"
    (repo / "skills").mkdir(parents=True)
    projects = tmp_path / "projects"
    d = projects / "-Users-x-emdash-repositories-echo"
    d.mkdir(parents=True)
    _write_transcript(d / "a.jsonl", str(repo), [("Read", {"file_path": "/x"}, "ok")])

    seen_cmds = []

    def fake_run(cmd, **kwargs):
        seen_cmds.append(cmd)
        return sp.CompletedProcess(
            cmd, returncode=1, stdout="Error: Exceeded USD budget (0.5)", stderr="")

    monkeypatch.setattr(ar.subprocess, "run", fake_run)
    result = ar.run_review(str(repo), projects_dir=projects)

    assert "Exceeded USD budget" in result["error"]          # (a) stdout not swallowed
    budget = float(seen_cmds[0][seen_cmds[0].index("--max-budget-usd") + 1])
    assert budget > 0.5                                       # (b) default clears the observed cost


# --- Source-verification gate (the recurring "re-surfaced an already-fixed finding" bug) ---

def test_source_gate_drops_shipped_keeps_live_and_annotates(tmp_path):
    """The gate drops a finding the LLM verdicts `shipped` and keeps `live`/`unverifiable`
    ones, annotating each with its verdict. git calls no-op in a non-repo tmp dir."""
    from orchestrator.agent_review import verify_findings_against_source

    findings = [
        {"title": "add reply-all default", "target": "bin/echo_email.py",
         "recommendation": "flip the default"},
        {"title": "label denominators", "target": "skills/org-research/SKILL.md",
         "recommendation": "inline the denominator"},
        {"title": "mystery", "target": "skills/x/SKILL.md", "recommendation": "do x"},
    ]

    def fake_verdict(_prompt):
        return [
            {"index": 0, "verdict": "shipped", "evidence": "already reads as:eva@ in main"},
            {"index": 1, "verdict": "live", "evidence": "still bare percentages"},
            # index 2 omitted → defaults to unverifiable → KEPT
        ]

    kept, dropped, error = verify_findings_against_source(tmp_path, findings, verdict_fn=fake_verdict)
    assert error is None
    assert [f["title"] for f in dropped] == ["add reply-all default"]
    assert dropped[0]["verification"]["verdict"] == "shipped"
    assert [f["title"] for f in kept] == ["label denominators", "mystery"]
    assert kept[0]["verification"]["verdict"] == "live"
    assert kept[1]["verification"]["verdict"] == "unverifiable"   # missing verdict → kept


def test_source_gate_fails_open_when_verification_unavailable(tmp_path):
    """If the verdict pass returns nothing (LLM error/parse miss), NOTHING is dropped —
    the gate never silently eats a finding it couldn't check."""
    from orchestrator.agent_review import verify_findings_against_source

    findings = [{"title": "z", "target": "a/b.py", "recommendation": "do z"}]
    kept, dropped, error = verify_findings_against_source(tmp_path, findings, verdict_fn=lambda _p: None)
    assert dropped == []
    assert kept == findings   # unchanged, not annotated — a true no-op on failure
    assert error                # ...and the reason is surfaced, never a silent pass


def test_run_review_applies_source_gate(tmp_path, monkeypatch):
    """run_review wires the gate: a synthesized finding the gate marks shipped lands in
    dropped_findings, not findings — with the gate ON by default."""
    import subprocess as sp
    from orchestrator import agent_review as ar

    repo = tmp_path / "repositories" / "echo"
    (repo / "skills").mkdir(parents=True)
    projects = tmp_path / "projects"
    d = projects / "-Users-x-emdash-repositories-echo"
    d.mkdir(parents=True)
    _write_transcript(d / "a.jsonl", str(repo), [("Read", {"file_path": "/x"}, "ok")])

    def fake_run(cmd, **kwargs):   # the synthesis claude -p call
        return sp.CompletedProcess(
            cmd, returncode=0,
            stdout="- title: already fixed thing\n  friction_type: tool_failure\n", stderr="")

    monkeypatch.setattr(ar.subprocess, "run", fake_run)
    # Stub the gate's verdict so no real git/LLM runs; mark the only finding shipped.
    monkeypatch.setattr(
        ar, "verify_findings_against_source",
        lambda repo, findings, **kw: ([], [{**findings[0], "verification": {"verdict": "shipped"}}], None),
    )

    result = ar.run_review(str(repo), projects_dir=projects)
    assert result["findings"] == []
    assert len(result["dropped_findings"]) == 1
    assert result["dropped_findings"][0]["title"] == "already fixed thing"


def test_run_review_surfaces_verification_error(tmp_path, monkeypatch):
    """When the source gate can't run, run_review KEEPS the findings and records
    `verification_error` — a silent no-op gate (unverified findings looking verified)
    is the failure mode we're closing."""
    import subprocess as sp
    from orchestrator import agent_review as ar

    repo = tmp_path / "repositories" / "echo"
    (repo / "skills").mkdir(parents=True)
    projects = tmp_path / "projects"
    d = projects / "-Users-x-emdash-repositories-echo"
    d.mkdir(parents=True)
    _write_transcript(d / "a.jsonl", str(repo), [("Read", {"file_path": "/x"}, "ok")])

    def fake_run(cmd, **kwargs):
        return sp.CompletedProcess(
            cmd, returncode=0, stdout="- title: t\n  friction_type: tool_failure\n", stderr="")

    monkeypatch.setattr(ar.subprocess, "run", fake_run)
    monkeypatch.setattr(
        ar, "verify_findings_against_source",
        lambda repo, findings, **kw: (list(findings), [], "verify pass timed out after 300s"),
    )
    result = ar.run_review(str(repo), projects_dir=projects)
    assert len(result["findings"]) == 1          # kept (fail-open)
    assert result["dropped_findings"] == []
    assert "timed out" in result["verification_error"]


def test_run_review_no_verify_skips_gate(tmp_path, monkeypatch):
    """--no-verify (verify=False) returns synthesized findings untouched — the gate never runs."""
    import subprocess as sp
    from orchestrator import agent_review as ar

    repo = tmp_path / "repositories" / "echo"
    (repo / "skills").mkdir(parents=True)
    projects = tmp_path / "projects"
    d = projects / "-Users-x-emdash-repositories-echo"
    d.mkdir(parents=True)
    _write_transcript(d / "a.jsonl", str(repo), [("Read", {"file_path": "/x"}, "ok")])

    def fake_run(cmd, **kwargs):
        return sp.CompletedProcess(
            cmd, returncode=0, stdout="- title: t\n  friction_type: tool_failure\n", stderr="")

    monkeypatch.setattr(ar.subprocess, "run", fake_run)

    def boom(*a, **k):
        raise AssertionError("gate must not run when verify=False")

    monkeypatch.setattr(ar, "verify_findings_against_source", boom)
    result = ar.run_review(str(repo), projects_dir=projects, verify=False)
    assert len(result["findings"]) == 1
    assert result["dropped_findings"] == []
