"""Tests for the secret-leak scanner used by the autonomous PM gate."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).parent.parent.parent
    / "plugins"
    / "canopy"
    / "skills"
    / "product-management"
    / "scripts"
    / "secret_scan.py"
)


def _run(stdin: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def test_clean_diff_passes() -> None:
    diff = "+def hello():\n+    return 'world'\n"
    result = _run(diff)
    assert result.returncode == 0, result.stderr


def test_aws_access_key_blocks() -> None:
    diff = "+aws_key = 'AKIAIOSFODNN7EXAMPLE'\n"
    result = _run(diff)
    assert result.returncode == 1
    assert "AWS access key" in result.stderr


def test_anthropic_key_blocks() -> None:
    diff = "+ANTHROPIC_API_KEY=sk-ant-abcDEF_123-xyz\n"
    result = _run(diff)
    assert result.returncode == 1
    assert "Anthropic" in result.stderr


def test_github_token_blocks() -> None:
    diff = "+TOKEN = 'ghp_" + "A" * 36 + "'\n"
    result = _run(diff)
    assert result.returncode == 1
    assert "GitHub" in result.stderr


def test_env_value_substring_blocks(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("DB_PASSWORD=hunter2supersecret\nUNSET=\n")
    diff = "+config = {'pwd': 'hunter2supersecret'}\n"
    result = _run(diff, "--env-file", str(env))
    assert result.returncode == 1
    assert ".env value" in result.stderr


def test_env_value_empty_lines_ignored(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("UNSET=\n# comment\n\n")
    diff = "+nothing = 'fine'\n"
    result = _run(diff, "--env-file", str(env))
    assert result.returncode == 0


def test_restricted_filename_blocks() -> None:
    diff = (
        "diff --git a/secrets/gws-sa-key.json b/secrets/gws-sa-key.json\n"
        "+{\"private_key\": \"...\"}\n"
    )
    result = _run(diff)
    assert result.returncode == 1
    assert "restricted file" in result.stderr.lower()


def test_debug_leftover_in_source_blocks() -> None:
    diff = (
        "diff --git a/src/foo.py b/src/foo.py\n"
        "+def f():\n"
        "+    print('debug')\n"
    )
    result = _run(diff)
    assert result.returncode == 1
    assert "debug" in result.stderr.lower()


def test_debug_in_test_file_allowed() -> None:
    diff = (
        "diff --git a/tests/test_foo.py b/tests/test_foo.py\n"
        "+def test_x():\n"
        "+    print('ok')\n"
    )
    result = _run(diff)
    assert result.returncode == 0
