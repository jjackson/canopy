"""Health checks for the canopy plugin install.

Each check is a small, read-only function returning a CheckResult. They
degrade gracefully — an absent file or unreadable JSON reports ``ok=False``
with a human-readable detail rather than raising. ``run_doctor`` composes
them all and reports an overall pass/fail.

Ported from the documented checks in
``plugins/canopy/skills/canopy-doctor/SKILL.md``: hook registration, session
log, repo map, workbench token (presence + permissions), and plugin version.
Network-dependent checks (live workbench API connectivity, auth-preflight)
are intentionally left to the skill launcher so ``canopy doctor`` stays fast,
offline, and CI-gateable.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from orchestrator.paths import CANOPY_DIR


@dataclass
class CheckResult:
    """Result of a single health check."""

    name: str
    ok: bool
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


def _claude_dir(home: Path) -> Path:
    return home / ".claude"


def check_hook_registered(home: Path | None = None) -> CheckResult:
    """The PostToolUse hook must be registered in ~/.claude/settings.json."""
    home = home or Path.home()
    settings = _claude_dir(home) / "settings.json"
    name = "Hook registration"
    if not settings.exists():
        return CheckResult(name, False, f"{settings} not found — run /canopy:setup")
    try:
        data = json.loads(settings.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return CheckResult(name, False, f"could not read {settings}: {e}")

    hooks = data.get("hooks", {}).get("PostToolUse", [])
    found = any(
        "post_tool_use.py" in h.get("command", "")
        for entry in hooks
        if isinstance(entry, dict)
        for h in entry.get("hooks", [])
        if isinstance(h, dict)
    )
    if found:
        return CheckResult(name, True, "PostToolUse hook registered")
    return CheckResult(name, False, "PostToolUse hook not registered — run /canopy:setup")


def check_session_log(canopy_dir: Path | None = None) -> CheckResult:
    """The session log should exist and have at least one entry."""
    canopy_dir = canopy_dir or CANOPY_DIR
    log = canopy_dir / "session-log.jsonl"
    name = "Session log"
    if not log.exists():
        return CheckResult(name, False, "session-log.jsonl not found — hook may not be firing")
    try:
        lines = sum(1 for line in log.read_text().splitlines() if line.strip())
    except OSError as e:
        return CheckResult(name, False, f"could not read session-log.jsonl: {e}")
    if lines == 0:
        return CheckResult(name, False, "session-log.jsonl is empty — hook may not be firing")
    return CheckResult(name, True, f"session-log.jsonl has {lines} entries")


def check_repo_map(canopy_dir: Path | None = None) -> CheckResult:
    """The repo map should exist and parse as JSON."""
    canopy_dir = canopy_dir or CANOPY_DIR
    repo_map = canopy_dir / "repo-map.json"
    name = "Repo map"
    if not repo_map.exists():
        return CheckResult(name, False, "repo-map.json not found — project identification won't work")
    try:
        data = json.loads(repo_map.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return CheckResult(name, False, f"repo-map.json unreadable: {e}")
    if not isinstance(data, dict):
        return CheckResult(name, False, "repo-map.json is not a JSON object")
    return CheckResult(name, True, f"repo-map.json has {len(data)} project mappings")


def _resolve_token_file(home: Path, canopy_dir: Path) -> Path | None:
    """Mirror the skill's resolution: CLAUDE_PLUGIN_DATA first, then canopy dir."""
    plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if plugin_data:
        candidate = Path(plugin_data) / "workbench-token"
        if candidate.exists():
            return candidate
    fallback = canopy_dir / "workbench-token"
    if fallback.exists():
        return fallback
    return None


def check_workbench_token(
    home: Path | None = None, canopy_dir: Path | None = None
) -> CheckResult:
    """The workbench token must exist, be non-empty, and be mode 600."""
    home = home or Path.home()
    canopy_dir = canopy_dir or CANOPY_DIR
    name = "Workbench token"
    token_file = _resolve_token_file(home, canopy_dir)
    if token_file is None:
        return CheckResult(
            name,
            False,
            f"workbench-token not found at {canopy_dir / 'workbench-token'} — run /canopy:setup",
        )
    try:
        contents = token_file.read_text().strip()
    except OSError as e:
        return CheckResult(name, False, f"could not read {token_file}: {e}")
    if not contents:
        return CheckResult(name, False, f"workbench-token at {token_file} is empty — run /canopy:setup")

    perms = oct(token_file.stat().st_mode & 0o777)[2:]
    if perms != "600":
        return CheckResult(
            name,
            False,
            f"workbench-token exists ({len(contents)} bytes) but permissions are {perms} "
            f"(should be 600) — chmod 600 {token_file}",
        )
    return CheckResult(name, True, f"workbench-token exists ({len(contents)} bytes, permissions {perms})")


def check_plugin_version(home: Path | None = None) -> CheckResult:
    """The installed_plugins.json should record an installed canopy version."""
    home = home or Path.home()
    f = _claude_dir(home) / "plugins" / "installed_plugins.json"
    name = "Plugin version"
    if not f.exists():
        return CheckResult(name, False, "installed_plugins.json not found")
    try:
        data = json.loads(f.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return CheckResult(name, False, f"installed_plugins.json unreadable: {e}")

    for key, val in data.get("plugins", {}).items():
        if "canopy" in key:
            entries = val if isinstance(val, list) else [val]
            if entries and isinstance(entries[0], dict):
                version = entries[0].get("version", "unknown")
                return CheckResult(name, True, f"canopy {version}")
    return CheckResult(name, False, "no canopy entry in installed_plugins.json")


# Order matters for display: registration → state → auth.
_CHECKS = (
    check_hook_registered,
    check_session_log,
    check_repo_map,
    check_workbench_token,
    check_plugin_version,
)


def run_doctor(
    home: Path | None = None, canopy_dir: Path | None = None
) -> tuple[list[CheckResult], bool]:
    """Run every check and return (results, overall_ok).

    ``home`` and ``canopy_dir`` are injectable for testing; production callers
    pass nothing and the real paths are used.
    """
    home = home or Path.home()
    canopy_dir = canopy_dir or CANOPY_DIR

    results = [
        check_hook_registered(home=home),
        check_session_log(canopy_dir=canopy_dir),
        check_repo_map(canopy_dir=canopy_dir),
        check_workbench_token(home=home, canopy_dir=canopy_dir),
        check_plugin_version(home=home),
    ]
    overall_ok = all(r.ok for r in results)
    return results, overall_ok
