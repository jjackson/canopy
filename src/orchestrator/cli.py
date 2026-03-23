"""CLI entry point for the orchestrator."""

from pathlib import Path
import click
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
def sessions_list(hours, as_json):
    """List recent sessions grouped by project."""
    import json as json_mod
    from datetime import datetime, timezone, timedelta

    from orchestrator.scanner import scan_all_transcripts
    from orchestrator.repo_map import load_repo_map
    from orchestrator.labels import load_labels

    projects_dir = Path.home() / ".claude" / "projects"
    state_dir = Path.home() / ".claude" / "orchestrator"
    repo_map = load_repo_map(state_dir / "repo-map.json")
    labels = load_labels(state_dir / "labels.yaml")

    all_sessions = scan_all_transcripts(projects_dir, repo_map, labels)

    # Filter by recency
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_iso = cutoff.isoformat()
    recent = [s for s in all_sessions if s.get("last_ts") and s["last_ts"] >= cutoff_iso]
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
    log_file = Path.home() / ".claude" / "orchestrator" / "session-log.jsonl"
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
    state_dir = Path.home() / ".claude" / "orchestrator"
    state_dir.mkdir(parents=True, exist_ok=True)

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
    import yaml
    from orchestrator.analyzer import analyze_transcript
    from orchestrator.proposer import generate_proposals
    from orchestrator.observations import create_observation, save_observation
    from orchestrator.proposals import create_proposal, save_proposal

    try:
        registry_path = find_registry()
    except click.ClickException:
        raise

    reg = load_registry(registry_path)
    registry_summary = format_for_skill(reg)

    state_dir = Path.home() / ".claude" / "orchestrator"
    state_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"Analyzing: {transcript}")
    click.echo()

    observations = analyze_transcript(
        Path(transcript), registry_summary, model=model, max_budget_usd=budget,
    )

    if not observations:
        click.echo("No observations found.")
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
        return

    click.echo()
    click.echo("Generating proposals...")
    click.echo()

    proposals_raw = generate_proposals(
        saved, registry_summary, model=model, max_budget_usd=budget,
    )

    if not proposals_raw:
        click.echo("No proposals generated.")
        return

    # Validate and fix proposals against the registry
    proposals_raw = _validate_proposals(proposals_raw, reg)

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


@main.command("serve")
@click.option("--port", default=8484, type=int, help="Port to serve on")
def serve(port):
    """Start the transcript browser web UI."""
    state_dir = Path.home() / ".claude" / "orchestrator"
    state_dir.mkdir(parents=True, exist_ok=True)
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


def _validate_proposals(proposals: list[dict], registry: dict) -> list[dict]:
    """Validate and fix proposals against the registry.

    - Fix target_repo mismatches (e.g., tool for connect-search proposed for connect-labs)
    - Auto-apply canopy registry_update proposals instead of just proposing them
    - Drop proposals for tools that already exist
    """
    from orchestrator.registry import get_all_servers, get_all_tools

    servers = get_all_servers(registry)
    all_tools = get_all_tools(registry)
    existing_tool_names = {t["name"] for t in all_tools}

    # Build server name -> repo mapping
    server_repos = {s["name"]: s.get("repo", "") for s in servers}

    validated = []
    for p in proposals:
        action = p.get("action", "").lower()
        ptype = p.get("type", "")
        target_repo = p.get("target_repo", "")

        # Fix target_repo: if the action mentions a specific server, use that server's repo
        for server in servers:
            server_name = server["name"]
            if server_name in action or server_name.replace("-", "_") in action:
                correct_repo = server.get("repo", "")
                if correct_repo and correct_repo != target_repo:
                    p["target_repo"] = correct_repo
                    p["_fixed"] = f"target_repo corrected from {target_repo} to {correct_repo}"
                break

        # Drop proposals for tools that already exist
        if ptype == "new_tool":
            # Extract proposed tool name from action
            for tool_name in existing_tool_names:
                if tool_name in action and f"add a `{tool_name}`" in action.lower():
                    p["_dropped"] = f"tool {tool_name} already exists"
                    break
            if "_dropped" in p:
                continue

        validated.append(p)

    return validated


def _print_cycle_result(result: dict) -> None:
    click.echo()
    click.echo(f"Transcripts analyzed: {result.get('transcripts_analyzed', 0)}")
    click.echo(f"Observations created: {result.get('observations_created', 0)}")
    click.echo(f"Observations merged:  {result.get('observations_merged', 0)}")
    click.echo(f"Proposals generated:  {result.get('proposals_generated', 0)}")
    click.echo(f"Proposals implemented: {result.get('proposals_implemented', 0)}")
    click.echo(f"Proposals failed:     {result.get('proposals_failed', 0)}")

    if result.get("errors"):
        click.echo()
        click.echo("Errors:")
        for err in result["errors"]:
            click.echo(f"  - {err}")
