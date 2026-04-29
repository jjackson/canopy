"""Tests for the autonomous.yaml validator (spec §2 + Phase 0)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SCRIPT = (
    Path(__file__).parent.parent.parent
    / "plugins"
    / "canopy"
    / "skills"
    / "product-management"
    / "scripts"
    / "validate_autonomous_config.py"
)

VALID = {
    "email": {
        "to": "user@example.com",
        "from": "bot@example.com",
        "subject_prefix": "[proj]",
        "sender_skill": "ace:email-communicator",
    },
    "shipping": {
        "branch_prefix": "proj/auto/",
        "pr_label": "autonomous",
        "merge": "squash",
        "deploy_command": "gh workflow run deploy.yml",
        "deploy_workflow": "deploy.yml",
        "post_deploy_health": ["https://example.com/health"],
    },
    "testing": {
        "unit": "pytest -q",
        "lint": "ruff check .",
        "types": "tsc -b",
        "dogfood": {
            "base_url": "http://localhost:8000",
            "start_command": "docker compose up -d",
            "wait_for": "http://localhost:8000/health",
            "headless_browser_skill": "gstack",
        },
    },
    "guardrails": {
        "one_pr_in_flight": True,
        "diff_size_limit_lines": 1500,
        "max_fix_forward_attempts": 3,
    },
    "theme_detection": {
        "lens_rotation": ["user-value", "tech-debt"],
    },
}


def _run(cfg_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(cfg_path)],
        capture_output=True,
        text=True,
        check=False,
    )


def _write(tmp_path: Path, cfg: dict) -> Path:
    p = tmp_path / "autonomous.yaml"
    p.write_text(yaml.safe_dump(cfg))
    return p


def test_valid_config_passes(tmp_path: Path) -> None:
    p = _write(tmp_path, VALID)
    result = _run(p)
    assert result.returncode == 0, result.stderr
    assert "ready" in result.stdout.lower()


def test_missing_file_fails(tmp_path: Path) -> None:
    result = _run(tmp_path / "nope.yaml")
    assert result.returncode == 1
    assert "not found" in result.stderr.lower() or "no such" in result.stderr.lower()


def test_missing_email_to_fails(tmp_path: Path) -> None:
    cfg = {**VALID, "email": {**VALID["email"]}}
    del cfg["email"]["to"]
    p = _write(tmp_path, cfg)
    result = _run(p)
    assert result.returncode == 1
    assert "email.to" in result.stderr


def test_bad_merge_value_fails(tmp_path: Path) -> None:
    cfg = {**VALID, "shipping": {**VALID["shipping"], "merge": "bogus"}}
    p = _write(tmp_path, cfg)
    result = _run(p)
    assert result.returncode == 1
    assert "shipping.merge" in result.stderr


def test_negative_diff_limit_fails(tmp_path: Path) -> None:
    cfg = {
        **VALID,
        "guardrails": {**VALID["guardrails"], "diff_size_limit_lines": -1},
    }
    p = _write(tmp_path, cfg)
    result = _run(p)
    assert result.returncode == 1
    assert "diff_size_limit_lines" in result.stderr


def test_empty_lens_rotation_fails(tmp_path: Path) -> None:
    cfg = {**VALID, "theme_detection": {"lens_rotation": []}}
    p = _write(tmp_path, cfg)
    result = _run(p)
    assert result.returncode == 1
    assert "lens_rotation" in result.stderr


def test_missing_dogfood_block_fails(tmp_path: Path) -> None:
    cfg = {**VALID, "testing": {k: v for k, v in VALID["testing"].items() if k != "dogfood"}}
    p = _write(tmp_path, cfg)
    result = _run(p)
    assert result.returncode == 1
    assert "dogfood" in result.stderr


def test_post_deploy_health_must_be_nonempty_list(tmp_path: Path) -> None:
    cfg = {
        **VALID,
        "shipping": {**VALID["shipping"], "post_deploy_health": []},
    }
    p = _write(tmp_path, cfg)
    result = _run(p)
    assert result.returncode == 1
    assert "post_deploy_health" in result.stderr


def test_optional_prepare_string_passes(tmp_path: Path) -> None:
    cfg = {
        **VALID,
        "testing": {**VALID["testing"], "prepare": "uv sync && (cd frontend && npm install)"},
    }
    p = _write(tmp_path, cfg)
    result = _run(p)
    assert result.returncode == 0, result.stderr


def test_prepare_empty_string_fails(tmp_path: Path) -> None:
    cfg = {**VALID, "testing": {**VALID["testing"], "prepare": ""}}
    p = _write(tmp_path, cfg)
    result = _run(p)
    assert result.returncode == 1
    assert "prepare" in result.stderr


def test_prepare_non_string_fails(tmp_path: Path) -> None:
    cfg = {**VALID, "testing": {**VALID["testing"], "prepare": ["uv", "sync"]}}
    p = _write(tmp_path, cfg)
    result = _run(p)
    assert result.returncode == 1
    assert "prepare" in result.stderr


def test_malformed_yaml_fails(tmp_path: Path) -> None:
    p = tmp_path / "autonomous.yaml"
    p.write_text("email: : :\n")
    result = _run(p)
    assert result.returncode == 1
    assert "yaml" in result.stderr.lower() or "parse" in result.stderr.lower()
