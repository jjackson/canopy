"""A mid-scene ``goto`` must NOT become the scene's start URL.

Background: ``build_scenes_from_spec`` resolves a scene's start URL from
(1) an explicit ``url:``, (2) a leading ``goto`` action, (3) the legacy
run_data slide. Before this fix, rule 2 matched the FIRST goto *anywhere*
in the actions list — so a scripted mid-scene navigation (publish → capture
the new entity id → ``goto /x/${id}/``) was hoisted to scene start and the
recorder navigated to a literal ``/x/${id}/`` (the capture that binds the
var hadn't run yet), filming a Django 404 for the whole scene.

Also pins the import-order fix: importing ``record_video`` by path must give
``_lib.orchestrator`` the REAL ``has_unresolved`` (repo root on sys.path
before the orchestrator import), not the always-False portable stub — the
stub is what let the hoisted ``${var}`` URL through the nav guard.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.walkthrough.record_video import build_scenes_from_spec  # noqa: E402

BASE = "https://labs.connect.dimagi.com"


def _scene(actions, **kw):
    return {"title": "t", **kw, "actions": actions}


def test_midscene_goto_is_not_hoisted_to_scene_url():
    """A goto after other actions leaves scene url None (stay on prev page)."""
    scenes = build_scenes_from_spec(
        {"scenes": [_scene([
            {"kind": "click", "target": "text:Generate with AI"},
            {"kind": "click", "target": "css:button[type=submit]", "must_succeed": True},
            {"kind": "capture", "var": "solicitation_id", "pattern": r"/solicitations/(\d+)/"},
            {"kind": "goto", "target": "/solicitations/${solicitation_id}/?program_id=10008"},
        ])]},
        BASE,
        run_data=None,
    )
    assert scenes[0]["url"] is None
    # ...and the mid-scene goto stays in the action list to run at its slot.
    assert any((a.get("kind") == "goto") for a in scenes[0]["actions"])


def test_leading_goto_still_defines_scene_url():
    """The legitimate rule-2 case is unchanged: actions[0] goto → scene url."""
    scenes = build_scenes_from_spec(
        {"scenes": [_scene([
            {"kind": "goto", "target": "/microplans/program/10008/"},
            {"kind": "click", "target": "text:Open"},
        ])]},
        BASE,
        run_data=None,
    )
    assert scenes[0]["url"] == f"{BASE}/microplans/program/10008/"


def test_repo_root_on_syspath_before_lib_orchestrator_import():
    """record_video.py must put the repo root on sys.path BEFORE importing
    ``_lib.orchestrator`` — otherwise the orchestrator's defensive import of
    ``scripts.narrative.substitution`` fails in by-path invocations and freezes
    the always-False ``has_unresolved`` stub (the nav guard that stops literal
    ``${var}`` URLs never fires). Pinned as a source-order assertion because a
    normal test process already has the repo root on sys.path, which would
    mask a regression."""
    src = (
        Path(__file__).resolve().parents[2]
        / "scripts" / "walkthrough" / "record_video.py"
    ).read_text()
    repo_root_insert = src.index("_REPO_ROOT = Path(__file__).resolve().parents[2]")
    orchestrator_import = src.index("from _lib.orchestrator import")
    assert repo_root_insert < orchestrator_import, (
        "repo-root sys.path insert must precede the _lib.orchestrator import "
        "in record_video.py (else _lib.orchestrator falls back to no-op "
        "${var} stubs in by-path invocations)"
    )


def test_orchestrator_stub_fallback_is_loud(capsys):
    """If the defensive import ever falls back again, it must warn on stderr —
    a silent identity resolve_string films literal ${var} URLs as 404s."""
    import importlib.util
    import subprocess
    import sys as _sys
    import tempfile

    repo_root = Path(__file__).resolve().parents[2]
    probe = (
        "import sys\n"
        # Strip repo root + cwd so scripts.narrative CANNOT import, then load
        # _lib.orchestrator the way a by-path invocation would see it.\n"
        f"sys.path = [p for p in sys.path if p not in ('', '.', {str(repo_root)!r})]\n"
        f"sys.path.insert(0, {str(repo_root / 'scripts' / 'walkthrough')!r})\n"
        "import _lib.orchestrator as o\n"
        "print('unresolved:', o.has_unresolved('/x/${y}/'))\n"
    )
    with tempfile.TemporaryDirectory() as td:
        out = subprocess.run(
            [_sys.executable, "-c", probe], capture_output=True, text=True, cwd=td
        )
    assert out.returncode == 0, out.stderr
    assert "unresolved: False" in out.stdout  # the stub is active in this probe
    assert "WARNING" in out.stderr and "scripts.narrative" in out.stderr
