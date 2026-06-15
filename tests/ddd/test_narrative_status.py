"""Regression tests for `narrative status` and the shared _review_id_from_url.

`scripts.ddd.narrative._cmd_status` calls `_review_id_from_url(...)` but never
imported it — a latent NameError. These tests pin the helper's new home
(scripts.ddd.review) and assert that `_cmd_status` on a nonexistent run does
NOT raise NameError.
"""
from __future__ import annotations

import pytest

from scripts.ddd.review import _review_id_from_url


def test_review_id_from_url_extracts_uuid():
    url = "https://x/review/3cc7f6f1-f4d7-4fcc-b136-6d44fee3c287"
    assert _review_id_from_url(url) == "3cc7f6f1-f4d7-4fcc-b136-6d44fee3c287"


def test_review_id_from_url_none():
    assert _review_id_from_url(None) is None


def test_narrative_module_imports():
    import scripts.ddd.narrative  # noqa: F401


def test_cmd_status_nonexistent_run_no_nameerror(monkeypatch):
    """_cmd_status on a run that does not exist must not raise NameError.

    It is allowed to raise FileNotFoundError or sys.exit / print a not-found
    status — we only assert the NameError (from the un-imported helper) is gone.
    """
    import scripts.ddd.narrative as narrative

    # Avoid any real network: stub the canopy-web narrative-existence probe.
    import scripts.ddd.review as rv
    monkeypatch.setattr(rv, "narrative_version_exists", lambda *a, **k: False)

    try:
        narrative._cmd_status("does-not-exist-2026-01-01-001")
    except NameError as exc:
        pytest.fail(f"_cmd_status raised NameError: {exc}")
    except SystemExit:
        # Expected: _cmd_status calls sys.exit(0/1) at the end.
        pass
