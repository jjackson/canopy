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
@click.option("--min-turns", default=0, type=int,
              help="Drop sessions with fewer than N user messages — useful for "
                   "filtering trivial/empty sessions out of session-review batches "
                   "where each analyzed session costs an LLM call.")
def sessions_list(hours, as_json, project, min_turns):
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

    # Drop trivial sessions before they reach LLM-driven analysis. A 2026-05-02
    # session-review run wasted ~2 min on 4 sessions that returned 0 observations
    # because they were too short to contain meaningful friction signal. Use
    # --min-turns ~5 to skip these in batch contexts.
    if min_turns > 0:
        recent = [s for s in recent if s.get("user_msgs", 0) >= min_turns]

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
        # Distinguish "proposer ran cleanly with nothing to suggest" from "the
        # proposer's claude -p call broke" — the agent's salvage logic
        # (session-review.md Step 5b) needs to know which case it is so it
        # can hand-craft proposals from the saved observations rather than
        # silently dropping them. The actual failure detail was already
        # printed to stderr by generate_proposals().
        click.echo(
            "WARN: proposer returned no proposals — see stderr for whether "
            "it was a parse error or genuinely no-suggestions. "
            f"The {len(saved)} observation(s) above are saved and can be "
            "promoted to findings by hand if proposer parse-errored."
        )
        click.echo(f"STATUS: DONE {len(saved)}-observations 0-proposals proposer-empty")
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


@main.group("shareout")
def shareout_group():
    """Team work-briefing commands — gather a date range and post to canopy-web."""


@shareout_group.command("gather")
@click.option("--from", "from_date", default=None, help="Start date YYYY-MM-DD")
@click.option("--to", "to_date", default=None, help="End date YYYY-MM-DD")
@click.option("--days", default=None, type=int, help="Last N full days ending yesterday")
@click.option("--project", default=None,
              help="Filter to sessions whose resolved repo ends with /<name>")
@click.option("--author", default="@me", help="GitHub PR author (default: @me)")
@click.option("--api-url", default=None,
              help="canopy-web base URL (used to find the last shareout for the default window)")
@click.option("--json-out", "json_out", default=None,
              help="Write corpus JSON to this path instead of stdout")
def shareout_gather(from_date, to_date, days, project, author, api_url, json_out):
    """Gather sessions + the author's PRs per project for a date range.

    With no --from/--to/--days, the window runs from the end of the most recent
    existing shareout up to today (the gap since the last one). If no shareout
    exists yet — or canopy-web is unreachable — it falls back to yesterday.
    """
    import datetime as dt
    import json as json_mod
    import os

    from orchestrator import shareout as shareout_mod
    from orchestrator.repo_map import load_repo_map
    from orchestrator.labels import load_labels

    projects_dir = Path.home() / ".claude" / "projects"
    state_dir = ensure_canopy_dir()
    repo_map = load_repo_map(state_dir / "repo-map.json")
    labels = load_labels(state_dir / "labels.yaml")

    if not (from_date or to_date or days):
        # Incremental default: continue from where the last shareout left off.
        api = api_url or os.environ.get("CANOPY_WEB_API_URL", shareout_mod.DEFAULT_API)
        token = shareout_mod.resolve_pat()
        latest_end = shareout_mod.fetch_latest_period_end(api, token) if token else None
        start, end = shareout_mod.resolve_default_range(latest_end)
    else:
        start, end = shareout_mod.resolve_range(from_date, to_date, days)
    corpus = shareout_mod.gather(
        projects_dir=projects_dir,
        repo_map=repo_map,
        labels=labels,
        start=start,
        end=end,
        author=author,
        project_filter=project,
    )
    out = json_mod.dumps(corpus, indent=2, default=str)
    if json_out:
        Path(json_out).write_text(out)
        click.echo(f"Wrote corpus for {start}..{end} "
                   f"({len(corpus['projects'])} projects) to {json_out}")
    else:
        click.echo(out)


@shareout_group.command("post")
@click.argument("authoring_json", type=click.Path(exists=True))
@click.option("--corpus", "corpus_json", default=None, type=click.Path(exists=True),
              help="gather corpus JSON — auto-fills each project's all_prs (full PR list)")
@click.option("--source", "source_override", default=None,
              help="Override the source tag. Reuse a prior run's source to REPLACE its "
                   "rows (idempotency is keyed on project+period+source) instead of "
                   "appending a fresh timestamped set.")
@click.option("--api-url", default=None,
              help="canopy-web base URL (default: $CANOPY_WEB_API_URL or prod)")
def shareout_post(authoring_json, corpus_json, source_override, api_url):
    """Post an authored briefings doc to the canopy-web /shareouts feed."""
    import datetime as dt
    import json as json_mod
    import os

    from orchestrator import shareout as shareout_mod

    api = api_url or os.environ.get("CANOPY_WEB_API_URL", shareout_mod.DEFAULT_API)
    token = shareout_mod.resolve_pat()
    if not token:
        raise click.ClickException(
            "no canopy-web PAT — run /canopy:canopy-web-pat-mint or set CANOPY_WEB_PAT"
        )

    authoring = json_mod.loads(Path(authoring_json).read_text())
    if corpus_json:
        corpus = json_mod.loads(Path(corpus_json).read_text())
        shareout_mod.fill_all_prs_from_corpus(authoring, corpus)
    source = source_override or f"canopy:shareout@{dt.datetime.now(dt.timezone.utc).isoformat()}"
    payload = shareout_mod.build_post_payload(authoring, source=source)

    status, body = shareout_mod.post(payload, api, token)
    if status not in (200, 201):
        raise click.ClickException(f"post failed ({status}): {body}")
    click.echo(f"Posted {body.get('created', 0)} briefing(s) "
               f"(replaced {body.get('replaced', 0)}, skipped {body.get('skipped', 0)}).")
    click.echo(f"View: {shareout_mod.feed_url(api)}")


@shareout_group.command("clear")
@click.option("--source", default=None, help="Delete shareouts with this exact source tag")
@click.option("--project", default=None, help="Delete shareouts for this project slug")
@click.option("--from", "date_from", default=None, help="period_end on/after YYYY-MM-DD")
@click.option("--to", "date_to", default=None, help="period_start on/before YYYY-MM-DD")
@click.option("--all", "clear_all", is_flag=True, help="Required to delete with no filters")
@click.option("--api-url", default=None, help="canopy-web base URL")
def shareout_clear(source, project, date_from, date_to, clear_all, api_url):
    """Delete shareouts from the canopy-web feed (filters AND-combine)."""
    import os

    from orchestrator import shareout as shareout_mod

    filters = {k: v for k, v in {
        "source": source, "project": project, "date_from": date_from, "date_to": date_to,
    }.items() if v}
    if not filters and not clear_all:
        raise click.ClickException("refusing to clear ALL shareouts without --all")

    api = api_url or os.environ.get("CANOPY_WEB_API_URL", shareout_mod.DEFAULT_API)
    token = shareout_mod.resolve_pat()
    if not token:
        raise click.ClickException("no canopy-web PAT — run /canopy:canopy-web-pat-mint")
    status, body = shareout_mod.clear(filters, api, token)
    if status != 200:
        raise click.ClickException(f"clear failed ({status}): {body}")
    click.echo(f"Cleared {body.get('cleared', 0)} shareout row(s).")


@main.group("test-audit")
def test_audit():
    """Test-audit tools: build a corpus for the agent to judge, then apply verdicts."""


@test_audit.command("collect")
@click.argument("repo", type=click.Path(exists=True, file_okay=False, path_type=Path),
                default=".")
@click.option("--no-run", is_flag=True,
              help="Skip the test runner; static analysis only.")
@click.option("--reruns", type=int, default=0,
              help="Run the suite N extra times for flake detection (default: 0).")
@click.option("--framework", type=click.Choice(["auto", "pytest", "vitest"]),
              default="auto", show_default=True,
              help="Override framework detection.")
@click.option("--source-roots", "source_roots", default=None,
              help="Comma-separated list of repo-relative source directories "
                   "to scan for the module inventory (e.g. 'lib,mcp'). "
                   "Defaults to the framework's conventional layout.")
def test_audit_collect(repo, no_run, reruns, framework, source_roots):
    """Build the audit corpus (test inventory + source + runtime) for an agent to read."""
    from orchestrator.test_audit import collect_corpus

    fw = None if framework == "auto" else framework
    roots = [r.strip() for r in source_roots.split(",")] if source_roots else None
    if roots:
        roots = [r for r in roots if r]
    result = collect_corpus(Path(repo), run_tests=not no_run, reruns=reruns,
                            framework=fw, source_roots=roots)
    click.echo(f"corpus: {result.corpus_path}")
    click.echo(f"stamp_dir: {result.stamp_dir}")
    click.echo(f"framework: {result.framework}")
    click.echo(f"test_count: {result.test_count}")
    click.echo(f"ran_tests: {result.ran_tests}")


@test_audit.command("apply")
@click.argument("stamp_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--repo", type=click.Path(exists=True, file_okay=False, path_type=Path),
              default=None,
              help="Repo root (default: infer from stamp_dir).")
@click.option("--aggressive", is_flag=True,
              help="Apply prunes with score 4-6 too. Default: only score 0-3.")
@click.option("--dry-run", is_flag=True,
              help="Plan changes but don't write or open a PR.")
@click.option("--framework", type=click.Choice(["auto", "pytest", "vitest"]),
              default="auto", show_default=True,
              help="Override framework detection (default: read from corpus.yaml).")
def test_audit_apply(stamp_dir, repo, aggressive, dry_run, framework):
    """Read <stamp_dir>/verdicts.yaml and apply (delete/skip) + open a PR."""
    from orchestrator.test_audit import apply_audit, render_apply_summary

    fw = None if framework == "auto" else framework
    result = apply_audit(Path(stamp_dir), repo=Path(repo) if repo else None,
                         aggressive=aggressive, dry_run=dry_run, framework=fw)
    click.echo(render_apply_summary(result))


@main.command("doctor")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def doctor_cmd(as_json):
    """Diagnose canopy plugin health.

    Runs read-only checks — hook registration, session log, repo map,
    workbench token, plugin version. Exits non-zero if any check fails so it
    can gate CI.
    """
    import json as json_mod
    from orchestrator.doctor import run_doctor

    results, overall_ok = run_doctor()

    if as_json:
        click.echo(json_mod.dumps(
            {
                "ok": overall_ok,
                "checks": [r.to_dict() for r in results],
            },
            indent=2,
        ))
    else:
        width = max(len(r.name) for r in results)
        for r in results:
            status = "OK  " if r.ok else "FAIL"
            click.echo(f"  [{status}] {r.name.ljust(width)}  {r.detail}")
        click.echo()
        if overall_ok:
            click.echo("All checks passed — canopy is healthy.")
        else:
            click.echo("Some checks failed — see details above.")

    if not overall_ok:
        raise click.exceptions.Exit(1)


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


@main.command("verify-findings")
@click.argument("id_prefixes", nargs=-1)
@click.option("--all-pending", is_flag=True,
              help="Verify every proposal whose status is currently `pending`.")
@click.option("--json-output", "as_json", is_flag=True,
              help="Emit JSON for skill consumption (no triage table).")
@click.option("--model", default="sonnet",
              help="Model for the verdict LLM call.")
@click.option("--budget", default=0.50, type=float,
              help="Max USD per claude -p call.")
def verify_findings_cmd(id_prefixes, all_pending, as_json, model, budget):
    """Re-verify session-review proposals against the current state of their target repos.

    Drops proposals whose fix already shipped (flips status to `obsolete`)
    and surfaces a triage table with one verdict per proposal:
    shipped / partial / open / unverifiable. Caller passes proposal-id
    prefixes (8+ chars each) or --all-pending.
    """
    import json as json_mod
    from orchestrator.verify_findings import verify

    if not id_prefixes and not all_pending:
        raise click.UsageError(
            "pass at least one proposal-id prefix, or --all-pending."
        )

    result = verify(
        id_prefixes=list(id_prefixes) if id_prefixes else None,
        all_pending=all_pending,
        model=model,
        max_budget_usd=budget,
    )

    if as_json:
        # Drop internal _path before emitting — callers don't need it.
        for v in result["verdicts"]:
            v.pop("_path", None)
        click.echo(json_mod.dumps(result, indent=2, default=str))
        return

    summary = result["summary"]
    if not result["verdicts"]:
        click.echo("No proposals matched. Pass id-prefixes or --all-pending.")
        return

    click.echo(
        f"verify-findings: {summary['shipped']} shipped · "
        f"{summary['partial']} partial · {summary['open']} open · "
        f"{summary['unverifiable']} unverifiable "
        f"(of {summary['total']})"
    )
    click.echo()

    # Triage table
    click.echo(
        f"{'status':<14} {'id':<14} {'evidence':<60}"
    )
    click.echo("-" * 90)
    for v in result["verdicts"]:
        verdict = (v.get("verdict") or "")[:13]
        pid = (v.get("id") or "")[:13]
        evidence = (v.get("evidence") or "")[:60]
        click.echo(f"{verdict:<14} {pid:<14} {evidence:<60}")


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


@version.command("verify-bump")
@click.option("--repo", default=None, type=click.Path(exists=True, file_okay=False),
              help="Repo root (defaults to current working directory)")
@click.option("--base-ref", default="origin/main",
              help="Base ref to compare against (default: origin/main)")
def version_verify_bump(repo, base_ref):
    """Fail if plugins/canopy/ changed without a VERSION bump on this branch.

    The check that catches the discipline failure CLAUDE.md flags as the #1
    canopy mistake — merging plugin asset changes without bumping VERSION,
    which makes `/canopy:update` silently report UP_TO_DATE and leaves
    every existing session stuck on the old cache.
    """
    from orchestrator.version_bump import verify_bump_when_plugin_changed

    repo_root = Path(repo) if repo else Path.cwd()
    try:
        result = verify_bump_when_plugin_changed(repo_root, base_ref=base_ref)
    except FileNotFoundError as e:
        raise click.ClickException(str(e))

    click.echo(result["reason"])
    if result["plugin_files_changed"]:
        click.echo(f"\nPlugin files changed on this branch ({len(result['plugin_files_changed'])}):")
        for p in result["plugin_files_changed"]:
            click.echo(f"  {p}")
    if result["main_version"] and result["local_version"]:
        click.echo(f"\nbase {result['base_ref']} VERSION: {result['main_version']}")
        click.echo(f"branch HEAD VERSION:    {result['local_version']}")
    if result["ok"]:
        return
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
    mp_path = result.get("marketplace_json_path")
    mp_n = result.get("marketplace_json_replacements", 0)
    if mp_path and mp_n:
        click.echo(f"  wrote: {mp_path} ({mp_n} version field{'s' if mp_n != 1 else ''})")


@main.command("structure-drift")
@click.option("--repo", default=None, type=click.Path(exists=True, file_okay=False),
              help="Repo root to audit (defaults to the canopy checkout this CLI ships from)")
@click.option("--strict", is_flag=True,
              help="Exit non-zero if any finding exists (CI gate)")
@click.option("--per-skill-limit", default=None, type=int,
              help="Per-skill description char limit (default: 1024)")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def structure_drift_cmd(repo, strict, per_skill_limit, as_json):
    """Self-audit canopy's documented structural invariants in one pass.

    Checks the invariants canopy documents in CLAUDE.md:
      - command/skill collisions follow Pattern B (read SKILL.md from disk)
      - no command/skill/agent uses a reserved built-in slash-command name
      - VERSION == plugin.json version == marketplace.json version field(s)
      - no skill description exceeds the per-skill char budget

    Default: print findings and exit 0. With --strict, exit non-zero when any
    finding exists, so CI can gate on it.
    """
    import json as json_mod
    from orchestrator.structure_drift import run_structure_drift, DEFAULT_PER_SKILL_LIMIT

    repo_root = Path(repo) if repo else None
    psl = per_skill_limit if per_skill_limit is not None else DEFAULT_PER_SKILL_LIMIT

    report = run_structure_drift(repo_root=repo_root, per_skill_limit=psl)

    if as_json:
        click.echo(json_mod.dumps(report, indent=2, default=str))
    else:
        counts = report["counts"]
        if report["ok"]:
            click.echo("OK: no structure drift detected.")
        else:
            click.echo(
                f"DRIFT: {counts['total']} finding(s) — "
                f"{counts['error']} error, {counts['warning']} warning\n"
            )
            for inv, items in report["by_invariant"].items():
                click.echo(f"[{inv}]")
                for f in items:
                    click.echo(f"  {f['severity'].upper()}: {f['detail']}")
                click.echo()

    if strict and not report["ok"]:
        raise click.exceptions.Exit(1)


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
        version = e.get("installed_version")
        version_str = f" v{version}" if version else ""
        click.echo(f"  {e['qualified']:<45} [{e['scope']}]{version_str}")
        if desc:
            click.echo(f"    {desc}")


@skills.command("budget")
@click.option("--scope", type=click.Choice(["all", "plugin", "user"]), default="all")
@click.option("--source", default=None, help="Filter by plugin name (e.g. 'canopy', 'ace')")
@click.option(
    "--per-skill-limit",
    type=int,
    default=None,
    help="Per-skill description char limit (default: 1024)",
)
@click.option(
    "--aggregate-limit",
    type=int,
    default=None,
    help="Aggregate description char limit across all skills (default: 1500)",
)
@click.option(
    "--top",
    type=int,
    default=None,
    help="Show only the top N largest skills (default: all)",
)
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def skills_budget(scope, source, per_skill_limit, aggregate_limit, top, as_json):
    """Show description-size budget for installed skills.

    Reads each skill's frontmatter `description`, ranks by size, and prints
    an aggregate gauge against the configured cap. Useful for diagnosing the
    silent "N skills dropped" message Claude Code shows when the system
    prompt overflows.
    """
    import json as json_mod
    from orchestrator.skill_catalog import build_catalog
    from orchestrator.skill_budget import (
        DEFAULT_AGGREGATE_LIMIT,
        DEFAULT_PER_SKILL_LIMIT,
        rank,
    )

    psl = per_skill_limit if per_skill_limit is not None else DEFAULT_PER_SKILL_LIMIT
    al = aggregate_limit if aggregate_limit is not None else DEFAULT_AGGREGATE_LIMIT

    catalog = build_catalog()
    if scope != "all":
        catalog = [e for e in catalog if e["scope"] == scope]
    if source:
        catalog = [e for e in catalog if e["source"] == source]

    ranked = rank(catalog)
    if top is not None and top > 0:
        ranked = ranked[:top]

    aggregate_used = sum(min(e["description_size"], psl) for e in ranked)
    over_count = sum(1 for e in ranked if e["description_size"] > psl)

    if as_json:
        click.echo(json_mod.dumps({
            "totals": {
                "skills_total": len(ranked),
                "aggregate_used": aggregate_used,
                "aggregate_limit": al,
                "per_skill_limit": psl,
                "per_skill_over": over_count,
            },
            "skills": ranked,
        }, indent=2, default=str))
        return

    if not ranked:
        click.echo("No skills match the given filters.")
        return

    click.echo(f"{len(ranked)} skill(s) — per-skill cap {psl} chars, aggregate cap {al} chars\n")
    click.echo(f"  {'STATUS':<5}  {'SIZE':>5}  {'KIND':<8}  {'NAME':<48}")
    for e in ranked:
        click.echo(
            f"  {e['per_skill_status']:<5}  {e['description_size']:>5}  "
            f"{(e.get('kind') or 'skill'):<8}  {e['qualified']}"
        )

    pct = (aggregate_used / al * 100) if al else 0
    click.echo()
    click.echo(
        f"  AGGREGATE: {aggregate_used}/{al} chars ({pct:.0f}%)  •  "
        f"{over_count} over per-skill cap"
    )
    if aggregate_used > al:
        click.echo("  ⚠ aggregate exceeds cap — run `canopy skills dropped` to see which skills get dropped")


@skills.command("dropped")
@click.option("--scope", type=click.Choice(["all", "plugin", "user"]), default="all")
@click.option("--source", default=None, help="Filter by plugin name (e.g. 'canopy', 'ace')")
@click.option(
    "--per-skill-limit",
    type=int,
    default=None,
    help="Per-skill description char limit (default: 1024)",
)
@click.option(
    "--aggregate-limit",
    type=int,
    default=None,
    help="Aggregate description char limit across all skills (default: 1500)",
)
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def skills_dropped(scope, source, per_skill_limit, aggregate_limit, as_json):
    """Simulate which skills Claude Code drops under the aggregate cap.

    Sums per-skill (capped) description sizes in alphabetical-by-qualified
    order and flags any skill whose inclusion would push the running total
    over the aggregate cap.
    """
    import json as json_mod
    from orchestrator.skill_catalog import build_catalog
    from orchestrator.skill_budget import (
        DEFAULT_AGGREGATE_LIMIT,
        DEFAULT_PER_SKILL_LIMIT,
        simulate_drops,
    )

    psl = per_skill_limit if per_skill_limit is not None else DEFAULT_PER_SKILL_LIMIT
    al = aggregate_limit if aggregate_limit is not None else DEFAULT_AGGREGATE_LIMIT

    catalog = build_catalog()
    if scope != "all":
        catalog = [e for e in catalog if e["scope"] == scope]
    if source:
        catalog = [e for e in catalog if e["source"] == source]

    result = simulate_drops(catalog, per_skill_limit=psl, aggregate_limit=al)

    if as_json:
        click.echo(json_mod.dumps(result, indent=2, default=str))
        return

    totals = result["totals"]
    dropped = result["dropped"]
    click.echo(
        f"{totals['kept_count']} kept, {totals['dropped_count']} dropped — "
        f"aggregate {totals['aggregate_used']}/{totals['aggregate_limit']} chars used"
    )
    if not dropped:
        click.echo("\nNo skills dropped under the configured caps.")
        return
    click.echo(f"\nDropped ({len(dropped)}):")
    for e in dropped:
        click.echo(
            f"  {e['qualified']:<48} {e['description_size']:>5} chars  ({e.get('drop_reason', 'aggregate_limit_exceeded')})"
        )


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
