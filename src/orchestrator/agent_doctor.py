"""Per-AGENT health checks — `canopy agent doctor`.

`canopy doctor` diagnoses the canopy plugin install; THIS module diagnoses one
agent repo's operational readiness: identity config, gating rails, secrets
manifest, gog email auth, and canopy-web registration + board reachability.
Composes the point-checks that already exist (`resolve_email_identity`,
provision's manifest loaders, `agent_email.preflight`,
`AgentClient.pending_commands`) into one command, so "the agent was set up on
some machine once" stops diverging from "this machine can run the agent".

Born from hal (2026-07-02): hal's gog client existed somewhere, but this
machine had no credentials file, no secrets.yaml to provision it from, and no
canopy-web registration — and nothing in the framework would have said so
short of an actual failed turn. `canopy create-agent` documents these steps
for NEW agents; this doctor verifies them for any agent, any machine, any day.

Same shape as doctor.py: small read-only checks returning CheckResult,
injectable dependencies for tests, `run_agent_doctor` composes them. Unlike
the plugin doctor, two checks are intentionally LIVE (gog token liveness,
canopy-web reachability) — an agent doctor that can't see dead auth would
miss the exact failures it exists to catch.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from orchestrator.doctor import CheckResult
from orchestrator.agent_email import (
    GOG_CONFIG_DIR,
    AgentEmailError,
    EmailIdentity,
    preflight,
    resolve_email_identity,
)
from orchestrator.agent_client import AgentClient, CanopyError
from orchestrator.provision import ProvisionError, load_env_block, load_manifest


def check_identity(repo: Path) -> tuple[CheckResult, EmailIdentity | None]:
    """config/agent.json (+ plugin.json) must yield a full email identity."""
    name = "Identity"
    try:
        ident = resolve_email_identity(repo)
    except AgentEmailError as e:
        return CheckResult(name, False, str(e)), None
    return CheckResult(
        name, True,
        f"slug={ident.slug} mailbox={ident.account} gog_client={ident.client}",
    ), ident


def check_gating(repo: Path) -> CheckResult:
    """config/gating.json must exist and parse — the agent's rails."""
    name = "Gating rails"
    path = Path(repo) / "config" / "gating.json"
    if not path.exists():
        return CheckResult(name, False, f"{path} not found — the agent has no rails")
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return CheckResult(name, False, f"{path} unreadable: {e}")
    deny, approve = data.get("deny", []), data.get("approve", [])
    return CheckResult(name, True, f"{len(deny)} deny rail(s), {len(approve)} approve rule(s)")


def check_secrets_manifest(repo: Path) -> CheckResult:
    """config/secrets.yaml must exist and parse, so `canopy provision` can
    rebuild this machine's agent state. Structural only — op-ref resolution
    stays in `canopy provision --check` (needs a 1Password session)."""
    name = "Secrets manifest"
    path = Path(repo) / "config" / "secrets.yaml"
    if not path.exists():
        return CheckResult(
            name, False,
            f"{path} not found — agent state won't survive a new machine; "
            "declare secrets there and run `canopy provision` "
            "(see create-agent § Channel + setup)",
        )
    try:
        secrets = load_manifest(Path(repo))
        env = load_env_block(Path(repo))
    except ProvisionError as e:
        return CheckResult(name, False, str(e))
    n_env = len(env.vars) if env else 0
    return CheckResult(
        name, True,
        f"{len(secrets)} file secret(s), {n_env} env var(s) — "
        "validate refs via `canopy provision --check`",
    )


def check_email_auth(
    identity: EmailIdentity | None,
    *,
    gog_dir: str | None = None,
    runner=subprocess.run,
) -> CheckResult:
    """Live gog Gmail auth for the agent's own client (wraps email preflight)."""
    name = "Email auth (gog)"
    if identity is None:
        return CheckResult(name, False, "skipped — identity unresolved")
    ok, lines = preflight(identity, gog_dir=gog_dir or GOG_CONFIG_DIR, runner=runner)
    detail = lines[0] if lines else ("ready" if ok else "failed")
    return CheckResult(name, ok, detail.removeprefix("OK: ").removeprefix("FIX: "))


def check_registration(
    identity: EmailIdentity | None,
    *,
    client_factory=AgentClient,
) -> CheckResult:
    """Agent registered on canopy-web and its board reachable (one live GET)."""
    name = "canopy-web board"
    if identity is None:
        return CheckResult(name, False, "skipped — identity unresolved")
    try:
        pending = client_factory({"slug": identity.slug}).pending_commands()
    except CanopyError as e:
        msg = str(e)
        if "404" in msg or "not found" in msg.lower():
            return CheckResult(
                name, False,
                f"agent {identity.slug!r} not registered — run "
                "`canopy agent-publish register --repo .`",
            )
        return CheckResult(name, False, msg)
    except RuntimeError as e:  # missing PAT / transport config
        return CheckResult(name, False, str(e))
    return CheckResult(name, True, f"registered; board reachable ({len(pending)} pending command(s))")


def run_agent_doctor(
    repo: Path,
    *,
    gog_dir: str | None = None,
    runner=subprocess.run,
    client_factory=AgentClient,
) -> tuple[list[CheckResult], bool]:
    """Run every per-agent check and return (results, overall_ok).

    ``gog_dir``, ``runner`` and ``client_factory`` are injectable for testing;
    production callers pass nothing and the real dependencies are used.
    """
    repo = Path(repo)
    ident_result, identity = check_identity(repo)
    results = [
        ident_result,
        check_gating(repo),
        check_secrets_manifest(repo),
        check_email_auth(identity, gog_dir=gog_dir, runner=runner),
        check_registration(identity, client_factory=client_factory),
    ]
    overall_ok = all(r.ok for r in results)
    return results, overall_ok
