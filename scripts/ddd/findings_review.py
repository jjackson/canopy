"""Product-findings review gate for demo-driven-development (review_mode: human).

After /canopy:ddd-run judges an iteration, findings are routed. In
``review_mode: autonomous`` (the default) the orchestrator auto-applies
PRODUCT findings whose ``fix_kind`` is ``mechanical``. In ``review_mode:
human`` the user picks which PRODUCT findings to implement — and before this
module existed, that meant a hand-written chat table with no way to see the
evidence behind each finding without manually scrubbing the deck and video.

This module formalizes that flow: it clusters the iteration's PRODUCT
findings, attaches **evidence deep-links** to each cluster — the hosted deck
URL with a ``#scene-<N>`` anchor AND the hosted clip URL with a
``#t=<seconds>`` time fragment at that scene's start offset — and posts ONE
``product_findings`` review to the canopy-web review surface. The user opens
a single link, reads each cluster next to its evidence, and decides
implement / skip / defer per cluster.

Where the video timestamps come from: the walkthrough recorder
(``scripts/walkthrough/record_video.py``) stamps per-scene
``start_seconds``/``duration_seconds`` into the run report
(``run-report.json``, see ``RunReport.scenes``); ``scene_timestamps`` reads
them back; the canopy-web ``/w/<id>`` viewer seeks to ``#t=<seconds>`` on
load.

Public API (pure functions — no network):
    cluster_findings(findings, user_verdict=None, scene_resolver=None) -> list[dict]
    build_findings_review_request(run_id, spec, findings, user_verdict,
                                  deck_url, clip_url, scene_timestamps) -> ReviewRequest
    parse_selection(response_json) -> dict
    resolve_review_mode(spec_or_path) -> str

CLI (post touches network via review.post_review_request):
    python -m scripts.ddd.findings_review post <run_id> [--spec PATH] [--deck-url URL] [--clip-url URL]
    python -m scripts.ddd.findings_review apply <response_json_file>
    python -m scripts.ddd.findings_review mode <spec_path>
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

from scripts.ddd.narrative import (
    _internal_review_url,
    _narrative_slug_from_run_id,
    _title_slug,
    _tokenized_review_url,
)
from scripts.ddd.schemas.models import Decision, NarrationItem, ReviewRequest, UnifiedSpec

GATE = "product_findings"

# Decision vocabulary — per cluster, and the one overall decision.
CLUSTER_OPTIONS = ["implement", "skip", "defer"]
OVERALL_DECISION_ID = "findings-verdict"
OVERALL_OPTIONS = ["proceed with selected", "discuss"]

# Merge orderings: a cluster takes the WORST of its members.
_FIX_KIND_ORDER = {"mechanical": 0, "options": 1, "redesign": 2}
_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}

_SCENE_INT_RE = re.compile(r"(\d+)")


# ---------------------------------------------------------------------------
# Scene resolution — finding["scene"] is "<scene title or index>" per the
# ddd-concept-eval contract, so it may be an int, "3", "Scene 3", or a title.
# ---------------------------------------------------------------------------


def make_scene_resolver(spec: UnifiedSpec | dict | None):
    """Return a ``str|int -> int|None`` resolver mapping a finding's ``scene``
    field to its 1-based spec index.

    Resolution order: int / digit string → that index; ``"Scene N"`` style →
    N; otherwise slug-match against the spec's scene titles. ``None`` when the
    value can't be resolved (the cluster then gets no per-scene anchors).
    """
    title_to_index: dict[str, int] = {}
    scenes = []
    if isinstance(spec, UnifiedSpec):
        scenes = [s.title for s in spec.scenes]
    elif isinstance(spec, dict):
        scenes = [s.get("title", "") for s in (spec.get("scenes") or []) if isinstance(s, dict)]
    for i, title in enumerate(scenes, start=1):
        title_to_index[_title_slug(title)] = i

    def resolve(value) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        s = str(value).strip()
        if not s:
            return None
        if s.isdigit():
            return int(s)
        slug = _title_slug(s)
        if slug in title_to_index:
            return title_to_index[slug]
        m = _SCENE_INT_RE.search(s)
        if m and s.lower().startswith("scene"):
            return int(m.group(1))
        return None

    return resolve


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------


def _one_line_title(detail: str, *, max_len: int = 110) -> str:
    """First sentence of *detail*, truncated — the cluster's scannable title."""
    text = " ".join((detail or "").split())
    if not text:
        return "(untitled finding)"
    first = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    if len(first) > max_len:
        first = first[: max_len - 1].rstrip() + "…"
    return first


def _worst(values: list[str], order: dict[str, int], default: str) -> str:
    best = default
    best_rank = order.get(default, 0)
    for v in values:
        rank = order.get(v, -1)
        if rank > best_rank:
            best, best_rank = v, rank
    return best


def cluster_findings(
    findings: list[dict],
    *,
    user_verdict: dict | None = None,
    scene_resolver=None,
) -> list[dict]:
    """Cluster PRODUCT findings for the review surface.

    Parameters
    ----------
    findings:
        ``design_findings.json`` entries (the ddd-concept-eval contract:
        ``scene``, ``dimension``, ``severity``, ``route``, ``detail``,
        ``fix_recommendation``, optional ``fix_kind``, optional explicit
        ``cluster`` key).
    user_verdict:
        The parsed ``verdict-user.yaml`` dict.  Each dimension entry carrying
        a ``fix_kind`` (i.e. it scored ≤3 and emitted a finding) becomes its
        own cluster with id ``user-<dimension>``.  These findings are
        artifact-wide (the user-artifact judge scores the whole run), so they
        carry no scene anchor unless the justification names one.
    scene_resolver:
        ``str|int -> int|None`` mapping a finding's ``scene`` field to its
        1-based spec index (see :func:`make_scene_resolver`).  ``None`` →
        digit-only resolution.

    Returns
    -------
    list[dict]
        One dict per cluster: ``cluster_id``, ``title``, ``detail``,
        ``scenes`` (sorted 1-based indices), ``scene_labels`` (raw values
        that didn't resolve), ``dimension``, ``severity``, ``route``,
        ``fix_kind``, ``suggested_fix``, ``count``.  Only ``route ==
        "PRODUCT"`` findings are included — CONCEPT/RESEARCH/DEFER have
        their own routing and never reach this gate.

    Grouping key: an explicit ``cluster`` key on the finding when present,
    else ``(scene, dimension)`` — repeated judge output about the same scene
    + dimension reads as one decision, not N near-duplicate rows.
    """
    resolve = scene_resolver or make_scene_resolver(None)

    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for f in findings or []:
        if not isinstance(f, dict):
            continue
        if (f.get("route") or "").upper() != "PRODUCT":
            continue
        explicit = (f.get("cluster") or "").strip()
        if explicit:
            key = f"cluster:{_title_slug(explicit)}"
        else:
            idx = resolve(f.get("scene"))
            dim = f.get("dimension") or "general"
            scene_part = f"scene-{idx}" if idx is not None else _title_slug(str(f.get("scene") or "no-scene"))
            key = f"{scene_part}-{_title_slug(dim)}"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(f)

    clusters: list[dict] = []
    for key in order:
        members = groups[key]
        cluster_id = key.removeprefix("cluster:")
        scenes: set[int] = set()
        scene_labels: list[str] = []
        details: list[str] = []
        fixes: list[str] = []
        for f in members:
            idx = resolve(f.get("scene"))
            if idx is not None:
                scenes.add(idx)
            elif f.get("scene"):
                label = str(f["scene"])
                if label not in scene_labels:
                    scene_labels.append(label)
            d = (f.get("detail") or "").strip()
            if d and d not in details:
                details.append(d)
            fx = (f.get("fix_recommendation") or "").strip()
            if fx and fx not in fixes:
                fixes.append(fx)
        detail = "\n".join(details)
        clusters.append(
            {
                "cluster_id": cluster_id,
                "title": _one_line_title(details[0] if details else ""),
                "detail": detail,
                "scenes": sorted(scenes),
                "scene_labels": scene_labels,
                "dimension": members[0].get("dimension") or "general",
                "severity": _worst([m.get("severity", "low") for m in members], _SEVERITY_ORDER, "low"),
                "route": "PRODUCT",
                "fix_kind": _worst(
                    [m.get("fix_kind", "options") for m in members], _FIX_KIND_ORDER, "mechanical"
                ),
                "suggested_fix": "\n".join(fixes),
                "count": len(members),
            }
        )

    # User-artifact judge findings: one cluster per dimension carrying a fix.
    dims = (user_verdict or {}).get("dimensions") or {}
    for dim_id, entry in dims.items():
        if not isinstance(entry, dict) or not entry.get("fix_kind"):
            continue
        score = entry.get("score")
        try:
            severity = "high" if float(score) <= 2 else "medium"
        except (TypeError, ValueError):
            severity = "medium"
        detail = (entry.get("justification") or "").strip()
        clusters.append(
            {
                "cluster_id": f"user-{_title_slug(str(dim_id))}",
                "title": _one_line_title(detail) if detail else f"User-artifact: {dim_id}",
                "detail": detail,
                "scenes": [],
                "scene_labels": [],
                "dimension": str(dim_id),
                "severity": severity,
                "route": "PRODUCT",
                "fix_kind": entry.get("fix_kind", "options"),
                "suggested_fix": (entry.get("fix_recommendation") or "").strip(),
                "count": 1,
            }
        )

    return clusters


# ---------------------------------------------------------------------------
# Evidence links
# ---------------------------------------------------------------------------


def _format_ts(seconds: float) -> str:
    """``83.4 -> "1:23"`` — mm:ss label for a video timestamp."""
    total = int(seconds)
    return f"{total // 60}:{total % 60:02d}"


def evidence_links(
    cluster: dict,
    *,
    deck_url: str | None,
    clip_url: str | None,
    scene_timestamps: dict[int, float] | None,
) -> list[dict]:
    """Build the ``[{label, url}]`` evidence list for one cluster.

    Per scene the cluster touches: the deck anchor (``<deck_url>#scene-<N>``)
    and — when the recorder stamped a timing for that scene — the clip
    deep-link (``<clip_url>#t=<seconds>``; the ``/w/`` viewer seeks on load).
    A cluster with no resolvable scenes (e.g. an artifact-wide user-judge
    finding) gets the bare deck/clip links so the reviewer still has one
    click to the artifact.
    """
    ts = scene_timestamps or {}
    links: list[dict] = []
    scenes: list[int] = cluster.get("scenes") or []
    if scenes:
        for n in scenes:
            if deck_url:
                links.append({"label": f"Deck — scene {n}", "url": f"{deck_url}#scene-{n}"})
            if clip_url and n in ts:
                start = ts[n]
                links.append(
                    {
                        "label": f"Video @ {_format_ts(start)} (scene {n})",
                        "url": f"{clip_url}#t={int(start)}",
                    }
                )
    else:
        if deck_url:
            links.append({"label": "Deck", "url": deck_url})
        if clip_url:
            links.append({"label": "Video", "url": clip_url})
    return links


_W_PAGE_RE = re.compile(r"^(?P<base>https?://[^/]+)/w/(?P<wid>[0-9a-fA-F-]{36})")


def _clip_content_url(clip_url: str | None) -> str | None:
    """Derive the streamable ``/w/<id>/content`` URL from a ``/w/<id>`` page URL.

    The review surface embeds ``request_json.video.url`` in a player; the
    ``/w/<id>`` page URL is an HTML app route, not media — the bytes live at
    ``/w/<id>/content``.  Preserves any existing query (e.g. a share token).
    Returns ``None`` when *clip_url* isn't a recognisable ``/w/`` URL.
    """
    if not clip_url:
        return None
    m = _W_PAGE_RE.match(clip_url)
    if not m:
        return None
    query = ""
    if "?" in clip_url:
        query = "?" + clip_url.split("?", 1)[1].split("#", 1)[0]
    return f"{m.group('base')}/w/{m.group('wid')}/content{query}"


# ---------------------------------------------------------------------------
# Request building
# ---------------------------------------------------------------------------


def build_findings_review_request(
    run_id: str,
    spec: UnifiedSpec | dict | None,
    findings: list[dict],
    user_verdict: dict | None,
    deck_url: str | None,
    clip_url: str | None,
    scene_timestamps: dict[int, float] | None,
    *,
    narrative_slug: str | None = None,
) -> ReviewRequest:
    """Build the ``product_findings`` ReviewRequest for one judged iteration.

    One narration entry + one implement/skip/defer Decision per finding
    CLUSTER (PRODUCT route only — see :func:`cluster_findings`), each
    carrying evidence deep-links (deck ``#scene-<N>`` + clip ``#t=<seconds>``)
    so the reviewer never has to scrub for the moment a finding refers to.
    Plus one overall decision: proceed with the selected fixes, or discuss.

    The machine-readable cluster list (with evidence) also rides on
    ``ReviewRequest.findings``; the orchestrator reads the resolved
    ``response_json.decisions`` back via :func:`parse_selection`.
    """
    resolved_slug = (narrative_slug or "").strip() or _narrative_slug_from_run_id(run_id)
    resolver = make_scene_resolver(spec)
    clusters = cluster_findings(findings, user_verdict=user_verdict, scene_resolver=resolver)

    narration: list[NarrationItem] = []
    decisions: list[Decision] = []
    for i, cluster in enumerate(clusters, start=1):
        links = evidence_links(
            cluster,
            deck_url=deck_url,
            clip_url=clip_url,
            scene_timestamps=scene_timestamps,
        )
        cluster["evidence"] = links

        text_parts = [cluster["detail"] or cluster["title"]]
        if cluster["suggested_fix"]:
            text_parts.append(f"Suggested fix: {cluster['suggested_fix']}")
        if links:
            text_parts.append(
                "Evidence: " + " · ".join(f"{e['label']} → {e['url']}" for e in links)
            )
        narration.append(
            NarrationItem(
                scene=i,
                id=cluster["cluster_id"],
                title=cluster["title"],
                text="\n\n".join(text_parts),
            )
        )
        scene_tag = (
            "scenes " + ", ".join(str(n) for n in cluster["scenes"])
            if cluster["scenes"]
            else "whole artifact"
        )
        decisions.append(
            Decision(
                id=cluster["cluster_id"],
                prompt=(
                    f"[{cluster['severity']} · {cluster['dimension']} · "
                    f"{cluster['fix_kind']} · {scene_tag}] {cluster['title']}"
                ),
                options=list(CLUSTER_OPTIONS),
                recommended="implement",
                **{"class": GATE},
            )
        )

    decisions.append(
        Decision(
            id=OVERALL_DECISION_ID,
            prompt="Proceed with the selected fixes, or discuss first?",
            options=list(OVERALL_OPTIONS),
            recommended="proceed with selected",
            **{"class": GATE},
        )
    )

    video: dict = {}
    content_url = _clip_content_url(clip_url)
    if content_url:
        video = {"url": content_url}

    return ReviewRequest(
        run_id=run_id,
        narrative_slug=resolved_slug,
        gate=GATE,
        video=video,
        narration=narration,
        decisions=decisions,
        findings=clusters,
        autonomous_audit=[],
    )


# ---------------------------------------------------------------------------
# Response parsing (the `apply` subcommand)
# ---------------------------------------------------------------------------


def parse_selection(response_json: dict) -> dict:
    """Turn a resolved review's ``response_json`` into a machine-readable selection.

    Returns::

        {"overall": "proceed with selected" | "discuss" | None,
         "selections": [{"cluster_id": str, "decision": str}, ...],
         "implement": [cluster ids],
         "skip": [cluster ids],
         "defer": [cluster ids]}

    Unknown decision values are preserved in ``selections`` but excluded from
    the three buckets (the orchestrator treats them as ``defer`` — never
    auto-apply on ambiguity).
    """
    decisions: dict = (response_json or {}).get("decisions") or {}
    overall = decisions.get(OVERALL_DECISION_ID)
    selections: list[dict] = []
    buckets: dict[str, list[str]] = {"implement": [], "skip": [], "defer": []}
    for cluster_id, decision in decisions.items():
        if cluster_id == OVERALL_DECISION_ID:
            continue
        selections.append({"cluster_id": cluster_id, "decision": decision})
        if decision in buckets:
            buckets[decision].append(cluster_id)
    return {
        "overall": overall,
        "selections": selections,
        "implement": buckets["implement"],
        "skip": buckets["skip"],
        "defer": buckets["defer"],
    }


# ---------------------------------------------------------------------------
# Review mode resolution
# ---------------------------------------------------------------------------


def resolve_review_mode(spec_or_path) -> str:
    """Return the effective review mode for a spec: ``autonomous`` | ``human``.

    Accepts a spec dict, a ``UnifiedSpec``, or a path to the spec YAML.  The
    mode lives on the spec's optional ``review_mode`` key; absent, unreadable,
    or unrecognised values default to ``autonomous`` (the documented default —
    human review is always an explicit opt-in).
    """
    raw = None
    if isinstance(spec_or_path, UnifiedSpec):
        return spec_or_path.review_mode
    if isinstance(spec_or_path, dict):
        raw = spec_or_path
    else:
        p = Path(spec_or_path)
        if not p.exists():
            return "autonomous"
        try:
            raw = yaml.safe_load(p.read_text())
        except Exception:
            return "autonomous"
    if not isinstance(raw, dict):
        return "autonomous"
    mode = raw.get("review_mode")
    return mode if mode in ("autonomous", "human") else "autonomous"


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def _latest(d: dict) -> str | None:
    """Value at the largest int key of an ``iteration -> url`` map."""
    if not d:
        return None
    try:
        key = max(d, key=lambda k: int(k))
    except (TypeError, ValueError):
        return None
    return d[key]


def _git_toplevel() -> Path | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], stderr=subprocess.DEVNULL, text=True
        ).strip()
        return Path(out) if out else None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _default_spec_path(narrative_slug: str) -> Path | None:
    """``<git-toplevel>/docs/walkthroughs/<slug>.yaml`` when it exists."""
    top = _git_toplevel()
    if top is None:
        return None
    candidate = top / "docs" / "walkthroughs" / f"{narrative_slug}.yaml"
    return candidate if candidate.exists() else None


def _load_yaml(path: Path) -> dict | None:
    try:
        data = yaml.safe_load(path.read_text())
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _cmd_post(args: argparse.Namespace) -> None:
    """Post the product-findings review for *run_id*, stamp run_state, print JSON.

    Inputs are resolved from the run dir (CWD's git toplevel via
    ``runstate._resolve_ddd_dir``): ``design_findings.json``,
    ``verdict-user.yaml``, ``run-report.json`` (scene timestamps), and the
    run_state's ``iteration_decks`` / ``iteration_clips`` for the hosted
    artifact URLs.  Prints ``{posted: false, reason}`` (exit 0) when there are
    no PRODUCT findings — that's a clean outcome, not an error.
    """
    from scripts.ddd import review as rv  # network-touching — local import
    from scripts.ddd import runstate as rs
    from scripts.walkthrough._lib.results import scene_timestamps as read_scene_timestamps

    run_id = args.run_id
    try:
        state = rs.load(run_id)
    except FileNotFoundError:
        print(f"ERROR: run_state for {run_id!r} not found — wrong run_id or wrong CWD?", file=sys.stderr)
        sys.exit(1)

    run_dir = rs._resolve_ddd_dir() / "runs" / run_id
    findings = _load_json(run_dir / "design_findings.json") or []
    user_verdict = _load_yaml(run_dir / "verdict-user.yaml")
    report = _load_json(run_dir / "run-report.json") or {}
    timestamps = read_scene_timestamps(report) if isinstance(report, dict) else {}

    iteration = state.iteration
    deck_url = (args.deck_url or "").strip() or state.iteration_decks.get(iteration) or _latest(
        state.iteration_decks
    )
    clip_url = (args.clip_url or "").strip() or state.iteration_clips.get(iteration) or _latest(
        state.iteration_clips
    )

    spec: dict | None = None
    spec_path = Path(args.spec) if args.spec else _default_spec_path(state.narrative_slug)
    if spec_path is not None:
        spec = _load_yaml(spec_path)
        if spec is None:
            print(f"WARNING: could not read spec at {spec_path} — scene titles won't resolve.", file=sys.stderr)

    request = build_findings_review_request(
        run_id,
        spec,
        findings,
        user_verdict,
        deck_url,
        clip_url,
        timestamps,
        narrative_slug=state.narrative_slug,
    )

    if not request.findings:
        print(
            json.dumps(
                {"posted": False, "reason": "no PRODUCT findings to review", "run_id": run_id}
            )
        )
        return

    result = rv.post_review_request(request)

    # Stamp run_state so the orchestrator (and a resumed session) can find the
    # pending review without re-posting. Mirrors narrative post's stamping.
    review_id = (result.get("id") or "").strip()
    if review_id:
        state.findings_review_id = review_id
    share = _tokenized_review_url(result)
    if share:
        state.findings_review_url = share
    rs.save(state)

    base = rv._resolve_base_url(None)
    out = dict(result)
    out["posted"] = True
    out["clusters"] = len(request.findings)
    internal = _internal_review_url(result, base)
    if internal:
        out["internal_url"] = internal
    if share:
        out["share_url"] = share if share.startswith("http") else f"{base.rstrip('/')}{share}"
    if internal:
        print(f"internal (owner, left rail): {internal}", file=sys.stderr)
    if out.get("share_url"):
        print(f"external (share, no rail):   {out['share_url']}", file=sys.stderr)
    print(json.dumps(out))


def _cmd_apply(args: argparse.Namespace) -> None:
    """Parse a resolved response JSON file and print the selection."""
    response_path = Path(args.response_json_file)
    if not response_path.exists():
        print(f"ERROR: response JSON file not found: {response_path}", file=sys.stderr)
        sys.exit(1)
    response_json = json.loads(response_path.read_text())
    print(json.dumps(parse_selection(response_json)))


def _cmd_mode(args: argparse.Namespace) -> None:
    """Print the effective review mode for a spec path: autonomous | human."""
    print(resolve_review_mode(args.spec_path))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m scripts.ddd.findings_review")
    sub = parser.add_subparsers(dest="command", required=True)

    p_post = sub.add_parser("post", help="post the product-findings review for a judged run")
    p_post.add_argument("run_id")
    p_post.add_argument("--spec", help="unified spec YAML (default: <git-toplevel>/docs/walkthroughs/<narrative_slug>.yaml)")
    p_post.add_argument("--deck-url", help="hosted deck URL (default: run_state.iteration_decks[iteration])")
    p_post.add_argument("--clip-url", help="hosted clip URL (default: run_state.iteration_clips[iteration])")
    p_post.set_defaults(func=_cmd_post)

    p_apply = sub.add_parser("apply", help="parse a resolved response_json into a machine-readable selection")
    p_apply.add_argument("response_json_file")
    p_apply.set_defaults(func=_cmd_apply)

    p_mode = sub.add_parser("mode", help="print the spec's effective review mode (autonomous | human)")
    p_mode.add_argument("spec_path")
    p_mode.set_defaults(func=_cmd_mode)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
