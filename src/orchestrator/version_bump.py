"""Atomic-ish VERSION coordination across worktrees.

Two parallel canopy worktrees have repeatedly bumped VERSION to the same
number, requiring manual rebase + force-push recovery. The fix:

- `canopy version verify` — confirm VERSION and plugin.json agree (CI-safe)
- `canopy version bump` — pick `max(local, origin/main) + patch+1`, write both
  files atomically. Fetches origin first so a parallel worktree's bump is
  visible before deciding the next number.

Doesn't fully solve concurrent pushes — the second push will still fail and
need re-bump — but it solves the common case where the user forgot to fetch
before bumping.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _parse(version: str) -> tuple[int, int, int]:
    if not VERSION_RE.match(version.strip()):
        raise ValueError(f"Not a semver patch string: {version!r}")
    major, minor, patch = version.strip().split(".")
    return int(major), int(minor), int(patch)


def _format(parts: tuple[int, int, int]) -> str:
    return ".".join(str(p) for p in parts)


def _read_version_file(path: Path) -> str:
    return path.read_text().strip()


_PLUGIN_VERSION_LINE_RE = re.compile(r'("version"\s*:\s*")[\d.]+(")')


def _read_plugin_json_version(path: Path) -> str:
    """Extract the version field via regex — avoids round-tripping JSON which
    would normalize formatting (unicode escapes, array layout, etc.)."""
    text = path.read_text()
    match = _PLUGIN_VERSION_LINE_RE.search(text)
    if not match:
        raise ValueError(f"Could not find a version line in {path}")
    # Re-extract just the version string between the quotes
    inner = re.search(r'"version"\s*:\s*"([\d.]+)"', text)
    return inner.group(1) if inner else ""


def _write_plugin_json_version(path: Path, new_version: str) -> None:
    """Surgical replace of the version line — preserves all other formatting."""
    text = path.read_text()
    new_text, n = _PLUGIN_VERSION_LINE_RE.subn(rf'\g<1>{new_version}\g<2>', text, count=1)
    if n != 1:
        raise ValueError(f"Could not find a version line to replace in {path}")
    path.write_text(new_text)


def find_version_files(repo_root: Path) -> tuple[Path, Path]:
    """Locate the VERSION file and plugins/canopy/.claude-plugin/plugin.json."""
    version_path = repo_root / "VERSION"
    plugin_json_path = repo_root / "plugins" / "canopy" / ".claude-plugin" / "plugin.json"
    if not version_path.is_file():
        raise FileNotFoundError(f"VERSION not found at {version_path}")
    if not plugin_json_path.is_file():
        raise FileNotFoundError(f"plugin.json not found at {plugin_json_path}")
    return version_path, plugin_json_path


def verify(repo_root: Path) -> tuple[bool, str, str]:
    """Return (matches, version_text, plugin_json_text). Use for CI checks."""
    v_path, p_path = find_version_files(repo_root)
    v = _read_version_file(v_path)
    p = _read_plugin_json_version(p_path)
    return (v == p, v, p)


def fetch_origin_main_version(repo_root: Path) -> str | None:
    """Fetch origin and read VERSION from origin/main. Returns None on failure."""
    try:
        subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=repo_root, capture_output=True, text=True, timeout=15, check=False,
        )
        result = subprocess.run(
            ["git", "show", "origin/main:VERSION"],
            cwd=repo_root, capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode != 0:
            return None
        text = result.stdout.strip()
        if VERSION_RE.match(text):
            return text
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def compute_next_version(local: str, origin: str | None) -> str:
    """Pick the next version: max(local, origin) with patch+1.

    Handles the case where another worktree already bumped on origin/main
    while we were working — we'll bump from origin's number, not ours.
    """
    candidates = [_parse(local)]
    if origin is not None:
        candidates.append(_parse(origin))
    base = max(candidates)
    bumped = (base[0], base[1], base[2] + 1)
    return _format(bumped)


def bump(repo_root: Path) -> dict:
    """Compute and write the next version. Returns a summary dict."""
    v_path, p_path = find_version_files(repo_root)
    matches, local_v, plugin_v = verify(repo_root)
    if not matches:
        raise ValueError(
            f"VERSION ({local_v}) and plugin.json ({plugin_v}) disagree — "
            f"fix the mismatch before bumping."
        )
    origin_v = fetch_origin_main_version(repo_root)
    next_v = compute_next_version(local_v, origin_v)
    v_path.write_text(next_v + "\n")
    _write_plugin_json_version(p_path, next_v)
    return {
        "previous_local": local_v,
        "origin_main": origin_v,
        "new_version": next_v,
        "version_path": str(v_path),
        "plugin_json_path": str(p_path),
    }
