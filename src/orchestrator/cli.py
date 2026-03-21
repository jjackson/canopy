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
