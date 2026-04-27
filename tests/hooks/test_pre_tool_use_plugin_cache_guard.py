"""Tests for hooks/pre_tool_use_plugin_cache_guard.py.

The guard must:
  - block mutating Bash commands targeting ~/.claude/plugins/cache or
    ~/.claude/plugins/installed_plugins.json,
  - block Edit/Write on paths inside that cache,
  - allow benign reads (ls, cat),
  - honour CANOPY_ALLOW_CACHE_PATCH=1 as an override.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

HOOK_PATH = Path(__file__).resolve().parents[2] / "hooks" / "pre_tool_use_plugin_cache_guard.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location(
        "pre_tool_use_plugin_cache_guard", HOOK_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def hook():
    return _load_hook()


# ---------------------------------------------------------------------------
# evaluate(): pure-logic tests (no stdin/stdout, no sys.exit)
# ---------------------------------------------------------------------------


def _bash_payload(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _edit_payload(file_path: str, tool_name: str = "Edit") -> dict:
    return {"tool_name": tool_name, "tool_input": {"file_path": file_path}}


def test_blocks_rsync_into_cache(hook, monkeypatch):
    monkeypatch.delenv("CANOPY_ALLOW_CACHE_PATCH", raising=False)
    action, detail = hook.evaluate(
        _bash_payload("rsync -a foo/ ~/.claude/plugins/cache/ace/ace/0.1.9/")
    )
    assert action == "block"
    assert detail and "ace" in detail


def test_blocks_cp_into_cache(hook, monkeypatch):
    monkeypatch.delenv("CANOPY_ALLOW_CACHE_PATCH", raising=False)
    action, detail = hook.evaluate(
        _bash_payload("cp file.ts ~/.claude/plugins/cache/ace/ace/0.1.9/foo.ts")
    )
    assert action == "block"
    assert detail and "cache" in detail


def test_blocks_mv_into_cache(hook, monkeypatch):
    monkeypatch.delenv("CANOPY_ALLOW_CACHE_PATCH", raising=False)
    action, _ = hook.evaluate(
        _bash_payload("mv build/dist.js ~/.claude/plugins/cache/canopy/canopy/0.2.38/foo.js")
    )
    assert action == "block"


def test_blocks_redirect_into_installed_plugins(hook, monkeypatch):
    monkeypatch.delenv("CANOPY_ALLOW_CACHE_PATCH", raising=False)
    action, _ = hook.evaluate(
        _bash_payload("echo '{}' > ~/.claude/plugins/installed_plugins.json")
    )
    assert action == "block"


def test_blocks_append_redirect_into_cache(hook, monkeypatch):
    monkeypatch.delenv("CANOPY_ALLOW_CACHE_PATCH", raising=False)
    action, _ = hook.evaluate(
        _bash_payload("echo hi >> ~/.claude/plugins/cache/ace/ace/0.1.9/foo")
    )
    assert action == "block"


def test_blocks_tee_into_cache(hook, monkeypatch):
    monkeypatch.delenv("CANOPY_ALLOW_CACHE_PATCH", raising=False)
    action, _ = hook.evaluate(
        _bash_payload(
            "echo '{}' | tee ~/.claude/plugins/installed_plugins.json"
        )
    )
    assert action == "block"


def test_blocks_sed_in_place_inside_cache(hook, monkeypatch):
    monkeypatch.delenv("CANOPY_ALLOW_CACHE_PATCH", raising=False)
    action, _ = hook.evaluate(
        _bash_payload("sed -i 's/foo/bar/' ~/.claude/plugins/cache/ace/ace/0.1.9/file.ts")
    )
    assert action == "block"


def test_blocks_rm_inside_cache(hook, monkeypatch):
    monkeypatch.delenv("CANOPY_ALLOW_CACHE_PATCH", raising=False)
    action, _ = hook.evaluate(
        _bash_payload("rm -rf ~/.claude/plugins/cache/ace/ace/0.1.9/foo")
    )
    assert action == "block"


def test_blocks_edit_on_cache_path(hook, monkeypatch):
    monkeypatch.delenv("CANOPY_ALLOW_CACHE_PATCH", raising=False)
    home = os.path.expanduser("~")
    action, detail = hook.evaluate(
        _edit_payload(
            f"{home}/.claude/plugins/cache/ace/ace/0.1.9/src/rest-token.ts",
            tool_name="Edit",
        )
    )
    assert action == "block"
    assert detail and "Edit" in detail


def test_blocks_write_on_installed_plugins(hook, monkeypatch):
    monkeypatch.delenv("CANOPY_ALLOW_CACHE_PATCH", raising=False)
    home = os.path.expanduser("~")
    action, _ = hook.evaluate(
        _edit_payload(
            f"{home}/.claude/plugins/installed_plugins.json", tool_name="Write"
        )
    )
    assert action == "block"


def test_blocks_multiedit_on_cache_path(hook, monkeypatch):
    monkeypatch.delenv("CANOPY_ALLOW_CACHE_PATCH", raising=False)
    action, _ = hook.evaluate(
        _edit_payload(
            "~/.claude/plugins/cache/ace/ace/0.1.9/x.ts", tool_name="MultiEdit"
        )
    )
    assert action == "block"


# ---------------------------------------------------------------------------
# Allow paths
# ---------------------------------------------------------------------------


def test_allows_ls_of_cache(hook, monkeypatch):
    monkeypatch.delenv("CANOPY_ALLOW_CACHE_PATCH", raising=False)
    action, _ = hook.evaluate(_bash_payload("ls ~/.claude/plugins/cache/"))
    assert action == "allow"


def test_allows_cat_of_installed_plugins(hook, monkeypatch):
    monkeypatch.delenv("CANOPY_ALLOW_CACHE_PATCH", raising=False)
    action, _ = hook.evaluate(
        _bash_payload("cat ~/.claude/plugins/installed_plugins.json")
    )
    assert action == "allow"


def test_allows_unrelated_bash(hook, monkeypatch):
    monkeypatch.delenv("CANOPY_ALLOW_CACHE_PATCH", raising=False)
    action, _ = hook.evaluate(_bash_payload("git status"))
    assert action == "allow"


def test_allows_cp_to_normal_path(hook, monkeypatch):
    monkeypatch.delenv("CANOPY_ALLOW_CACHE_PATCH", raising=False)
    action, _ = hook.evaluate(_bash_payload("cp foo.ts /tmp/bar.ts"))
    assert action == "allow"


def test_allows_edit_outside_cache(hook, monkeypatch):
    monkeypatch.delenv("CANOPY_ALLOW_CACHE_PATCH", raising=False)
    action, _ = hook.evaluate(_edit_payload("/tmp/foo.py"))
    assert action == "allow"


def test_allows_non_guarded_tool(hook, monkeypatch):
    monkeypatch.delenv("CANOPY_ALLOW_CACHE_PATCH", raising=False)
    # Read isn't in the guarded set even if file_path looks suspicious.
    action, _ = hook.evaluate(
        {
            "tool_name": "Read",
            "tool_input": {
                "file_path": "~/.claude/plugins/cache/ace/ace/0.1.9/foo.ts"
            },
        }
    )
    assert action == "allow"


# ---------------------------------------------------------------------------
# Override behaviour
# ---------------------------------------------------------------------------


def test_override_env_allows_with_warning(hook, monkeypatch):
    monkeypatch.setenv("CANOPY_ALLOW_CACHE_PATCH", "1")
    action, detail = hook.evaluate(
        _bash_payload("rsync -a foo/ ~/.claude/plugins/cache/ace/ace/0.1.9/")
    )
    assert action == "override"
    assert detail


def test_override_env_zero_does_not_allow(hook, monkeypatch):
    monkeypatch.setenv("CANOPY_ALLOW_CACHE_PATCH", "0")
    action, _ = hook.evaluate(
        _bash_payload("rsync -a foo/ ~/.claude/plugins/cache/ace/ace/0.1.9/")
    )
    assert action == "block"


# ---------------------------------------------------------------------------
# end-to-end main(): smoke test the JSON contract
# ---------------------------------------------------------------------------


def _run_main(hook_module, hook_data: dict, env: dict | None = None):
    """Run main() with mocked stdin/stdout and capture results."""
    stdin = io.StringIO(json.dumps(hook_data))
    stdout = io.StringIO()
    stderr = io.StringIO()
    env = env or {}
    with (
        mock.patch.object(sys, "stdin", stdin),
        mock.patch.object(sys, "stdout", stdout),
        mock.patch.object(sys, "stderr", stderr),
        mock.patch.dict(os.environ, env, clear=False),
    ):
        try:
            hook_module.main()
        except SystemExit as e:
            return stdout.getvalue(), stderr.getvalue(), e.code
    return stdout.getvalue(), stderr.getvalue(), None


def test_main_blocks_with_deny_decision(hook, monkeypatch):
    monkeypatch.delenv("CANOPY_ALLOW_CACHE_PATCH", raising=False)
    out, _err, code = _run_main(
        hook,
        _bash_payload("cp x ~/.claude/plugins/cache/ace/ace/0.1.9/y"),
    )
    payload = json.loads(out)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "BLOCKED" in payload["hookSpecificOutput"]["permissionDecisionReason"]
    assert code == 0


def test_main_allows_silently(hook, monkeypatch):
    monkeypatch.delenv("CANOPY_ALLOW_CACHE_PATCH", raising=False)
    out, _err, code = _run_main(hook, _bash_payload("ls /tmp"))
    payload = json.loads(out)
    assert payload == {"continue": True}
    assert code == 0


def test_main_override_warns_on_stderr_and_allows(hook, monkeypatch):
    monkeypatch.setenv("CANOPY_ALLOW_CACHE_PATCH", "1")
    out, err, code = _run_main(
        hook,
        _bash_payload("rsync -a foo/ ~/.claude/plugins/cache/ace/ace/0.1.9/"),
        env={"CANOPY_ALLOW_CACHE_PATCH": "1"},
    )
    payload = json.loads(out)
    assert payload == {"continue": True}
    assert "WARNING" in err
    assert code == 0


def test_main_handles_garbage_stdin(hook):
    stdin = io.StringIO("not json{{{")
    stdout = io.StringIO()
    with (
        mock.patch.object(sys, "stdin", stdin),
        mock.patch.object(sys, "stdout", stdout),
    ):
        with pytest.raises(SystemExit) as exc:
            hook.main()
    assert exc.value.code == 0
    payload = json.loads(stdout.getvalue())
    assert payload == {"continue": True}
