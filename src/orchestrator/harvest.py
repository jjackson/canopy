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
from orchestrator.session_sources import discover_local_sources


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
    """Every macOS user's ~/.claude/projects, with a readability flag (for confidence).

    Thin wrapper over `session_sources.discover_local_sources` -- the local
    /Users/*/.claude/projects glob + readable check now lives there (see its
    module docstring for why: this harvest corpus assembly and
    agent_coverage's cross-user transcript scan must never re-fork that glob
    into two copies). Preserves this function's original dict shape and its
    existing callers/tests unchanged.
    """
    return [{"user": s.name.split(":", 1)[1], "path": s.location, "readable": s.readable}
           for s in discover_local_sources(users_root=users_root)]


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


def build_intent_prompt(stripped: str, human_msgs: list[str]) -> str:
    """Assemble the intent-fidelity audit prompt — the JUDGMENT layer this module
    otherwise deliberately omits (see the module docstring: harvest does no judgment,
    reconstructing intent is the agent's native job). This is that reconstruction's
    prompt, not the reconstruction itself.

    Assembled INLINE by the framework-tier convention (#352): framework logic-prompts
    stay inline — static, co-located with their logic, immune to the #351 packaging
    class — while PRODUCT, user-editable templates go external via `prompts/load_prompt`.
    Sibling site: `agent_review.build_review_prompt`.

    `stripped` is the prompt<->response corpus for the session(s) under audit (see
    `strip_session`); `human_msgs` is Jonathan's own standing instructions / steering
    for the same span (see `human_messages`) — HIS words are the ground truth here,
    not a paraphrase of them.
    """
    human_msgs_block = "\n".join(f"- {m}" for m in human_msgs) if human_msgs else "(none)"
    return (
        "You are canopy's intent-fidelity auditor. Your job is to reconstruct what JONATHAN "
        "was actually going for, in HIS OWN WORDS, and then judge whether the agent did what "
        "he asked or decided — not whether the agent's output looks reasonable in isolation.\n\n"
        "Jonathan's own messages are the GROUND TRUTH for his intent. Weight them over anything "
        "the agent narrated about its own reasoning: an agent's self-description of what it did "
        "is not evidence of what Jonathan wanted.\n\n"
        f"SESSION (prompt<->response pairs):\n{stripped}\n\n"
        f"JONATHAN'S OWN WORDS (standing instructions / steering, verbatim):\n{human_msgs_block}\n\n"
        "Look for these four intent-miss classes:\n"
        "  1. approved-X/shipped-Y — Jonathan approved one thing and the agent shipped a "
        "different thing.\n"
        "  2. question-read-as-approval — Jonathan asked a clarifying QUESTION and the agent "
        "read it as an approval to proceed.\n"
        "  3. unapproved-judgment-folded-in — the agent folded in its own judgment call on "
        "something Jonathan never approved or decided.\n"
        "  4. eroded-discipline — Jonathan told the agent to ALWAYS do something, and it "
        "silently stopped happening.\n\n"
        "Produce a YAML list of findings. Each item:\n"
        "  - title: short imperative\n"
        "  - friction_type: intent_miss\n"
        "  - evidence: a RECORD (not free text) proving the finding is grounded:\n"
        "      source_ref: Jonathan's VERBATIM quote, plus the diverging response it does not "
        "match — both quoted exactly as they appear above, never paraphrased\n"
        "      was_read: true    # you actually read the session, not a proxy for it\n"
        "      already_fixed_check: {ran: true, result: '<not-fixed as of this session | fixed by ...>'}\n"
        "      confidence: high|medium|low\n"
        "      confidence_basis: one sentence justifying the level from the evidence above\n"
        "  - A finding whose evidence is not a complete record, or whose source_ref is not a "
        "verbatim quote, WILL BE DROPPED. Do not emit it.\n"
        "  - fix_kind: one of [skill_edit, hook_rule, schema_validator, claude_update, channel_fix, new_skill]\n"
        "  - target: the file/path the fix touches\n"
        "  - recommendation: the concrete change to make\n"
        "Rules:\n"
        "- Only surface a finding where Jonathan's OWN words diverge from what the agent did — "
        "do not flag stylistic disagreements or things Jonathan never actually weighed in on.\n"
        "- eroded-discipline findings are an invariant ('always do X' silently stopped) — prefer "
        "hook_rule or schema_validator, not prose.\n"
        "Output ONLY the YAML list.\n"
    )
