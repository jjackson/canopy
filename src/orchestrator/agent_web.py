"""canopy-web agent-workspace client — the shared generalization of echo's bin/echo_canopy.py.

Lets ANY agent repo publish itself to canopy-web's `/api/agents/*` surface: register the agent,
mirror its skill catalog, post syncs (with self-grades), and push work products. Backs the
`canopy agent-publish` CLI. This is the "common" half of the §4a boundary — canopy owns the
client; the agent repo owns only its identity.

Identity is resolved from the agent repo itself (no per-agent client copy needed):
  - `.claude-plugin/plugin.json` → slug (`name`) + description
  - `config/agent.json` (optional) → email / persona / avatar_url / display name overrides
  - the git `origin` remote → the GitHub blob base for skill links

Auth: a canopy-web PAT via `CANOPY_WEB_PAT`, or `~/.claude/canopy/workbench-token`
(mint once via `/canopy:canopy-web-pat-mint`). Content is attributed to the agent slug, not the
PAT user. Stdlib only (urllib) — no `requests` dependency.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE = "https://canopy-web-ujpz2cuyxq-uc.a.run.app"
TOKEN_FILE = os.path.expanduser("~/.claude/canopy/workbench-token")


class AgentWebError(Exception):
    """Bad agent identity, missing PAT, or a non-2xx canopy-web response."""


def base_url() -> str:
    return os.environ.get("CANOPY_WEB_API_URL", DEFAULT_BASE).rstrip("/")


def token() -> str:
    t = os.environ.get("CANOPY_WEB_PAT", "").strip()
    if t:
        return t
    if os.path.exists(TOKEN_FILE):
        t = Path(TOKEN_FILE).read_text().strip()
        if t:
            return t
    raise AgentWebError(
        "no canopy-web PAT — set CANOPY_WEB_PAT or run /canopy:canopy-web-pat-mint"
    )


def _call(path: str, body=None, method: str = "POST") -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base_url() + path, data=data, method=method,
        headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            txt = r.read().decode()
            return json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode()[:400]
        except Exception:
            pass
        raise AgentWebError(f"{method} {path} -> {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise AgentWebError(f"{method} {path} -> connection error: {e.reason}")


# ---- identity resolution (pure; testable without network) -----------------------------

def gh_blob_base(repo_dir: Path) -> str:
    """`https://github.com/<owner>/<repo>/blob/main/skills/{name}/SKILL.md` from the origin remote.

    Returns "" if there's no parseable GitHub origin. `{name}` is left as a literal placeholder
    for catalog_from_repo to fill per skill.
    """
    try:
        url = subprocess.run(
            ["git", "-C", str(repo_dir), "remote", "get-url", "origin"],
            capture_output=True, text=True,
        ).stdout.strip()
    except Exception:
        url = ""
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+?)(?:\.git)?/?$", url)
    if not m:
        return ""
    return f"https://github.com/{m.group(1)}/{m.group(2)}/blob/main/skills/{{name}}/SKILL.md"


def resolve_identity(repo_dir: Path) -> dict:
    """Build the agent identity dict from the repo's plugin.json + optional config/agent.json."""
    repo = Path(repo_dir)
    pj = repo / ".claude-plugin" / "plugin.json"
    if not pj.exists():
        raise AgentWebError(
            f"no .claude-plugin/plugin.json in {repo} — run this from an agent repo root"
        )
    p = json.loads(pj.read_text())
    slug = p.get("name")
    if not slug:
        raise AgentWebError(f"{pj} has no `name`")
    ident = {
        "slug": slug,
        "name": slug.replace("-", " ").title(),
        "email": "",
        "description": p.get("description", ""),
        "persona": "",
        "avatar_url": "",
    }
    aj = repo / "config" / "agent.json"
    if aj.exists():
        ident.update({k: v for k, v in json.loads(aj.read_text()).items() if v})
    return ident


def _frontmatter(path: Path):
    """Pull `name` + `description` from a SKILL.md YAML frontmatter (handles folded `>` blocks)."""
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return None
    block = m.group(1)
    name = re.search(r"^name:\s*(.+)$", block, re.M)
    desc = re.search(r"^description:\s*(?:>\s*)?\n?((?:.|\n)*?)(?:\n\w[\w-]*:|\Z)", block, re.M)
    name_v = name.group(1).strip() if name else None
    desc_v = " ".join(l.strip() for l in (desc.group(1).splitlines() if desc else [])).strip()
    return name_v, desc_v


def catalog_from_repo(repo_dir: Path) -> list[dict]:
    """Mirror skills/*/SKILL.md into canopy-web's skill-catalog shape."""
    repo = Path(repo_dir)
    gh = gh_blob_base(repo)
    items = []
    for p in sorted(repo.glob("skills/*/SKILL.md")):
        fm = _frontmatter(p)
        if not fm or not fm[0]:
            continue
        name, desc = fm
        items.append({
            "name": name,
            "description": desc,
            "url": gh.format(name=name) if gh else "",
            "improvement_note": "",
        })
    return items


# ---- API operations -------------------------------------------------------------------

def register(repo_dir: Path) -> dict:
    ident = resolve_identity(repo_dir)
    return _call("/api/agents/", {
        "slug": ident["slug"], "name": ident["name"], "email": ident["email"],
        "description": ident["description"], "persona": ident["persona"],
        "avatar_url": ident["avatar_url"],
    })


def put_skills(repo_dir: Path) -> dict:
    ident = resolve_identity(repo_dir)
    items = catalog_from_repo(repo_dir)
    return _call(f"/api/agents/{ident['slug']}/skills/", {"skills": items}, method="PUT")


def post_sync(repo_dir: Path, *, doc_url: str, title: str, summary: str,
              grades: dict, period_start: str, period_end: str, source: str) -> dict:
    ident = resolve_identity(repo_dir)
    return _call(f"/api/agents/{ident['slug']}/syncs/", {
        "period_start": period_start, "period_end": period_end, "title": title,
        "summary": summary, "doc_url": doc_url, "self_grades": grades, "source": source,
    })


def push_work(repo_dir: Path, items: list[dict]) -> dict:
    ident = resolve_identity(repo_dir)
    return _call(f"/api/agents/{ident['slug']}/work-products/", {"work_products": items})
