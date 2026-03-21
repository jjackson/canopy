"""CLI entry point for the orchestrator."""

from pathlib import Path
import click
from orchestrator.registry import (
    load_registry, get_all_servers, get_all_tools, get_workflows,
    format_for_skill, RegistryError,
)
from orchestrator.capture import read_session_log, group_by_session, classify_sessions
from orchestrator.pipeline import run_cycle, CycleConfig


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
    """Orchestrator — self-improving MCP orchestration."""


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

    proposals_dir = state_dir / "proposals"
    click.echo(f"Generated {len(proposals_raw)} proposals:")
    click.echo()
    for p_data in proposals_raw:
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
        click.echo(f"  [{v.get('confidence', '?')}] {proposal['action'][:80]}")
        if v.get("test_description"):
            click.echo(f"       verify: {v['test_description'][:90]}")


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
