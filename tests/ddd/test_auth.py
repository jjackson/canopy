"""Tests for scripts/ddd/auth.py — the shared canopy-web auth/URL helpers.

No network. scripts.ddd.auth now RE-EXPORTS the canonical resolvers from
orchestrator.canopy_web, so the on-disk fallback is patched at its real source —
``orchestrator.canopy_web.TOKEN_FILE`` — not the re-exported alias.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ddd.auth import (
    DEFAULT_API,
    TOKEN_FILE,
    resolve_base_url,
    resolve_token,
)


# ---------------------------------------------------------------------------
# resolve_base_url
# ---------------------------------------------------------------------------


def test_resolve_base_url_strips_trailing_slash():
    assert resolve_base_url("http://x/") == "http://x"


def test_resolve_base_url_explicit_wins(monkeypatch):
    monkeypatch.setenv("CANOPY_WEB_API_URL", "http://env-host/")
    assert resolve_base_url("http://explicit/") == "http://explicit"


def test_resolve_base_url_env_wins_over_default(monkeypatch):
    monkeypatch.setenv("CANOPY_WEB_API_URL", "http://env-host/")
    assert resolve_base_url(None) == "http://env-host"


def test_resolve_base_url_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("CANOPY_WEB_API_URL", raising=False)
    assert resolve_base_url(None) == DEFAULT_API


# ---------------------------------------------------------------------------
# resolve_token — precedence: explicit arg > env > TOKEN_FILE > raise
# ---------------------------------------------------------------------------


def test_resolve_token_explicit_wins(monkeypatch):
    monkeypatch.setenv("CANOPY_WEB_PAT", "env-token")
    assert resolve_token("explicit-token") == "explicit-token"


def test_resolve_token_env_wins_over_file(monkeypatch, tmp_path):
    tok = tmp_path / "token"
    tok.write_text("file-token")
    monkeypatch.setattr("orchestrator.canopy_web.TOKEN_FILE", tok)
    monkeypatch.setenv("CANOPY_WEB_PAT", "env-token")
    assert resolve_token(None) == "env-token"


def test_resolve_token_file_fallback(monkeypatch, tmp_path):
    tok = tmp_path / "token"
    tok.write_text("  file-token  \n")
    monkeypatch.setattr("orchestrator.canopy_web.TOKEN_FILE", tok)
    monkeypatch.delenv("CANOPY_WEB_PAT", raising=False)
    assert resolve_token(None) == "file-token"


def test_resolve_token_raises_when_none(monkeypatch, tmp_path):
    missing = tmp_path / "nope"
    monkeypatch.setattr("orchestrator.canopy_web.TOKEN_FILE", missing)
    monkeypatch.delenv("CANOPY_WEB_PAT", raising=False)
    with pytest.raises(RuntimeError):
        resolve_token(None)
