"""Tests for the find-session skill helper (plugins/canopy/skills/find-session).

The helper answers "find my OTHER active session on repo X" — so the load-
bearing behaviors are: (1) the current session is excluded, (2) candidates rank
by recency, (3) a target slug / path scopes the search precisely (canopy-web
must not catch ace-web), and (4) harness noise (system-reminders, task
notifications) is not surfaced as a human prompt.

We exercise the real CLI entry point via subprocess with a temp $HOME so the
test covers arg parsing and `$CLAUDE_CODE_SESSION_ID` exclusion end-to-end.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

NOW = time.time()

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "plugins" / "canopy" / "skills" / "find-session" / "scripts" / "find_session.py"
)


def _write_session(home, project_key, session_id, cwd, branch, prompts, mtime):
    """Write a minimal transcript jsonl and stamp its mtime."""
    proj = home / ".claude" / "projects" / project_key
    proj.mkdir(parents=True, exist_ok=True)
    path = proj / f"{session_id}.jsonl"
    lines = []
    for p in prompts:
        lines.append(json.dumps({
            "type": "user",
            "cwd": cwd,
            "gitBranch": branch,
            "isSidechain": False,
            "message": {"content": p},
        }))
    path.write_text("\n".join(lines) + "\n")
    # `mtime` is a small relative-ordering knob; map it into the recent past
    # (larger == more recent) so every fixture lands inside the 24h window.
    stamp = NOW - (10000 - mtime)
    os.utime(path, (stamp, stamp))
    return path


def _run(home, *args, session_id="current-session"):
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["CLAUDE_CODE_SESSION_ID"] = session_id
    out = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_excludes_current_session(tmp_path):
    _write_session(tmp_path, "-Users-x-repo-foo", "current-session",
                   "/Users/x/repo/foo", "main", ["this is the current session"], 2000)
    _write_session(tmp_path, "-Users-x-repo-foo", "sibling",
                   "/Users/x/repo/foo", "feat/x", ["sibling session work"], 1000)
    out = _run(tmp_path)
    assert "sibling session work" in out
    assert "this is the current session" not in out
    assert "current-session" not in out


def test_ranks_by_recency(tmp_path):
    _write_session(tmp_path, "-a-foo", "older", "/a/foo", "b1", ["older prompt"], 1000)
    _write_session(tmp_path, "-a-foo", "newer", "/a/foo", "b2", ["newer prompt"], 5000)
    out = _run(tmp_path, "--top", "1")
    # Newest is the fully-digested top candidate.
    assert out.index("newer prompt") < (out.index("older prompt") if "older prompt" in out else len(out))
    assert "newer prompt" in out


def test_slug_target_scopes_precisely(tmp_path):
    # canopy-web target must not catch ace-web (the classic substring trap).
    _write_session(tmp_path, "-Users-x-worktrees-canopy-web-feat", "cw",
                   "/Users/x/worktrees/canopy-web/feat", "main", ["canopy web work"], 3000)
    _write_session(tmp_path, "-Users-x-worktrees-ace-web-feat", "aw",
                   "/Users/x/worktrees/ace-web/feat", "main", ["ace web work"], 4000)
    out = _run(tmp_path, "canopy-web")
    assert "canopy web work" in out
    assert "ace web work" not in out


def test_path_target_does_not_leaf_match_wrong_repo(tmp_path):
    _write_session(tmp_path, "-Users-x-worktrees-canopy-web-feat", "cw",
                   "/Users/x/worktrees/canopy-web/feat", "main", ["canopy web work"], 3000)
    _write_session(tmp_path, "-Users-x-worktrees-ace-web-feat", "aw",
                   "/Users/x/worktrees/ace-web/feat", "main", ["ace web work"], 4000)
    out = _run(tmp_path, "/Users/x/worktrees/canopy-web")
    assert "canopy web work" in out
    assert "ace web work" not in out


def test_filters_harness_noise(tmp_path):
    _write_session(
        tmp_path, "-a-foo", "sib", "/a/foo", "main",
        [
            "<system-reminder>do not surface me</system-reminder>",
            "<task-notification>nor me</task-notification>",
            "Caveat: nor me either",
            "real human prompt here",
        ],
        2000,
    )
    out = _run(tmp_path)
    assert "real human prompt here" in out
    assert "do not surface me" not in out
    assert "nor me" not in out
    assert "Caveat:" not in out


def test_no_candidates_is_graceful(tmp_path):
    _write_session(tmp_path, "-a-foo", "current-session", "/a/foo", "main",
                   ["only this session exists"], 2000)
    out = _run(tmp_path)
    assert "No matching active session" in out


def test_json_output_shape(tmp_path):
    _write_session(tmp_path, "-a-foo", "sib", "/a/foo", "main", ["hello"], 2000)
    out = _run(tmp_path, "--json")
    data = json.loads(out)
    assert len(data) == 1
    assert data[0]["session_id"] == "sib"
    assert data[0]["prompts"] == ["hello"]
