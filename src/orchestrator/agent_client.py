"""Shared client for canopy-web's agent workspace (/api/agents). Operator-plane
only (identity, syncs, work-products, skills, tasks, commands) — NO run lifecycle."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel

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
