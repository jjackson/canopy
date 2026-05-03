"""CLI entry point for the orchestrator."""

from pathlib import Path
import click
from orchestrator.paths import CANOPY_DIR, ensure_canopy_dir
from orchestrator.registry import (
    load_registry, get_all_servers, get_all_tools, get_workflows,
    format_for_skill, RegistryError,
)
from orchestrator.capture import read_session_log, group_by_session, classify_sessions
from orchestrator.pipeline import run_cycle, CycleConfig
from orchestrator.server import run_server


def find_registry() -> Path:
    candidates = [
        Path.cwd() / "registry.yaml",
        Path(__file__).parent.parent.parent / "registry.yaml",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise click.ClickException("registry.yaml not found")


@click.group()
def main():
    """Canopy — self-improving MCP orchestration."""


@main.group()
def registry():
    """Registry commands."""


@registry.command("show")
@click.option("--format", "fmt", type=click.Choice(["summary", "skill", "json"]), default="summary")
def registry_show(fmt):
    """Display the loaded registry."""
    try:
        reg = load_registry(find_registry())
    except RegistryError as e:
        raise click.ClickException(str(e))

    if fmt == "skill":
        click.echo(format_for_skill(reg))
    elif fmt == "json":
        import json
        click.echo(json.dumps(reg, indent=2, default=str))
    else:
        servers = get_all_servers(reg)
        tools = get_all_tools(reg)
        workflows = get_workflows(reg)
        click.echo(f"Registry v{reg['version']} — {len(servers)} servers, {len(tools)} tools, {len(workflows)} workflows")
        click.echo()
        for s in servers:
            tool_count = len([t for t in tools if t["server"] == s["name"]])
            click.echo(f"  [{s['domain']}] {s['name']} — {s['description']} ({tool_count} tools, {s.get('data_access', '?')})")


@registry.command("sync")
def registry_sync():
    """Sync registry tools with actual MCP server code."""
    from orchestrator.registry_sync import sync_registry

    try:
        reg_path = find_registry()
    except click.ClickException:
        raise

    click.echo(f"Scanning repos for MCP tools...")
    summary = sync_registry(reg_path)

    for server, info in sorted(summary.items()):
        if isinstance(info, dict) and "error" in info:
            click.echo(f"  {server}: {info['error']}")
        elif isinstance(info, dict):
            added = info.get("added", [])
            removed = info.get("removed", [])
            total = info.get("total", 0)
            if added or removed:
                click.echo(f"  {server}: {total} tools ({len(added)} added, {len(removed)} removed)")
                for a in added:
                    click.echo(f"    + {a}")
                for r in removed:
                    click.echo(f"    - {r}")
            else:
                click.echo(f"  {server}: {total} tools (up to date)")

    click.echo()
    click.echo("Registry synced.")


@registry.command("validate")
def registry_validate():
    """Validate registry.yaml structure."""
    try:
        reg = load_registry(find_registry())
    except RegistryError as e:
        raise click.ClickException(str(e))

    errors = []
    for server in get_all_servers(reg):
        if not server.get("tools"):
            errors.append(f"Server {server['name']} has no tools")
        if not server.get("answers"):
            errors.append(f"Server {server['name']} has no answers")
        if not server.get("ownership"):
            errors.append(f"Server {server['name']} has no ownership field")

    if errors:
        for e in errors:
            click.echo(f"  ERROR: {e}", err=True)
        raise click.ClickException(f"{len(errors)} validation errors")
    else:
        click.echo("Registry is valid.")


@main.group()
def sessions():
    """Session log commands."""


@sessions.command("list")
@click.option("--hours", default=24, type=int, help="Only show sessions with activity in the last N hours")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON (for skill consumption)")
@click.option("--project", default=None,
              help="Filter to sessions whose resolved GitHub repo ends with /<name>. "
                   "Uses repo-map (incl. emdash worktree path inference). "
                   "Example: --project ace matches jjackson/ace but NOT jjackson/ace-web.")
def sessions_list(hours, as_json, project):
    """List recent sessions grouped by project."""
    import json as json_mod
    from datetime import datetime, timezone, timedelta

    from orchestrator.scanner import scan_all_transcripts
    from orchestrator.repo_map import load_repo_map
    from orchestrator.labels import load_labels

    projects_dir = Path.home() / ".claude" / "projects"
    state_dir = ensure_canopy_dir()
    repo_map = load_repo_map(state_dir / "repo-map.json")
    labels = load_labels(state_dir / "labels.yaml")

    all_sessions = scan_all_transcripts(projects_dir, repo_map, labels)

    # Filter by recency
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_iso = cutoff.isoformat()
    recent = [s for s in all_sessions if s.get("last_ts") and s["last_ts"] >= cutoff_iso]

    # Filter by project (precise: repo must end with /<name>; never substring-matches).
    # Uses scanner's resolved `repo` field which honors emdash worktree inference,
    # so deleted-worktree sessions still get classified correctly.
    if project:
        suffix = f"/{project}"
        recent = [s for s in recent if (s.get("repo") or "").endswith(suffix)]

    recent.sort(key=lambda s: s["last_ts"], reverse=True)

    if as_json:
        click.echo(json_mod.dumps(recent, indent=2, default=str))
        return

    if not recent:
        click.echo(f"No sessions with activity in the last {hours} hours.")
        return

    click.echo(f"Sessions with activity in the last {hours} hours:\n")
    for i, s in enumerate(recent, 1):
        project = s.get("repo") or s["project_key"]
        ts = s["last_ts"][:16].replace("T", " ")
        msg = s["first_msg"][:50] + ("..." if len(s["first_msg"]) > 50 else "")
        click.echo(f"  {i:>3}  [{ts}]  {project:<30}  \"{msg}\"  ({s['user_msgs']} msgs)")


@sessions.command("status")
def sessions_status():
    """Show session log status."""
    log_file = CANOPY_DIR / "session-log.jsonl"
    entries = read_session_log(log_file)
    if not entries:
        click.echo("No session log entries found.")
        return

    groups = group_by_session(entries)
    classified = classify_sessions(groups)

    click.echo(f"Session log: {len(entries)} entries, {len(groups)} sessions")
    click.echo(f"  Multi-server sessions: {len(classified['multi_server'])}")
    click.echo(f"  Single-server sessions: {len(classified['single_server'])}")

    latest = entries[-1]
    click.echo(f"  Latest: {latest['ts']} — {latest['server']}.{latest['tool']}")


@main.command("improve")
@click.option("--observe-only", is_flag=True, help="Analyze transcripts but don't propose or implement")
@click.option("--dry-run", is_flag=True, help="Analyze and propose but don't implement")
@click.option("--model", default="sonnet", help="Model to use for analysis/proposals")
def improve(observe_only, dry_run, model):
    """Run an improvement cycle — analyze sessions, propose and implement improvements."""
    state_dir = ensure_canopy_dir()

    try:
        registry_path = find_registry()
    except click.ClickException:
        raise

    config = CycleConfig(
        observe_only=observe_only,
        dry_run=dry_run,
        model=model,
    )

    click.echo("Starting improvement cycle...")
    if observe_only:
        click.echo("  Mode: observe-only (no proposals or implementation)")
    elif dry_run:
        click.echo("  Mode: dry-run (no implementation)")

    result = run_cycle(
        state_dir=state_dir,
        registry_path=registry_path,
        config=config,
    )

    _print_cycle_result(result)


@main.command("analyze")
@click.argument("transcript", type=click.Path(exists=True))
@click.option("--propose", is_flag=True, help="Also generate proposals from observations")
@click.option("--model", default="sonnet", help="Model to use")
@click.option("--budget", default=1.0, type=float, help="Max USD per claude -p call")
def analyze_cmd(transcript, propose, model, budget):
    """Analyze a specific transcript file for observations and proposals."""
    import sys
    import yaml
    from orchestrator.analyzer import analyze_transcript
    from orchestrator.proposer import generate_proposals
    from orchestrator.observations import create_observation, save_observation
    from orchestrator.proposals import create_proposal, save_proposal

    # STATUS sentinel: emitted unconditionally before any heavy work, flushed
    # immediately. Lets background-bash callers distinguish "process never
    # produced output" (0-byte file = something killed the command before it
    # started, e.g. uv venv contention under parallel launches) from
    # "process started, ran the LLM call, produced no observations". Surfaced
    # by a session-review run that fanned out 10 parallel `canopy analyze`
    # background tasks; 9 produced 0 bytes and the 1 that ran returned
    # "No observations" on a session that had 9 findings on a sequential
    # rerun. Without this sentinel the failure was invisible.
    click.echo(f"STATUS: STARTED analyze {transcript}")
    sys.stdout.flush()

    try:
        registry_path = find_registry()
    except click.ClickException:
        click.echo(f"STATUS: FAILED registry-not-found", err=False)
        sys.stdout.flush()
        raise

    reg = load_registry(registry_path)
    registry_summary = format_for_skill(reg)

    state_dir = ensure_canopy_dir()

    click.echo(f"Analyzing: {transcript}")
    click.echo()

    try:
        observations = analyze_transcript(
            Path(transcript), registry_summary, model=model, max_budget_usd=budget,
        )
    except Exception as e:
        click.echo(f"STATUS: FAILED analyze-raised {type(e).__name__}: {e}")
        sys.stdout.flush()
        raise

    if not observations:
        click.echo("No observations found.")
        click.echo("STATUS: DONE 0-observations")
        sys.stdout.flush()
        return

    click.echo(f"Found {len(observations)} observations:")
    click.echo()

    # Save and display
    obs_dir = state_dir / "observations"
    saved = []
    for obs_data in observations:
        obs = create_observation(
            obs_type=obs_data.get("type", "gap"),
            description=obs_data.get("description", ""),
            severity=obs_data.get("severity", "medium"),
            session_id=Path(transcript).stem,
            related_servers=obs_data.get("related_servers", []),
            lifecycle_stage=obs_data.get("lifecycle_stage"),
        )
        save_observation(obs, obs_dir)
        saved.append(obs)
        click.echo(f"  [{obs['severity']}] {obs['description']}")

    if not propose:
        click.echo(f"STATUS: DONE {len(saved)}-observations no-propose")
        sys.stdout.flush()
        return

    click.echo()
    click.echo("Generating proposals...")
    click.echo()

    from orchestrator.skill_catalog import build_catalog, format_for_prompt
    catalog = build_catalog()
    catalog_text = format_for_prompt(catalog)

    try:
        proposals_raw = generate_proposals(
            saved, registry_summary, model=model, max_budget_usd=budget,
            skill_catalog=catalog_text,
        )
    except Exception as e:
        click.echo(f"STATUS: FAILED propose-raised {type(e).__name__}: {e}")
        sys.stdout.flush()
        raise

    if not proposals_raw:
        click.echo("No proposals generated.")
        click.echo(f"STATUS: DONE {len(saved)}-observations 0-proposals")
        sys.stdout.flush()
        return

    # Validate and fix proposals against the registry + skill catalog
    proposals_raw, dropped = _validate_proposals(proposals_raw, reg, catalog)

    if dropped:
        click.echo(f"Dropped {len(dropped)} duplicate/redundant proposal(s):")
        for d in dropped:
            reason = d.get("_dropped", "unknown reason")
            preview = (d.get("action") or "").replace("\n", " ")[:80]
            click.echo(f"  [dropped: {reason}]")
            click.echo(f"    {preview}")
        click.echo()

    proposals_dir = state_dir / "proposals"
    click.echo(f"Generated {len(proposals_raw)} proposals:")
    click.echo()
    for i, p_data in enumerate(proposals_raw, 1):
        proposal = create_proposal(
            proposal_type=p_data.get("type", "new_tool"),
            action=p_data.get("action", ""),
            target_repo=p_data.get("target_repo", ""),
            ownership=p_data.get("ownership", "self"),
            motivation=p_data.get("motivation", ""),
            observation_id=p_data.get("observation_id", ""),
            complexity=p_data.get("complexity", "medium"),
            verification=p_data.get("verification"),
        )
        save_proposal(proposal, proposals_dir)
        v = proposal.get("verification", {})
        target = p_data.get("target_system", "project")
        confidence = v.get("confidence", "?")

        click.echo(f"  {i}. [{confidence}] [{target}] {proposal['type']}")
        click.echo(f"     {proposal['action']}")
        click.echo(f"     Target: {proposal['target_repo']}")
        click.echo(f"     Motivation: {proposal['motivation'][:120]}")
        if v.get("test_description"):
            click.echo(f"     Verify: {v['test_description']}")
        if v.get("expected_outcome"):
            click.echo(f"     Expected: {v['expected_outcome'][:120]}")
        click.echo()

    click.echo(f"STATUS: DONE {len(saved)}-observations {len(proposals_raw)}-proposals")
    sys.stdout.flush()


@main.command("serve")
@click.option("--port", default=8484, type=int, help="Port to serve on")
def serve(port):
    """Start the transcript browser web UI."""
    state_dir = ensure_canopy_dir()
    projects_dir = Path.home() / ".claude" / "projects"

    try:
        registry_path = find_registry()
    except click.ClickException:
        raise

    run_server(
        projects_dir=projects_dir,
        state_dir=state_dir,
        registry_path=registry_path,
        port=port,
    )


@main.command("brief")
@click.option("--model", default="sonnet", help="Model to use for brief generation")
@click.option("--budget", default=1.0, type=float, help="Max USD per claude -p call")
def brief(model, budget):
    """Generate a strategic brief from recent activity."""
    from orchestrator.briefing import generate_brief

    state_dir = ensure_canopy_dir()

    # brief can run without registry (falls back to simple digest), unlike improve which requires it
    try:
        registry_path = find_registry()
    except click.ClickException:
        registry_path = None

    click.echo(generate_brief(
        state_dir=state_dir,
        registry_path=registry_path,
        model=model,
        max_budget_usd=budget,
    ))


@main.group("test-audit")
def test_audit():
    """Test-audit tools: build a corpus for the agent to judge, then apply verdicts."""


@test_audit.command("collect")
@click.argument("repo", type=click.Path(exists=True, file_okay=False, path_type=Path),
                default=".")
@click.option("--no-run", is_flag=True,
              help="Skip pytest; static analysis only.")
@click.option("--reruns", type=int, default=0,
              help="Run the suite N extra times for flake detection (default: 0).")
def test_audit_collect(repo, no_run, reruns):
    """Build the audit corpus (test inventory + source + runtime) for an agent to read."""
    from orchestrator.test_audit import collect_corpus

    result = collect_corpus(Path(repo), run_tests=not no_run, reruns=reruns)
    click.echo(f"corpus: {result.corpus_path}")
    click.echo(f"stamp_dir: {result.stamp_dir}")
    click.echo(f"test_count: {result.test_count}")
    click.echo(f"ran_pytest: {result.ran_pytest}")


@test_audit.command("apply")
@click.argument("stamp_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--repo", type=click.Path(exists=True, file_okay=False, path_type=Path),
              default=None,
              help="Repo root (default: infer from stamp_dir).")
@click.option("--aggressive", is_flag=True,
              help="Apply prunes with score 4-6 too. Default: only score 0-3.")
@click.option("--dry-run", is_flag=True,
              help="Plan changes but don't write or open a PR.")
def test_audit_apply(stamp_dir, repo, aggressive, dry_run):
    """Read <stamp_dir>/verdicts.yaml and apply (delete/skip) + open a PR."""
    from orchestrator.test_audit import apply_audit, render_apply_summary

    result = apply_audit(Path(stamp_dir), repo=Path(repo) if repo else None,
                         aggressive=aggressive, dry_run=dry_run)
    click.echo(render_apply_summary(result))


@main.command("patterns")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def patterns_cmd(as_json):
    """Show cross-session friction patterns."""
    import json as json_mod
    from orchestrator.patterns import detect_patterns

    state_dir = ensure_canopy_dir()
    obs_dir = state_dir / "observations"

    results = detect_patterns(obs_dir)

    if as_json:
        click.echo(json_mod.dumps(results, indent=2, default=str))
        return

    if not results:
        click.echo("No patterns detected. Run `canopy improve` to analyze sessions first.")
        return

    recurring = [p for p in results if p["type"] == "recurring_issue"]
    hotspots = [p for p in results if p["type"] == "project_hotspot"]

    if recurring:
        click.echo("Recurring Issues:\n")
        for p in recurring:
            servers = ", ".join(p["related_servers"]) if p["related_servers"] else "general"
            click.echo(f"  [{p['severity']}] {p['issue_type']} — {servers}")
            click.echo(f"    Seen {p['total_frequency']}x across {p['unique_sessions']} sessions ({p['observation_count']} observations)")
            for desc in p.get("descriptions", [])[:2]:
                click.echo(f"    - {desc[:80]}")
            click.echo()

    if hotspots:
        click.echo("Project Hotspots:\n")
        for p in hotspots:
            high = f" ({p['high_severity_count']} high)" if p["high_severity_count"] else ""
            click.echo(f"  {p['server']}: {p['issue_count']} issues{high}")
        click.echo()


@main.command("portfolio-discover")
@click.option("--max-age-days", default=30, type=int,
              help="How recent the latest commit must be to count as 'active'")
@click.option("--json-output", "as_json", is_flag=True,
              help="Emit JSON for skill consumption")
@click.option("--api-url", default=None,
              help="Override the canopy-web API base URL (default: $CANOPY_WEB_API_URL or the prod URL)")
def portfolio_discover_cmd(max_age_days, as_json, api_url):
    """List local emdash repos with recent activity that aren't yet curated on canopy-web.

    Closes the gap where a freshly-created project (e.g. expense-helper) stays
    invisible to the canopy portfolio feed until manually registered. Scans
    ~/emdash/{worktrees,repositories} and ~/emdash-projects, asks canopy-web
    which slugs are already curated, and prints the difference.
    """
    import json as json_mod
    import os
    from orchestrator.portfolio_discover import (
        discover_active_repos, fetch_curated_slugs, diff_against_curated,
    )

    active = discover_active_repos(max_age_days=max_age_days)

    base_url = api_url or os.environ.get(
        "CANOPY_WEB_API_URL",
        "https://canopy-web-ujpz2cuyxq-uc.a.run.app",
    )
    token_file = Path.home() / ".claude" / "canopy" / "workbench-token"
    curated: set = set()
    curated_reachable = False
    if token_file.exists() and token_file.read_text().strip():
        curated = fetch_curated_slugs(base_url, token_file.read_text().strip())
        curated_reachable = bool(curated) or True  # we tried; empty means none curated, not unreachable
        # but treat URLError → empty set as "unreachable"; the fetch helper
        # returns set() for both "no projects" and "couldn't reach" — accept the
        # ambiguity, the user gets useful output either way.

    candidates = diff_against_curated(active, curated)

    if as_json:
        click.echo(json_mod.dumps(
            {
                "active_count": len(active),
                "curated_count": len(curated),
                "candidates": candidates,
            },
            indent=2,
        ))
        return

    if not active:
        click.echo("No active git repos found under emdash roots.")
        return

    click.echo(
        f"Found {len(active)} repos with commits in the last {max_age_days} days; "
        f"{len(curated)} are already curated on canopy-web."
    )
    if not candidates:
        click.echo("All active repos are already curated. Nothing to register.")
        return

    click.echo()
    click.echo(f"Candidates not yet curated ({len(candidates)}):")
    for c in candidates:
        ts_short = c["last_commit"][:10]
        click.echo(f"  [{ts_short}]  {c['slug']:30}  {c['path']}")
    click.echo()
    click.echo(f"Register a project at: {base_url.rstrip('/')}/admin/")


@main.group()
def version():
    """VERSION coordination across worktrees."""


@version.command("verify")
@click.option("--repo", default=None, type=click.Path(exists=True, file_okay=False),
              help="Repo root (defaults to current working directory)")
def version_verify(repo):
    """Verify VERSION and plugin.json agree on the current version."""
    from orchestrator.version_bump import verify
    repo_root = Path(repo) if repo else Path.cwd()
    try:
        matches, v, p = verify(repo_root)
    except FileNotFoundError as e:
        raise click.ClickException(str(e))
    if matches:
        click.echo(f"OK: VERSION and plugin.json both at v{v}")
    else:
        click.echo(f"MISMATCH: VERSION={v}  plugin.json={p}", err=True)
        raise click.exceptions.Exit(1)


@version.command("bump")
@click.option("--repo", default=None, type=click.Path(exists=True, file_okay=False),
              help="Repo root (defaults to current working directory)")
def version_bump(repo):
    """Bump VERSION + plugin.json by max(local, origin/main) + patch+1.

    Fetches origin/main first so a parallel worktree's bump is visible before
    deciding the next number. Solves the recurring "two worktrees both bumped
    to the same number" friction.
    """
    from orchestrator.version_bump import bump
    repo_root = Path(repo) if repo else Path.cwd()
    try:
        result = bump(repo_root)
    except (FileNotFoundError, ValueError) as e:
        raise click.ClickException(str(e))

    prev = result["previous_local"]
    origin = result["origin_main"]
    new = result["new_version"]
    origin_str = origin or "(unreachable)"
    click.echo(f"Bumped to v{new}")
    click.echo(f"  was: local=v{prev}  origin/main=v{origin_str}")
    click.echo(f"  wrote: {result['version_path']}")
    click.echo(f"  wrote: {result['plugin_json_path']}")


@main.group()
def skills():
    """Inspect installed skills (plugin + user)."""


@skills.command("list")
@click.option("--scope", type=click.Choice(["all", "plugin", "user"]), default="all")
@click.option("--source", default=None, help="Filter by plugin name (e.g. 'canopy', 'ace')")
@click.option("--search", default=None, help="Filter by substring in name or description")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def skills_list(scope, source, search, as_json):
    """List skills available across plugin and user scopes."""
    import json as json_mod
    from orchestrator.skill_catalog import build_catalog

    catalog = build_catalog()
    if scope != "all":
        catalog = [e for e in catalog if e["scope"] == scope]
    if source:
        catalog = [e for e in catalog if e["source"] == source]
    if search:
        s = search.lower()
        catalog = [e for e in catalog if s in e["name"].lower() or s in (e["description"] or "").lower()]

    if as_json:
        click.echo(json_mod.dumps(catalog, indent=2, default=str))
        return

    if not catalog:
        click.echo("No skills match the given filters.")
        return

    click.echo(f"{len(catalog)} skill(s):\n")
    for e in catalog:
        desc = (e.get("description") or "").replace("\n", " ")
        if len(desc) > 80:
            desc = desc[:77] + "..."
        click.echo(f"  {e['qualified']:<45} [{e['scope']}]")
        if desc:
            click.echo(f"    {desc}")


@skills.command("find")
@click.argument("query", nargs=-1, required=True)
@click.option("--limit", default=5, type=int, help="Maximum matches to display")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def skills_find(query, limit, as_json):
    """Fuzzy-match installed skills by name and description.

    Useful for the "do we already have a skill for X?" check before proposing
    or building a new one.
    """
    import json as json_mod
    from orchestrator.skill_catalog import build_catalog, find_skills

    text = " ".join(query)
    catalog = build_catalog()
    matches = find_skills(text, catalog, limit=limit)

    if as_json:
        click.echo(json_mod.dumps(matches, indent=2, default=str))
        return

    if not matches:
        click.echo(f"No skills match '{text}'.")
        return

    click.echo(f"{len(matches)} match(es) for '{text}':\n")
    for e in matches:
        desc = (e.get("description") or "").replace("\n", " ")
        if len(desc) > 80:
            desc = desc[:77] + "..."
        click.echo(f"  {e['qualified']:<45} [{e['scope']}]")
        if desc:
            click.echo(f"    {desc}")
        click.echo(f"    {e['path']}")


@skills.command("overlap")
@click.argument("action_text", nargs=-1, required=True)
def skills_overlap(action_text):
    """Check whether a proposed skill action overlaps with an existing skill."""
    from orchestrator.skill_catalog import build_catalog, find_overlap, extract_candidate_names

    text = " ".join(action_text)
    catalog = build_catalog()
    match = find_overlap(text, catalog)
    if match:
        click.echo(f"OVERLAP: {match['qualified']} ({match['scope']})")
        if match.get("description"):
            click.echo(f"  {match['description']}")
        click.echo(f"  {match['path']}")
        raise click.exceptions.Exit(1)
    click.echo("No overlap detected.")
    candidates = extract_candidate_names(text)
    if candidates:
        click.echo(f"  Candidates examined: {', '.join(candidates[:8])}")


@main.group()
def observations():
    """Inspect saved observations."""


@observations.command("list")
@click.option("--type", "obs_type", default=None, help="Filter by observation type (friction, gap, etc.)")
@click.option("--status", default=None, help="Filter by status (pending, addressed, etc.)")
@click.option("--severity", default=None, help="Filter by severity (low, medium, high)")
@click.option("--limit", default=20, type=int, help="Maximum rows to display")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def observations_list(obs_type, status, severity, limit, as_json):
    """List observations with optional filters."""
    import json as json_mod
    from orchestrator.observations import list_observations

    state_dir = ensure_canopy_dir()
    obs_dir = state_dir / "observations"
    rows = list_observations(obs_dir, obs_type=obs_type, status=status)
    if severity:
        rows = [o for o in rows if o.get("severity") == severity]
    rows.sort(key=lambda o: (o.get("created", ""), o.get("frequency", 0)), reverse=True)
    rows = rows[:limit]

    if as_json:
        click.echo(json_mod.dumps(rows, indent=2, default=str))
        return

    if not rows:
        click.echo("No observations match the given filters.")
        return

    click.echo(f"{len(rows)} observation(s):\n")
    for o in rows:
        sev = o.get("severity", "?")
        otype = o.get("type", "?")
        st = o.get("status", "?")
        freq = o.get("frequency", 1)
        desc = (o.get("description") or "").replace("\n", " ")
        if len(desc) > 100:
            desc = desc[:97] + "..."
        click.echo(f"  {o['id']}  [{sev}] [{otype}] [{st}]  freq={freq}")
        click.echo(f"    {desc}")


@observations.command("show")
@click.argument("obs_id")
def observations_show(obs_id):
    """Show full YAML for a single observation by id (or id prefix)."""
    state_dir = ensure_canopy_dir()
    obs_dir = state_dir / "observations"
    matches = sorted(obs_dir.glob(f"{obs_id}*.yaml"))
    if not matches:
        raise click.ClickException(f"No observation found matching id '{obs_id}'")
    if len(matches) > 1:
        click.echo(f"Multiple matches for '{obs_id}':", err=True)
        for m in matches:
            click.echo(f"  {m.stem}", err=True)
        raise click.ClickException("Specify a more unique id prefix.")
    click.echo(matches[0].read_text())


@main.group()
def proposals():
    """Inspect saved proposals."""


@proposals.command("list")
@click.option("--status", default=None, help="Filter by status (pending, implemented, failed)")
@click.option("--complexity", default=None, help="Filter by complexity (low, medium, high)")
@click.option("--limit", default=20, type=int, help="Maximum rows to display")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def proposals_list(status, complexity, limit, as_json):
    """List proposals with optional filters."""
    import json as json_mod
    from orchestrator.proposals import list_proposals

    state_dir = ensure_canopy_dir()
    proposals_dir = state_dir / "proposals"
    rows = list_proposals(proposals_dir, status=status)
    if complexity:
        rows = [p for p in rows if p.get("complexity") == complexity]
    rows.sort(key=lambda p: p.get("created", ""), reverse=True)
    rows = rows[:limit]

    if as_json:
        click.echo(json_mod.dumps(rows, indent=2, default=str))
        return

    if not rows:
        click.echo("No proposals match the given filters.")
        return

    click.echo(f"{len(rows)} proposal(s):\n")
    for p in rows:
        ptype = p.get("type", "?")
        st = p.get("status", "?")
        cx = p.get("complexity", "?")
        conf = (p.get("verification") or {}).get("confidence", "?")
        action = (p.get("action") or "").replace("\n", " ")
        if len(action) > 100:
            action = action[:97] + "..."
        click.echo(f"  {p['id']}  [{st}] [{ptype}] complexity={cx} conf={conf}")
        click.echo(f"    {action}")
        target = p.get("target_repo")
        if target:
            click.echo(f"    target: {target}")


@proposals.command("show")
@click.argument("proposal_id")
def proposals_show(proposal_id):
    """Show full YAML for a single proposal by id (or id prefix)."""
    state_dir = ensure_canopy_dir()
    proposals_dir = state_dir / "proposals"
    matches = sorted(proposals_dir.glob(f"{proposal_id}*.yaml"))
    if not matches:
        raise click.ClickException(f"No proposal found matching id '{proposal_id}'")
    if len(matches) > 1:
        click.echo(f"Multiple matches for '{proposal_id}':", err=True)
        for m in matches:
            click.echo(f"  {m.stem}", err=True)
        raise click.ClickException("Specify a more unique id prefix.")
    click.echo(matches[0].read_text())


def _validate_proposals(
    proposals: list[dict],
    registry: dict,
    skill_catalog: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Validate and fix proposals against the registry and skill catalog.

    Returns `(kept, dropped)`. Each dropped proposal has `_dropped` set to a
    human-readable reason; callers can surface this so users see what was
    filtered out and why.

    - Fix target_repo mismatches (e.g., tool for connect-search proposed for connect-labs)
    - Drop proposals for tools that already exist
    - Drop `new_skill` proposals that overlap with an existing skill
    """
    from orchestrator.registry import get_all_servers, get_all_tools
    from orchestrator.skill_catalog import find_overlap

    servers = get_all_servers(registry)
    all_tools = get_all_tools(registry)
    existing_tool_names = {t["name"] for t in all_tools}
    catalog = skill_catalog or []

    kept: list[dict] = []
    dropped: list[dict] = []
    for p in proposals:
        action = p.get("action", "")
        action_lc = action.lower()
        ptype = p.get("type", "")
        target_repo = p.get("target_repo", "")

        # Fix target_repo: if the action mentions a specific server, use that server's repo
        for server in servers:
            server_name = server["name"]
            if server_name in action_lc or server_name.replace("-", "_") in action_lc:
                correct_repo = server.get("repo", "")
                if correct_repo and correct_repo != target_repo:
                    p["target_repo"] = correct_repo
                    p["_fixed"] = f"target_repo corrected from {target_repo} to {correct_repo}"
                break

        # Drop proposals for tools that already exist
        if ptype == "new_tool":
            for tool_name in existing_tool_names:
                if tool_name in action_lc and f"add a `{tool_name}`" in action_lc:
                    p["_dropped"] = f"tool {tool_name} already exists"
                    break
            if "_dropped" in p:
                dropped.append(p)
                continue

        # Drop new_skill proposals that overlap with an existing skill
        if ptype == "new_skill" and catalog:
            overlap = find_overlap(action, catalog)
            if overlap:
                p["_dropped"] = f"skill {overlap['qualified']} already exists"
                dropped.append(p)
                continue

        kept.append(p)

    return kept, dropped


def _print_cycle_result(result: dict) -> None:
    click.echo()
    click.echo(f"Transcripts analyzed: {result.get('transcripts_analyzed', 0)}")
    click.echo(f"Observations created: {result.get('observations_created', 0)}")
    click.echo(f"Observations merged:  {result.get('observations_merged', 0)}")
    click.echo(f"Proposals generated:  {result.get('proposals_generated', 0)}")
    click.echo()
    click.echo("Implementation is handled by /canopy:improve skill agents.")

    if result.get("errors"):
        click.echo()
        click.echo("Errors:")
        for err in result["errors"]:
            click.echo(f"  - {err}")
