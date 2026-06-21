"""Portable agent secret provisioning from 1Password.

The problem: agents need credentials (service-account keys, OAuth creds, PATs) that must never
live in git, yet must be available wherever the agent runs — the main checkout, any emdash
worktree, and on every operator's machine. Hand-shuffling keys around is the lazy, non-portable
status quo.

The fix: each agent/provider repo declares a tracked `config/secrets.yaml` that lists what it
needs as **1Password references + local targets** (NO secret values). `canopy provision`
materializes them via the `op` CLI into their targets — idempotent, validated, one command on any
machine. 1Password is the source of truth (the house standard; `op` is already the auth path for
echo/ace/chrome-sales).

Manifest (`config/secrets.yaml`):

    secrets:
      - name: chrome-sales-gws-sa          # human label
        op: "op://AI-Agents/chrome-sales GWS SA/key"   # what `op read` resolves
        target: "{repo}/.gws-sa-key.json"  # where to write ({repo} = this repo; ~ ok; rel = repo-relative)
        mode: "0600"                        # default 0600 for files
        optional: false                     # if true, a missing op ref is skipped, not an error

Targets that should survive worktrees (things an agent reads globally) point at an absolute path
like `~/.canopy/agents/<slug>/<name>`; provider-local creds (e.g. chrome-sales's MCP keys) point
at `{repo}/...` in the provider's main checkout, where its launcher resolves them.
"""
from __future__ import annotations

import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml


class ProvisionError(Exception):
    pass


@dataclass
class Secret:
    name: str
    op_ref: str
    target: str
    mode: str = "0600"
    optional: bool = False


def load_manifest(repo: Path) -> list[Secret]:
    """Parse <repo>/config/secrets.yaml into Secret entries."""
    path = Path(repo) / "config" / "secrets.yaml"
    if not path.exists():
        raise ProvisionError(f"no secrets manifest at {path}")
    data = yaml.safe_load(path.read_text()) or {}
    items = data.get("secrets") or []
    if not isinstance(items, list):
        raise ProvisionError(f"{path}: `secrets` must be a list")
    out = []
    for i, it in enumerate(items):
        if not isinstance(it, dict) or not it.get("name") or not it.get("op") or not it.get("target"):
            raise ProvisionError(f"{path}: secret #{i} needs name, op, target")
        out.append(Secret(
            name=it["name"], op_ref=it["op"], target=it["target"],
            mode=str(it.get("mode", "0600")), optional=bool(it.get("optional", False)),
        ))
    return out


def resolve_target(target: str, repo: Path) -> Path:
    """Resolve a manifest target to an absolute path: {repo} → repo; ~ expanded; rel → repo/rel."""
    t = target.replace("{repo}", str(Path(repo)))
    p = Path(t).expanduser()
    if not p.is_absolute():
        p = Path(repo) / p
    return p


def _op_read(ref: str) -> str:
    """Resolve a 1Password reference to its value via the `op` CLI."""
    try:
        r = subprocess.run(["op", "read", ref], capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        raise ProvisionError("the 1Password CLI `op` is not installed / on PATH")
    except subprocess.TimeoutExpired:
        raise ProvisionError(f"`op read {ref}` timed out")
    if r.returncode != 0:
        raise ProvisionError(f"`op read {ref}` failed: {r.stderr.strip()[:200]}")
    return r.stdout


def provision(repo: Path, *, op_read=_op_read, check: bool = False) -> dict:
    """Materialize every secret in the repo's manifest from 1Password into its target.

    check=True validates that each op ref resolves (and reports where it WOULD write) without
    writing anything. Returns {provisioned, skipped, errors, results}. Idempotent: re-running
    overwrites targets with the current 1Password value.
    """
    repo = Path(repo)
    secrets = load_manifest(repo)
    results, errors = [], []
    provisioned = skipped = 0
    for s in secrets:
        dest = resolve_target(s.target, repo)
        try:
            value = op_read(s.op_ref)
        except ProvisionError as e:
            if s.optional:
                skipped += 1
                results.append({"name": s.name, "status": "skipped", "reason": str(e)})
                continue
            errors.append(f"{s.name}: {e}")
            results.append({"name": s.name, "status": "error", "reason": str(e)})
            continue
        if not value.strip():
            (errors if not s.optional else None)
            results.append({"name": s.name, "status": "empty", "target": str(dest)})
            if not s.optional:
                errors.append(f"{s.name}: 1Password returned an empty value")
            else:
                skipped += 1
            continue
        if check:
            results.append({"name": s.name, "status": "ok", "target": str(dest), "would_write": True})
            provisioned += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(value)
        try:
            dest.chmod(int(s.mode, 8))
        except ValueError:
            dest.chmod(0o600)
        results.append({"name": s.name, "status": "written", "target": str(dest),
                        "mode": oct(stat.S_IMODE(dest.stat().st_mode))})
        provisioned += 1
    return {
        "repo": str(repo), "check": check,
        "provisioned": provisioned, "skipped": skipped,
        "errors": errors, "results": results,
    }
