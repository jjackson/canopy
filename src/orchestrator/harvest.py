"""Harvest corpus assembly — the deterministic half of the architect/harvester (Hal).

The problem this solves (see canopy memory `harvester-architect`): a fast builder's session
review rots because it (a) reads one user, (b) reads a recent window, (c) persists stale insights.
This module is the *mechanical* fix: assemble a cross-user, origin-anchored corpus for one
initiative, and flag its own blindness. It does NO judgment — reconstructing intent and
characterizing drift is the agent's (Hal's) native job, reading the corpus this returns.

Design laws (proven on the DDD case):
- **Cross-user or the conclusion inverts.** JJ alternates macOS accounts (acedimagi + jjackson)
  on rate-limit; an initiative's ORIGIN can live on the account you can't see. Read every readable
  ~/.claude/projects on the machine.
- **Origin-anchored, longitudinal.** Return sessions oldest-first; intent is reconstructed from the
  ARC's start, not a recent window (a window read mistakes "still grinding" for "intent changed").
- **Flag own blindness.** `confidence: half-blind` is a first-class field whenever any user's
  sessions are unreadable.
"""
from __future__ import annotations

import datetime as _dt
import glob
import json
import os
from dataclasses import dataclass, field

from orchestrator import turn_synthesis


@dataclass
class SessionRef:
    user: str
    path: str
    project: str
    mtime: float
    first_prompt: str = ""

    @property
    def when(self) -> str:
        return _dt.datetime.fromtimestamp(self.mtime).strftime("%Y-%m-%d %H:%M")


def user_session_roots(users_root: str = "/Users") -> list[dict]:
    """Every macOS user's ~/.claude/projects, with a readability flag (for confidence)."""
    out = []
    for home in sorted(glob.glob(os.path.join(users_root, "*"))):
        p = os.path.join(home, ".claude", "projects")
        if not os.path.isdir(p):
            continue
        try:
            os.listdir(p)
            readable = True
        except OSError:
            readable = False
        out.append({"user": os.path.basename(home), "path": p, "readable": readable})
    return out


def _first_prompt(path: str) -> str:
    try:
        with open(path, errors="replace") as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                if e.get("type") == "user":
                    c = e.get("message", {}).get("content", "")
                    if isinstance(c, str) and c.strip() and not c.startswith("<"):
                        return c.strip().replace("\n", " ")[:200]
    except OSError:
        pass
    return ""


def human_messages(path: str, limit: int = 14) -> list[str]:
    """The human's typed turns (intent + steering) — the close-read evidence, not tool noise."""
    out = []
    try:
        with open(path, errors="replace") as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                if e.get("type") != "user":
                    continue
                c = e.get("message", {}).get("content", "")
                if isinstance(c, str):
                    s = c.strip()
                    if (s and not s.startswith("<") and not s.startswith("Caveat")
                            and "[Request interrupted" not in s and "tool_result" not in s):
                        out.append(s.replace("\n", " ")[:240])
                if len(out) >= limit:
                    break
    except OSError:
        pass
    return out


def _matches(initiative: str, terms: list[str], project_name: str, path: str) -> bool:
    name = project_name.lower()
    if any(t in name for t in terms):
        return True
    # else sample the head for any term (cheap; islice tolerates short files)
    import itertools
    try:
        with open(path, errors="replace") as fh:
            head = "".join(itertools.islice(fh, 60)).lower()
    except OSError:
        return False
    return any(t in head for t in terms)


def find_initiative_sessions(
    initiative: str, terms: list[str], roots: list[dict] | None = None
) -> list[SessionRef]:
    """All sessions matching the initiative, across all readable users, OLDEST FIRST."""
    roots = roots if roots is not None else user_session_roots()
    terms = [t.lower() for t in terms] or [initiative.lower()]
    refs: list[SessionRef] = []
    for root in roots:
        if not root["readable"]:
            continue
        for d in glob.glob(os.path.join(root["path"], "*")):
            proj = os.path.basename(d)
            for f in glob.glob(os.path.join(d, "*.jsonl")):
                if not _matches(initiative, terms, proj, f):
                    continue
                try:
                    mt = os.path.getmtime(f)
                except OSError:
                    continue
                refs.append(SessionRef(user=root["user"], path=f, project=proj, mtime=mt))
    refs.sort(key=lambda r: r.mtime)
    return refs


def _ordered_texts(path: str) -> list[tuple[str, str]]:
    """Ordered [('U', human_input) | ('A', assistant_text_block)] — tool noise dropped.

    The stripped conversation: what you said + what the agent said back. No tool calls/results.
    Delegates to the canonical ``turn_synthesis`` reducer (shared with share-session) so the
    noise filter and slash-command handling never drift between the two callers.
    """
    return turn_synthesis.iter_messages(path)


def strip_session(path: str, mode: str = "final") -> str:
    """A session reduced to (your inputs + assistant outputs), tool noise removed — the
    canopy-web-style readable view. mode='final' is the *turn-synthesis*: each prompt paired
    with the FINAL assistant reply that followed it; mode='full' keeps every assistant prose
    block."""
    if mode == "final":
        _session_id, turns = turn_synthesis.synthesize(path)
        parts: list[str] = []
        for t in turns:
            parts.append("USER: " + t.prompt)
            if t.response:
                parts.append("ASSISTANT: " + t.response)
        return "\n\n".join(parts)
    seq = turn_synthesis.iter_messages(path)
    return "\n\n".join(("USER: " if r == "U" else "ASSISTANT: ") + t for r, t in seq)


def session_digest(path: str, user: str = "", mtime: float = 0.0, inputs_k: int = 6,
                   full: bool = False) -> dict:
    """A per-session digest for the whole-arc map. Default = tiny (first input + a few sampled
    inputs + the final output, truncated). `full=True` = RICH: ALL your inputs untruncated (the
    highest-signal part, and short) + the full final output. Use full when quality > token-cost."""
    seq = _ordered_texts(path)
    inputs = [t for r, t in seq if r == "U"]
    finals = [t for r, t in seq if r == "A"]
    when = _dt.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M") if mtime else ""
    base = {
        "path": str(path), "user": user, "when": when,
        "project": "/".join([x for x in os.path.basename(os.path.dirname(path)).split("-") if x][-2:]),
        "turns": len(inputs),
    }
    if full:
        base["first_input"] = inputs[0] if inputs else ""
        base["inputs"] = inputs                       # ALL of them, untruncated
        base["final_output"] = finals[-1] if finals else ""
        return base
    sampled = inputs[:1]
    if len(inputs) > 1 and inputs_k > 1:
        rest = inputs[1:]
        step = max(1, len(rest) // (inputs_k - 1))
        sampled += rest[::step][: inputs_k - 1]
    base["first_input"] = inputs[0][:300] if inputs else ""
    base["inputs"] = [s[:160] for s in sampled]
    base["final_output"] = finals[-1][:300] if finals else ""
    return base


def corpus_map(initiative: str, terms: list[str], *, inputs_k: int = 6, full: bool = False,
               roots: list[dict] | None = None) -> dict:
    """Whole-arc MAP: a digest of EVERY matched session (cross-user, oldest-first). `full=True`
    makes each digest rich (all inputs untruncated + full final output) — still small enough to
    read the whole arc in one pass, and loses no input signal. Then drill in with strip_session."""
    roots = roots if roots is not None else user_session_roots()
    refs = find_initiative_sessions(initiative, terms, roots=roots)
    unreadable = [r["user"] for r in roots if not r["readable"]]
    return {
        "initiative": initiative, "terms": terms,
        "confidence": "half-blind" if unreadable else "whole-corpus",
        "unreadable_users": unreadable,
        "total_sessions": len(refs),
        "by_user": {u: sum(1 for r in refs if r.user == u) for u in {r.user for r in refs}},
        "span": ({"from": refs[0].when, "to": refs[-1].when} if refs else None),
        "digests": [session_digest(r.path, r.user, r.mtime, inputs_k=inputs_k, full=full) for r in refs],
    }


def assemble_corpus(
    initiative: str, terms: list[str], *, origin_k: int = 6, recent_k: int = 6,
    roots: list[dict] | None = None,
) -> dict:
    """Cross-user, origin-anchored corpus for one initiative. No judgment — material for Hal."""
    roots = roots if roots is not None else user_session_roots()
    refs = find_initiative_sessions(initiative, terms, roots=roots)

    unreadable = [r["user"] for r in roots if not r["readable"]]
    confidence = "half-blind" if unreadable else "whole-corpus"

    by_user: dict[str, int] = {}
    for r in refs:
        by_user[r.user] = by_user.get(r.user, 0) + 1

    def detail(refs_slice):
        out = []
        for r in refs_slice:
            r.first_prompt = r.first_prompt or _first_prompt(r.path)
            out.append({
                "user": r.user, "when": r.when,
                "project": "/".join([x for x in r.project.split("-") if x][-2:]),
                "first_prompt": r.first_prompt,
                "human_messages": human_messages(r.path),
            })
        return out

    return {
        "initiative": initiative,
        "terms": terms,
        "confidence": confidence,
        "unreadable_users": unreadable,
        "total_sessions": len(refs),
        "by_user": by_user,
        "span": (
            {"from": refs[0].when, "to": refs[-1].when} if refs else None
        ),
        # ORIGIN first (intent), then RECENT (status/drift). Deliberately not the middle grind.
        "origin_sessions": detail(refs[:origin_k]),
        "recent_sessions": detail(refs[-recent_k:][::-1]),
    }
