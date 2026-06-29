"""`canopy agent …` — thin CLI over AgentClient for shell-driven agents."""
import json
import click

from orchestrator.agent_client import AgentClient, catalog_from_repo, CanopyError


def _client(slug, **identity):
    return AgentClient({"slug": slug, **{k: v for k, v in identity.items() if v}})


def _emit(obj):
    click.echo(json.dumps(obj))


@click.group()
def agent():
    """Talk to canopy-web's agent workspace (/api/agents)."""


@agent.command("register")
@click.option("--slug", required=True)
@click.option("--name", default="")
@click.option("--email", default="")
@click.option("--description", default="")
@click.option("--persona", default="")
@click.option("--avatar-url", default="")
def agent_register(slug, name, email, description, persona, avatar_url):
    """Upsert agent identity."""
    try:
        c = _client(slug, name=name, email=email, description=description,
                    persona=persona, avatar_url=avatar_url)
        _emit(c.register())
    except (CanopyError, RuntimeError) as e:
        raise click.ClickException(str(e))


@agent.command("sync")
@click.option("--slug", required=True)
@click.option("--doc-url", required=True)
@click.option("--title", required=True)
@click.option("--summary", default="")
@click.option("--grades", default="{}", help="JSON object of self-grades")
@click.option("--period-start", required=True)
@click.option("--period-end", required=True)
@click.option("--source", default="manager-sync")
def agent_sync(slug, doc_url, title, summary, grades, period_start, period_end, source):
    """Post a manager sync."""
    try:
        c = _client(slug)
        _emit(c.post_sync(period_start=period_start, period_end=period_end, title=title,
                          summary=summary, doc_url=doc_url, self_grades=json.loads(grades), source=source))
    except (CanopyError, RuntimeError) as e:
        raise click.ClickException(str(e))


@agent.command("work")
@click.option("--slug", required=True)
@click.option("--json", "json_file", required=True, type=click.Path(exists=True),
              help="JSON file: [{title,kind,url,description,tags,source}]")
def agent_work(slug, json_file):
    """Upsert work products from a JSON file."""
    try:
        items = json.load(open(json_file))
        _emit(_client(slug).put_work_products(items))
    except (CanopyError, RuntimeError) as e:
        raise click.ClickException(str(e))


@agent.command("skills")
@click.option("--slug", required=True)
@click.option("--from-repo", "skills_root", type=click.Path(exists=True),
              help="glob <root>/*/SKILL.md into the catalog")
@click.option("--url-template", default="", help="e.g. https://github.com/org/repo/blob/main/skills/{name}/SKILL.md")
@click.option("--json", "json_file", type=click.Path(exists=True), help="explicit catalog JSON")
def agent_skills(slug, skills_root, url_template, json_file):
    """Replace the skill catalog (from a repo glob or a JSON file)."""
    try:
        if skills_root:
            items = catalog_from_repo(skills_root, url_template or "{name}")
        elif json_file:
            items = json.load(open(json_file))
        else:
            raise click.ClickException("pass --from-repo or --json")
        _emit(_client(slug).put_skills(items))
    except (CanopyError, RuntimeError) as e:
        raise click.ClickException(str(e))


@agent.command("tasks-sync")
@click.option("--slug", required=True)
@click.option("--json", "json_file", required=True, type=click.Path(exists=True),
              help="JSON file: [{ext_id,title,next_action,status,owner,assigned,…}]")
def agent_tasks_sync(slug, json_file):
    """Non-destructive task upsert from a JSON file."""
    try:
        tasks = json.load(open(json_file))
        _emit(_client(slug).sync_tasks(tasks))
    except (CanopyError, RuntimeError) as e:
        raise click.ClickException(str(e))


@agent.command("commands")
@click.option("--slug", required=True)
def agent_commands(slug):
    """List board actions queued for the agent (drain on a turn)."""
    try:
        cmds = _client(slug).pending_commands()
    except (CanopyError, RuntimeError) as e:
        raise click.ClickException(str(e))
    if not cmds:
        click.echo("no queued commands")
        return
    for c in cmds:
        click.echo(f"  #{c.id} {c.kind} -> {c.task_title or '(no task)'}  [{c.created_by}]  {c.payload or ''}")


@agent.command("tasks")
@click.option("--slug", required=True)
def agent_tasks(slug):
    """List the agent's board tasks (JSON) — e.g. to compute the next ext_id."""
    try:
        _emit(_client(slug).list_tasks())
    except (CanopyError, RuntimeError) as e:
        raise click.ClickException(str(e))


@agent.command("apply")
@click.option("--slug", required=True)
@click.option("--id", "cmd_id", type=int, required=True)
@click.option("--note", default="")
def agent_apply(slug, cmd_id, note):
    """Mark a queued command applied."""
    try:
        _emit(_client(slug).apply_command(cmd_id, result_note=note))
    except (CanopyError, RuntimeError) as e:
        raise click.ClickException(str(e))


@agent.command("set")
@click.option("--slug", required=True)
@click.option("--task-id", type=int, required=True)
@click.option("--rationale", default=None)
@click.option("--source-url", default=None)
@click.option("--plan", default=None)
@click.option("--status", default=None)
@click.option("--assigned", default=None)
@click.option("--next-action", default=None)
@click.option("--owner", default=None)
@click.option("--notes", default=None)
def agent_set(slug, task_id, **fields):
    """Patch a task (store rationale/source/plan/status/…)."""
    try:
        _emit(_client(slug).patch_task(task_id, **fields))
    except (CanopyError, RuntimeError) as e:
        raise click.ClickException(str(e))
