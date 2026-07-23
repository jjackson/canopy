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

A check that cries wolf is worse than no check: three of the five agents reported FAIL on a
healthy machine (2026-07-23), and every one was a false positive — gating counted only the
local `deny` array while the rails actually in force come from the fleet baseline mounted via
`channels`; hook wiring recognized only `.claude/settings.json` and not the plugin-style
`hooks/hooks.json` that ace uses; and auth-services demanded the fleet-wide LOGIN_SERVICES of
every agent, failing hal/ace over a scope they never call while missing that echo needs one
the constant omits. Each check must therefore model what actually runs at call time, and each
requirement must be the AGENT's, not the fleet's. This matters doubly because auto-heal is
built on top: healing a false positive damages a working agent.

Same shape as doctor.py: small read-only checks returning CheckResult,
injectable dependencies for tests, `run_agent_doctor` composes them. Unlike
the plugin doctor, two checks are intentionally LIVE (gog token liveness,
canopy-web reachability) — an agent doctor that can't see dead auth would
miss the exact failures it exists to catch.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from orchestrator.doctor import CheckResult
from orchestrator.agent_email import (
    GOG_CONFIG_DIR,
    AgentEmailError,
    EmailIdentity,
    granted_services,
    preflight,
    resolve_email_identity,
)
from orchestrator.agent_client import AgentClient, CanopyError
from orchestrator.provision import ProvisionError, load_env_block, load_manifest


_PLACEHOLDER_DOMAINS = {"example.com", "example.org", "example.net"}

# The gog services EVERY agent's mailbox needs. Deliberately NOT `LOGIN_SERVICES` — that
# constant is the generous default for an interactive `gog login`, not a per-agent
# REQUIREMENT. Demanding it of everyone reported hal/ace as broken over `appscript`, which
# neither uses, while missing that echo genuinely needs `slides` (not in the constant at all).
# Agents extend this by declaring `gog_services` in config/agent.json.
CORE_SERVICES = ("gmail", "drive", "docs", "sheets", "forms")


def _baseline_rails(cfg: dict) -> list | None:
    """The FLEET-BASELINE deny rails this agent mounts via `channels`, mirroring what
    hooks/gating_guard.py merges in at call time.

    A repo whose config/gating.json has `"deny": []` but `"channels": ["email"]` is fully
    railed at runtime — the baseline rails (agent-core/gating-baseline.json, shipped with the
    canopy plugin) are merged IN FRONT of the local list. Counting only the local `deny`
    array reported echo and hal as unrailed when they were not.

    Returns [] for legacy configs (no `channels`), or None when channels are mounted but the
    baseline can't be resolved — the state in which gating_guard fails CLOSED.
    """
    channels = cfg.get("channels")
    if not channels:
        return []
    try:
        plugin_dir = os.environ.get("CANOPY_PLUGIN_DIR")
        if not plugin_dir:
            reg = json.loads(
                (Path("~/.claude/plugins/installed_plugins.json").expanduser()).read_text())
            plugin_dir = reg["plugins"]["canopy@canopy"][0]["installPath"]
        base = json.loads(
            (Path(plugin_dir) / "agent-core" / "gating-baseline.json").read_text())
    except Exception:
        return None
    rails: list = []
    for ch in channels:
        rails.extend(base.get("channels", {}).get(ch, []))
    return rails


def required_services(identity: EmailIdentity | None) -> tuple[set[str], str]:
    """(required services, where that came from) for an agent's gog login.

    Per-agent via `gog_services` in config/agent.json; otherwise CORE_SERVICES. Lets echo
    require `slides` and hal not require `appscript`, instead of one fleet-wide list that is
    simultaneously too strict for some agents and too loose for others.
    """
    repo = getattr(identity, "repo", None)
    if repo:
        try:
            data = json.loads((Path(repo) / "config" / "agent.json").read_text())
        except (json.JSONDecodeError, OSError):
            data = {}
        declared = data.get("gog_services")
        if isinstance(declared, str):
            declared = declared.split(",")
        if declared:
            svc = {s.strip() for s in declared if isinstance(s, str) and s.strip()}
            if svc:
                return svc, "config/agent.json gog_services"
    return set(CORE_SERVICES), "fleet core"


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
    channels = data.get("channels") or []
    baseline = _baseline_rails(data)
    shims = list((Path(repo) / "bin").glob("*-email"))
    if baseline is None:
        return CheckResult(
            name, False,
            f"gating.json mounts channels {channels} but the fleet gating baseline "
            "(agent-core/gating-baseline.json) is unresolvable — gating_guard fails CLOSED, "
            "so every guarded tool call is blocked until the canopy plugin is installed or "
            "updated (/canopy:update)",
        )
    effective = len(baseline) + len(deny)
    if not effective and shims:
        return CheckResult(
            name, False,
            f"0 effective deny rails but {shims[0].name} exists — an outbound-capable agent "
            "needs at least the raw-send rail: mount it with \"channels\": [\"email\"] or add "
            "a local rail (see the factory's templated gating.json)",
        )
    return CheckResult(
        name, True,
        f"{effective} effective deny rail(s) — {len(baseline)} fleet-baseline via "
        f"channels={channels} + {len(deny)} local; {len(approve)} approve rule(s)",
    )


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
    # TWO valid registration paths. Repo-style agents wire the guard in .claude/settings.json;
    # agents shipped AS a Claude Code plugin (ace) wire it in hooks/hooks.json, which the
    # harness loads from the plugin root. Checking only the former reported ace's rails as
    # decorative when its guard is registered and firing.
    candidates = (
        (Path(repo) / ".claude" / "settings.json", ".claude/settings.json"),
        (Path(repo) / "hooks" / "hooks.json", "hooks/hooks.json"),
    )
    unreadable = []
    for path, label in candidates:
        if not path.exists():
            continue
        try:
            settings = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            unreadable.append(f"{label} unreadable: {e}")
            continue
        pre = settings.get("hooks", {}).get("PreToolUse", [])
        if any("gating_guard.py" in (h.get("command") or "")
               for entry in pre for h in entry.get("hooks", [])):
            return CheckResult(name, True,
                               f"gating_guard.py registered as a PreToolUse hook via {label}")
    if unreadable:
        return CheckResult(name, False, "; ".join(unreadable))
    return CheckResult(
        name, False,
        "no PreToolUse hook invokes gating_guard.py — the rails in config/gating.json are "
        f"decorative until one does; wire it in {repo}/.claude/settings.json (repo-style) or "
        f"{repo}/hooks/hooks.json (plugin-style)",
    )


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


def check_auth_services(
    identity: EmailIdentity | None,
    *,
    runner=subprocess.run,
) -> CheckResult:
    """Every service THIS agent requires is actually granted for its gog auth.

    Email auth (check_email_auth) proves the token is alive for Gmail; this proves the login
    covered the surface the agent actually uses. A token that works for Gmail but never
    consented to, say, Slides would silently 403 the first time the agent builds a deck, so
    we catch it here with the exact re-login fix.

    The requirement is PER-AGENT (`required_services`), not the fleet-wide LOGIN_SERVICES
    default: requiring that constant of everyone failed hal and ace over `appscript`, which
    neither uses, while never noticing that echo needs `slides`, which the constant omits.

    `granted_services` returning None means gog couldn't be introspected (not installed,
    account not found) — that's a SKIP (check_email_auth already owns the hard auth
    failure), not a second red herring."""
    name = "Auth services"
    if identity is None:
        return CheckResult(name, False, "skipped — identity unresolved")
    required, source = required_services(identity)
    granted = granted_services(identity, runner=runner)
    if granted is None:
        return CheckResult(name, True, "skipped — gog auth not introspectable (see Email auth)")
    missing = sorted(required - granted)
    if missing:
        # Re-login with required UNION already-granted: `gog login --services` REPLACES the
        # grant set, so remediating with the required list alone would silently revoke scopes
        # the agent had and uses.
        relogin = ",".join(sorted(required | granted))
        return CheckResult(
            name, False,
            f"missing scope(s) {missing} for {identity.account} (required per {source}) — "
            f"re-run: gog login {identity.account} --client {identity.client} "
            f"--services {relogin}",
        )
    return CheckResult(
        name, True,
        f"all {len(required)} required service(s) granted per {source} "
        f"({','.join(sorted(required))})",
    )


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
        check_auth_services(identity, runner=runner),
        check_registration(identity, client_factory=client_factory),
    ]
    overall_ok = all(r.ok for r in results)
    return results, overall_ok
