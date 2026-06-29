"""Shared client for canopy-web's agent workspace (/api/agents). Operator-plane
only (identity, syncs, work-products, skills, tasks, commands) — NO run lifecycle."""
from __future__ import annotations

import glob
import os
import re
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, ConfigDict

from orchestrator import canopy_web
from orchestrator.canopy_web import CanopyError, Transport  # re-export

__all__ = ["AgentIdentity", "BoardCommand", "AgentClient", "catalog_from_repo", "CanopyError"]


class AgentIdentity(BaseModel):
    slug: str
    name: str = ""
    email: str = ""
    description: str = ""
    persona: str = ""
    avatar_url: str = ""


class BoardCommand(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    kind: str
    task_title: Optional[str] = None
    created_by: str = ""
    payload: Optional[dict] = None


class AgentClient:
    def __init__(self, identity, *, base_url: Optional[str] = None,
                 token: Optional[str] = None, transport: Optional[Transport] = None):
        self.identity = identity if isinstance(identity, AgentIdentity) else AgentIdentity(**identity)
        self._base = base_url
        self._token = token
        self._transport = transport

    @property
    def slug(self) -> str:
        return self.identity.slug

    def _call(self, method: str, path: str, body=None) -> dict:
        return canopy_web.call(method, path, body, base_url=self._base,
                               token=self._token, transport=self._transport)

    def register(self) -> dict:
        return self._call("POST", "/api/agents/", self.identity.model_dump())

    def post_sync(self, *, period_start, period_end, title, doc_url,
                  summary="", self_grades=None, source="manager-sync") -> dict:
        body = {"period_start": period_start, "period_end": period_end, "title": title,
                "summary": summary, "doc_url": doc_url,
                "self_grades": self_grades or {}, "source": source}
        return self._call("POST", f"/api/agents/{self.slug}/syncs/", body)

    def put_work_products(self, items: list[dict]) -> dict:
        return self._call("POST", f"/api/agents/{self.slug}/work-products/", {"work_products": items})

    def put_skills(self, items: list[dict]) -> dict:
        return self._call("PUT", f"/api/agents/{self.slug}/skills/", {"skills": items})

    def sync_tasks(self, tasks: list[dict]) -> dict:
        return self._call("POST", f"/api/agents/{self.slug}/tasks/sync", {"tasks": tasks})

    def list_tasks(self) -> "list[dict]":
        raw = self._call("GET", f"/api/agents/{self.slug}/tasks/")
        return raw if isinstance(raw, list) else (raw or {}).get("results", [])

    def pending_commands(self) -> "list[BoardCommand]":
        raw = self._call("GET", f"/api/agents/{self.slug}/commands?status=pending")
        return [BoardCommand(**c) for c in (raw or [])]

    def apply_command(self, command_id: int, result_note: str = "") -> dict:
        return self._call("POST", f"/api/agents/{self.slug}/commands/{command_id}/apply",
                          {"result_note": result_note})

    def patch_task(self, task_id: int, **fields) -> dict:
        patch = {k: v for k, v in fields.items() if v is not None}
        return self._call("PATCH", f"/api/agents/{self.slug}/tasks/{task_id}/", patch)


def _frontmatter(path: str) -> "tuple[str, str] | None":
    text = Path(path).read_text()
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return None
    block = m.group(1)
    name = re.search(r"^name:\s*(.+)$", block, re.M)
    desc = re.search(r"^description:\s*(?:>\s*)?\n?((?:.|\n)*?)(?:\n\w[\w-]*:|\Z)", block, re.M)
    name_v = name.group(1).strip() if name else ""
    desc_v = " ".join(l.strip() for l in (desc.group(1).splitlines() if desc else [])).strip()
    return name_v, desc_v


def catalog_from_repo(skills_root, url_template: str) -> "list[dict]":
    items = []
    for p in sorted(glob.glob(os.path.join(str(skills_root), "*", "SKILL.md"))):
        fm = _frontmatter(p)
        if not fm or not fm[0]:
            continue
        name, desc = fm
        items.append({"name": name, "description": desc,
                      "url": url_template.format(name=name), "improvement_note": ""})
    return items
