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


_PLACEHOLDER_DOMAINS = {"example.com", "example.org", "example.net"}


def _is_placeholder_mailbox(addr: str) -> bool:
    """The factory stamps `<slug>@example.com` when no real address is given — resolvable, but
    NOT a configured agent. Treat that (and an empty address) as not-ready."""
    a = (addr or "").strip().lower()
    return not a or a.rsplit("@", 1)[-1] in _PLACEHOLDER_DOMAINS


def check_identity(repo: Path) -> tuple[CheckResult, EmailIdentity | None]:
    """config/agent.json (+ plugin.json) must yield a full, NON-placeholder email identity."""
    name = "Identity"
    try:
        ident = resolve_email_identity(repo)
    except AgentEmailError as e:
        return CheckResult(name, False, str(e)), None
    detail = f"slug={ident.slug} mailbox={ident.account} gog_client={ident.client}"
    # A resolvable-but-placeholder mailbox passes the resolver but silently reads as "ready" — the
    # exact trap that let eva sit on `eva@example.com`. Flag it instead of rubber-stamping it.
    if _is_placeholder_mailbox(ident.account):
        return CheckResult(
            name, False,
            f"{detail} — mailbox is the factory PLACEHOLDER; set a real address in "
            'config/agent.json ("email") and mint/vault it before wiring email',
        ), ident
    return CheckResult(name, True, detail), ident


def check_gating(repo: Path) -> CheckResult:
    """config/gating.json must exist and parse — the agent's rails.

    An outbound-capable agent (it has an email shim) with ZERO deny rails is the exact
    unsafe state the rails exist to prevent, so that combination fails rather than
    passing on "the file parses".
    """
    name = "Gating rails"
    path = Path(repo) / "config" / "gating.json"
    if not path.exists():
        return CheckResult(name, False, f"{path} not found — the agent has no rails")
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return CheckResult(name, False, f"{path} unreadable: {e}")
    deny, approve = data.get("deny", []), data.get("approve", [])
    shims = list((Path(repo) / "bin").glob("*-email"))
    if not deny and shims:
        return CheckResult(
            name, False,
            f"0 deny rails but {shims[0].name} exists — an outbound-capable agent "
            "needs at least the raw-send rail (see the factory's templated gating.json)",
        )
    return CheckResult(name, True, f"{len(deny)} deny rail(s), {len(approve)} approve rule(s)")


def check_hook_wiring(repo: Path) -> CheckResult:
    """The rails are only real if the PreToolUse hook is actually REGISTERED.

    config/gating.json without .claude/settings.json wiring hooks/gating_guard.py is
    decorative — the exact "set up somewhere, not on this repo" drift class this doctor
    exists to catch. Checks: guard file exists + settings.json references it under a
    PreToolUse matcher.
    """
    name = "Hook wiring"
    guard = Path(repo) / "hooks" / "gating_guard.py"
    if not guard.exists():
        return CheckResult(name, False, f"{guard} missing — rails have no enforcement")
    settings_path = Path(repo) / ".claude" / "settings.json"
    if not settings_path.exists():
        return CheckResult(
            name, False,
            f"{settings_path} missing — gating_guard.py is never invoked; wire it as a "
            "PreToolUse hook (see the factory's templated settings.json)",
        )
    try:
        settings = json.loads(settings_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return CheckResult(name, False, f"{settings_path} unreadable: {e}")
    pre = settings.get("hooks", {}).get("PreToolUse", [])
    wired = any(
        "gating_guard.py" in (h.get("command") or "")
        for entry in pre for h in entry.get("hooks", [])
    )
    if not wired:
        return CheckResult(
            name, False,
            f"{settings_path} has no PreToolUse hook invoking gating_guard.py — "
            "the rails in config/gating.json are decorative until it does",
        )
    return CheckResult(name, True, "gating_guard.py registered as a PreToolUse hook")


def check_secrets_manifest(repo: Path) -> CheckResult:
    """config/secrets.yaml must exist and parse, so `canopy provision` can
    rebuild this machine's agent state. Structural only — op-ref resolution
    stays in `canopy provision --check` (needs a 1Password session)."""
    name = "Secrets manifest"
    path = Path(repo) / "config" / "secrets.yaml"
    if not path.exists():
        # Escape hatch for agents with their own provisioning (ACE: .env.tpl +
        # `op inject`) — declared, not inferred, so absence stays a failure by default.
        agent_json = Path(repo) / "config" / "agent.json"
        try:
            provisioning = json.loads(agent_json.read_text()).get("provisioning", "")
        except (OSError, ValueError):
            provisioning = ""
        if provisioning:
            return CheckResult(
                name, True,
                f"self-managed ({provisioning}) — declared in agent.json; "
                "no canopy provision manifest expected",
            )
        return CheckResult(
            name, False,
            f"{path} not found — agent state won't survive a new machine; "
            "declare secrets there and run `canopy provision` "
            "(see create-agent § Channel + setup), or declare \"provisioning\" "
            "in config/agent.json if this agent provisions itself",
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
    # Keep the WHOLE remediation — preflight's multi-line FIX blocks carry the exact
    # command / console URL; truncating to the first line hides the actual fix.
    detail = " ".join(l.strip() for l in lines) if lines else ("ready" if ok else "failed")
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
        check_hook_wiring(repo),
        check_secrets_manifest(repo),
        check_email_auth(identity, gog_dir=gog_dir, runner=runner),
        check_registration(identity, client_factory=client_factory),
    ]
    overall_ok = all(r.ok for r in results)
    return results, overall_ok
