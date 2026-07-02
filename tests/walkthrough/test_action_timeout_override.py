"""Per-action ``timeout_ms`` override (slow server-side navigating clicks).

Playwright's ``locator.click`` waits for scheduled navigations inside the same
timeout, so a must_succeed publish/submit click whose POST mints records
before redirecting can blow the global 6s interaction timeout on a healthy
render. ``timeout_ms`` on the action loosens it for that one action only.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.narrative.models import Scene  # noqa: E402
from scripts.walkthrough._lib.config import RecorderConfig  # noqa: E402
from scripts.walkthrough._lib.recorder import _config_with_action_timeout  # noqa: E402

_BASE = dict(
    persona="lead", title="Publish the call", show="Lead publishes.",
    concept_claim="The call goes live on publish.", provenance="publish-call",
)


def test_schema_accepts_timeout_ms_on_click():
    s = Scene.model_validate({
        **_BASE,
        "actions": [
            {"kind": "click", "target": "css:button[type=submit]",
             "must_succeed": True, "timeout_ms": 30000},
        ],
    })
    assert s.actions[0].timeout_ms == 30000


def test_schema_timeout_ms_defaults_none():
    s = Scene.model_validate({
        **_BASE,
        "actions": [{"kind": "click", "target": "text:Open"}],
    })
    assert s.actions[0].timeout_ms is None


def test_override_loosens_interaction_and_goto_timeouts():
    cfg = RecorderConfig()
    out = _config_with_action_timeout(cfg, {"kind": "click", "timeout_ms": 30000})
    assert out.interaction_timeout_ms == 30000
    # goto default (60s) is already larger — max() keeps it
    assert out.goto_timeout_ms == max(cfg.goto_timeout_ms, 30000)


def test_override_never_tightens():
    cfg = RecorderConfig()
    out = _config_with_action_timeout(cfg, {"kind": "click", "timeout_ms": 1})
    assert out.interaction_timeout_ms == cfg.interaction_timeout_ms
    assert out.goto_timeout_ms == cfg.goto_timeout_ms


def test_no_override_returns_same_config():
    cfg = RecorderConfig()
    assert _config_with_action_timeout(cfg, {"kind": "click"}) is cfg
    assert _config_with_action_timeout(cfg, {"kind": "click", "timeout_ms": None}) is cfg
    assert _config_with_action_timeout(cfg, {"kind": "click", "timeout_ms": "bogus"}) is cfg
