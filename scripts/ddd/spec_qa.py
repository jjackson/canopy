"""DDD UnifiedSpec structural QA (SP2.2).

Pure-python, no LLM.  Delegates structural + semantic rules to validate.py;
adds QA-specific falsifiability checks on Scene.concept_claim.

Exposes:
    spec_qa(spec_obj_or_path, why_brief_path=None) -> Verdict

Rules checked:
    (via validate.py → _semantic_unified_spec)
    (b) Scene.provenance must match a SpineItem.id in the linked why_brief
    (e) Scene.persona must be defined in the personas dict
    (f) why_brief declared but not resolvable → problem
    Plus Pydantic-required fields (name, narrative, base_url, personas, scenes)

    (QA-specific, not in validate.py)
    (g) every Scene.concept_claim must be non-empty / non-whitespace
    (h) every Scene.concept_claim must be falsifiable — fails if it matches
        a banned list of pure-marketing phrases, OR has no verb.

Returns the ``Verdict`` model from scripts/ddd/schemas/models.py.
``verdict="pass"`` when all rules pass; ``verdict="fail"`` with a
``blocking_reason`` listing every violation when any rule fires.

On missing path, malformed input, or None, returns a ``fail`` Verdict
instead of raising — consistent with the ``-> Verdict`` contract.

CLI:
    python -m scripts.ddd.spec_qa <spec_path> [why_brief_path]
    exits 0 on pass, 1 on fail, 2 on usage error
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Union

import yaml

from scripts.ddd.schemas.models import UnifiedSpec, Verdict
from scripts.ddd.validate import validate

# ---------------------------------------------------------------------------
# Banned marketing phrases (case-insensitive substring match).
# If a concept_claim contains any of these, it is considered non-falsifiable.
# ---------------------------------------------------------------------------

_BANNED_PHRASES: list[str] = [
    "world-class",
    "world class",
    "seamless",
    "powerful",
    "robust",
    "best-in-class",
    "best in class",
    "cutting-edge",
    "cutting edge",
    "state-of-the-art",
    "state of the art",
    "revolutionary",
    "game-changing",
    "game changing",
    "innovative",
    "next-generation",
    "next generation",
]

# Simple verb indicators: common English verb tokens that suggest a claim
# describes an observable action or result.  A concept_claim must contain at
# least one of these (case-insensitive word-boundary match) to pass.
# We use a generous list to avoid false-positives on legitimate claims.
_VERB_PATTERNS: list[str] = [
    # base / infinitive forms commonly appearing in product claims
    r"\bcan\b",
    r"\bcannot\b",
    r"\bcan't\b",
    r"\bwill\b",
    r"\bwon't\b",
    r"\bshould\b",
    r"\bmust\b",
    r"\bgets?\b",
    r"\bgot\b",
    r"\breceives?\b",
    r"\bsends?\b",
    r"\bsent\b",
    r"\bshows?\b",
    r"\bshown\b",
    r"\bdisplays?\b",
    r"\bsees?\b",
    r"\bsaw\b",
    r"\bseen\b",
    r"\blocates?\b",
    r"\bfinds?\b",
    r"\bfound\b",
    r"\bloads?\b",
    r"\bloaded\b",
    r"\bopens?\b",
    r"\bopened\b",
    r"\bcloses?\b",
    r"\bsubmits?\b",
    r"\bsubmitted\b",
    r"\bsaves?\b",
    r"\bsaved\b",
    r"\bcreates?\b",
    r"\bcreated\b",
    r"\bdeletes?\b",
    r"\bdeleted\b",
    r"\bupdates?\b",
    r"\bupdated\b",
    r"\bnavigates?\b",
    r"\bnavigated\b",
    r"\breturns?\b",
    r"\bappears?\b",
    r"\bappeared\b",
    r"\bfilters?\b",
    r"\bfiltered\b",
    r"\bsorts?\b",
    r"\bsorted\b",
    r"\bexports?\b",
    r"\bexported\b",
    r"\btriggers?\b",
    r"\btriggered\b",
    r"\bnotifies?\b",
    r"\bnotified\b",
    r"\brenders?\b",
    r"\brendered\b",
    r"\bvalidates?\b",
    r"\bvalidated\b",
    r"\blogs?\b",
    r"\blogged\b",
    r"\brecords?\b",
    r"\brecorded\b",
    r"\bcompletes?\b",
    r"\bcompleted\b",
    r"\benables?\b",
    r"\benabled\b",
    r"\bprevents?\b",
    r"\bprevented\b",
    r"\breduces?\b",
    r"\breduced\b",
    r"\bincreases?\b",
    r"\bincreased\b",
    r"\bchanges?\b",
    r"\bchanged\b",
    r"\bsets?\b",
    r"\bset\b",
    r"\bhas\b",
    r"\bhave\b",
    r"\bhad\b",
    r"\bis\b",
    r"\bare\b",
    r"\bwas\b",
    r"\bwere\b",
    r"\ballow(?:s|ed)?\b",
    r"\bstart(?:s|ed)?\b",
    r"\bstop(?:s|ped)?\b",
    r"\brun(?:s)?\b",
    r"\bran\b",
    r"\brun\b",
    r"\bgenerate(?:s|d)?\b",
    r"\bproduce(?:s|d)?\b",
    r"\bprovide(?:s|d)?\b",
    r"\bsupport(?:s|ed)?\b",
    r"\bblock(?:s|ed)?\b",
    r"\breject(?:s|ed)?\b",
    r"\baccept(?:s|ed)?\b",
    r"\bconfirm(?:s|ed)?\b",
    r"\bdisable(?:s|d)?\b",
    r"\benable(?:s|d)?\b",
    r"\bfails?\b",
    r"\bfailed\b",
    r"\bpass(?:es|ed)?\b",
    r"\bdisplay(?:s|ed)?\b",
    r"\blist(?:s|ed)?\b",
    r"\blink(?:s|ed)?\b",
    r"\btrack(?:s|ed)?\b",
    r"\bmonitor(?:s|ed)?\b",
    r"\bmeasure(?:s|d)?\b",
    r"\bcalculate(?:s|d)?\b",
    r"\bcompute(?:s|d)?\b",
    r"\bprocess(?:es|ed)?\b",
    r"\btransform(?:s|ed)?\b",
    r"\bconvert(?:s|ed)?\b",
    r"\bimport(?:s|ed)?\b",
    r"\bdownload(?:s|ed)?\b",
    r"\bupload(?:s|ed)?\b",
    r"\binstall(?:s|ed)?\b",
    r"\bdeploy(?:s|ed)?\b",
    r"\bpush(?:es|ed)?\b",
    r"\bpull(?:s|ed)?\b",
    r"\bsync(?:s|ed)?\b",
    r"\breload(?:s|ed)?\b",
    r"\brefresh(?:es|ed)?\b",
    r"\bcache(?:s|d)?\b",
    r"\bqueue(?:s|d)?\b",
    r"\bschedule(?:s|d)?\b",
    r"\bsearch(?:es|ed)?\b",
    r"\bmatch(?:es|ed)?\b",
    r"\bfetch(?:es|ed)?\b",
    r"\bquery\b",
    r"\bqueries\b",
    r"\bqueried\b",
    r"\bwrap(?:s|ped)?\b",
    r"\bexpand(?:s|ed)?\b",
    r"\bcollapse(?:s|d)?\b",
    r"\bcopy\b",
    r"\bcopies\b",
    r"\bcopied\b",
    r"\bpaste(?:s|d)?\b",
    r"\bmove(?:s|d)?\b",
    r"\breorder(?:s|ed)?\b",
    r"\bgroup(?:s|ed)?\b",
    r"\bungroup(?:s|ed)?\b",
    r"\bcombine(?:s|d)?\b",
    r"\bmerge(?:s|d)?\b",
    r"\bsplit(?:s)?\b",
    r"\bdivide(?:s|d)?\b",
    r"\bjoin(?:s|ed)?\b",
    r"\bselect(?:s|ed)?\b",
    r"\bchoose(?:s|d)?\b",
    r"\bchose\b",
    r"\bchosen\b",
    r"\bclick(?:s|ed)?\b",
    r"\btap(?:s|ped)?\b",
    r"\bscroll(?:s|ed)?\b",
    r"\btype(?:s|d)?\b",
    r"\benter(?:s|ed)?\b",
    r"\bexecute(?:s|d)?\b",
    r"\binvoke(?:s|d)?\b",
    r"\bcall(?:s|ed)?\b",
    r"\bpresent(?:s|ed)?\b",
    r"\breport(?:s|ed)?\b",
    r"\bwarn(?:s|ed)?\b",
    r"\berror(?:s|ed)?\b",
    r"\braise(?:s|d)?\b",
    r"\bthrow(?:s)?\b",
    r"\bthrew\b",
    r"\bthrown\b",
    r"\bcatch(?:es|ed)?\b",
    r"\bcaught\b",
    r"\bretry\b",
    r"\bretries\b",
    r"\bretried\b",
    r"\btimeout(?:s|ed)?\b",
    r"\bexpire(?:s|d)?\b",
    r"\bexpired\b",
    r"\bcheck(?:s|ed)?\b",
    r"\bverify\b",
    r"\bverifies\b",
    r"\bverified\b",
    r"\bensure(?:s|d)?\b",
    r"\bguarantee(?:s|d)?\b",
    r"\bassert(?:s|ed)?\b",
    r"\btest(?:s|ed)?\b",
    r"\bprove(?:s|d)?\b",
    r"\bproved\b",
    r"\bproven\b",
    r"\bshow(?:s|ed)?\b",
    r"\bdemonstrate(?:s|d)?\b",
    r"\billustrate(?:s|d)?\b",
    r"\bindicate(?:s|d)?\b",
    r"\bsuggest(?:s|ed)?\b",
    r"\bimply\b",
    r"\bimplies\b",
    r"\bimplied\b",
    r"\bdescribe(?:s|d)?\b",
    r"\bexplain(?:s|ed)?\b",
    r"\bdefine(?:s|d)?\b",
    r"\boutput(?:s|ed)?\b",
    r"\binput(?:s|ed)?\b",
    r"\bparse(?:s|d)?\b",
    r"\bformat(?:s|ted)?\b",
    r"\bencode(?:s|d)?\b",
    r"\bdecode(?:s|d)?\b",
    r"\bencrypt(?:s|ed)?\b",
    r"\bdecrypt(?:s|ed)?\b",
    r"\bcompress(?:es|ed)?\b",
    r"\bdecompress(?:es|ed)?\b",
    r"\bstream(?:s|ed)?\b",
    r"\bbuffer(?:s|ed)?\b",
    r"\bbroadcast(?:s|ed)?\b",
    r"\bemit(?:s|ted)?\b",
    r"\blisten(?:s|ed)?\b",
    r"\bpoll(?:s|ed)?\b",
    r"\bwatch(?:es|ed)?\b",
    r"\bobserve(?:s|d)?\b",
    r"\bdetect(?:s|ed)?\b",
    r"\bidentify\b",
    r"\bidentifies\b",
    r"\bidentified\b",
    r"\bclassify\b",
    r"\bclassifies\b",
    r"\bclassified\b",
    r"\brank(?:s|ed)?\b",
    r"\bscore(?:s|d)?\b",
    r"\brate(?:s|d)?\b",
    r"\bgrade(?:s|d)?\b",
    r"\bevaluate(?:s|d)?\b",
    r"\bassess(?:es|ed)?\b",
    r"\breview(?:s|ed)?\b",
    r"\baudits?\b",
    r"\baudited\b",
    r"\bapprove(?:s|d)?\b",
    r"\breject(?:s|ed)?\b",
    r"\bpublish(?:es|ed)?\b",
    r"\barchive(?:s|d)?\b",
    r"\bdelete(?:s|d)?\b",
    r"\bremove(?:s|d)?\b",
    r"\bflag(?:s|ged)?\b",
    r"\btag(?:s|ged)?\b",
    r"\blabel(?:s|ed)?\b",
    r"\bannotate(?:s|d)?\b",
    r"\bhighlight(?:s|ed)?\b",
    r"\blink(?:s|ed)?\b",
    r"\bunlink(?:s|ed)?\b",
    r"\bassign(?:s|ed)?\b",
    r"\bunassign(?:s|ed)?\b",
    r"\bgrant(?:s|ed)?\b",
    r"\brevoke(?:s|d)?\b",
    r"\bauthenticate(?:s|d)?\b",
    r"\bauthorize(?:s|d)?\b",
    r"\bblock(?:s|ed)?\b",
    r"\bunblock(?:s|ed)?\b",
    r"\bban(?:s|ned)?\b",
    r"\bkick(?:s|ed)?\b",
    r"\binvite(?:s|d)?\b",
    r"\bnotify\b",
    r"\bnotifies\b",
    r"\bnotified\b",
    r"\balert(?:s|ed)?\b",
    r"\bremind(?:s|ed)?\b",
    r"\bprompt(?:s|ed)?\b",
    r"\bguide(?:s|d)?\b",
    r"\bdirect(?:s|ed)?\b",
    r"\bredirect(?:s|ed)?\b",
    r"\bforward(?:s|ed)?\b",
    r"\bback(?:s|ed)?\b",
    r"\bapply\b",
    r"\bapplies\b",
    r"\bapplied\b",
    r"\binstantiate(?:s|d)?\b",
    r"\binitialize(?:s|d)?\b",
    r"\bstart(?:s|ed)?\b",
    r"\bstop(?:s|ped)?\b",
    r"\bpause(?:s|d)?\b",
    r"\bresume(?:s|d)?\b",
    r"\bterminate(?:s|d)?\b",
    r"\bshutdown\b",
    r"\brestart(?:s|ed)?\b",
    r"\breset(?:s|ted)?\b",
    r"\bclear(?:s|ed)?\b",
    r"\bflush(?:es|ed)?\b",
    r"\bwipe(?:s|d)?\b",
    r"\bcleanup\b",
    r"\bclean(?:s|ed)?\b",
    r"\bfix(?:es|ed)?\b",
    r"\brepair(?:s|ed)?\b",
    r"\bheal(?:s|ed)?\b",
    r"\brecover(?:s|ed)?\b",
    r"\brestore(?:s|d)?\b",
    r"\bmigrate(?:s|d)?\b",
    r"\bupgrade(?:s|d)?\b",
    r"\bdowngrade(?:s|d)?\b",
    r"\broll(?:s|ed)?\b",
    r"\bscale(?:s|d)?\b",
    r"\bbalance(?:s|d)?\b",
    r"\bthrottle(?:s|d)?\b",
    r"\blimit(?:s|ed)?\b",
    r"\bcap(?:s|ped)?\b",
    r"\bquota\b",
    r"\bexceed(?:s|ed)?\b",
    r"\breach(?:es|ed)?\b",
    r"\bhit(?:s|ting)?\b",
    r"\bpass(?:es|ed)?\b",
    r"\bfail(?:s|ed)?\b",
    r"\berr(?:s|ed)?\b",
    r"\bcrash(?:es|ed)?\b",
    r"\bpanic(?:s|ked)?\b",
    r"\bthrow(?:s)?\b",
    r"\babort(?:s|ed)?\b",
    r"\bcancel(?:s|led)?\b",
    r"\bkill(?:s|ed)?\b",
    r"\bsignal(?:s|ed)?\b",
    r"\binterrupt(?:s|ed)?\b",
    r"\bdispatch(?:es|ed)?\b",
    r"\bqueue(?:s|d)?\b",
    r"\benqueue(?:s|d)?\b",
    r"\bdequeue(?:s|d)?\b",
    r"\bprioritize(?:s|d)?\b",
    r"\bschedule(?:s|d)?\b",
    r"\bdefer(?:s|red)?\b",
    r"\bdelay(?:s|ed)?\b",
    r"\bwait(?:s|ed)?\b",
    r"\bblock(?:s|ed)?\b",
    r"\bunblock(?:s|ed)?\b",
    r"\block(?:s|ed)?\b",
    r"\bunlock(?:s|ed)?\b",
    r"\bacquire(?:s|d)?\b",
    r"\brelease(?:s|d)?\b",
    r"\bhold(?:s|ing)?\b",
    r"\bheld\b",
    r"\bdrop(?:s|ped)?\b",
    r"\bpick(?:s|ed)?\b",
    r"\btake(?:s|n)?\b",
    r"\btook\b",
    r"\bgive(?:s|n)?\b",
    r"\bgave\b",
    r"\bpass(?:es|ed)?\b",
    r"\bfetch(?:es|ed)?\b",
    r"\bget(?:s)?\b",
    r"\bgot\b",
    r"\bput(?:s|ting)?\b",
    r"\bstore(?:s|d)?\b",
    r"\bload(?:s|ed)?\b",
    r"\bread(?:s)?\b",
    r"\bwrite(?:s|n)?\b",
    r"\bwrote\b",
    r"\bopen(?:s|ed)?\b",
    r"\bclose(?:s|d)?\b",
    r"\bmap(?:s|ped)?\b",
    r"\bfilter(?:s|ed)?\b",
    r"\breduce(?:s|d)?\b",
    r"\baggregate(?:s|d)?\b",
    r"\bcollect(?:s|ed)?\b",
    r"\baccumulate(?:s|d)?\b",
    r"\bcount(?:s|ed)?\b",
    r"\bsum(?:s|med)?\b",
    r"\baverage(?:s|d)?\b",
    r"\bcalculate(?:s|d)?\b",
    r"\bcompute(?:s|d)?\b",
    r"\bplot(?:s|ted)?\b",
    r"\bdraw(?:s|n)?\b",
    r"\bdrew\b",
    r"\brender(?:s|ed)?\b",
    r"\bpaint(?:s|ed)?\b",
    r"\bdisplay(?:s|ed)?\b",
    r"\bshow(?:s|n)?\b",
    r"\bhide(?:s|d)?\b",
    r"\bhid\b",
    r"\btoggle(?:s|d)?\b",
    r"\bswitch(?:es|ed)?\b",
    r"\bflip(?:s|ped)?\b",
    r"\brotate(?:s|d)?\b",
    r"\btranslate(?:s|d)?\b",
    r"\btransform(?:s|ed)?\b",
    r"\bresize(?:s|d)?\b",
    r"\bscale(?:s|d)?\b",
    r"\bzoom(?:s|ed)?\b",
    r"\bpan(?:s|ned)?\b",
    r"\bfocus(?:es|ed)?\b",
    r"\bblur(?:s|red)?\b",
    r"\bfade(?:s|d)?\b",
    r"\banimate(?:s|d)?\b",
    r"\btransition(?:s|ed)?\b",
    r"\bmorph(?:s|ed)?\b",
    r"\bslide(?:s|d)?\b",
    r"\bscroll(?:s|ed)?\b",
    r"\bdrag(?:s|ged)?\b",
    r"\bdrop(?:s|ped)?\b",
    r"\bresize(?:s|d)?\b",
    r"\bexpand(?:s|ed)?\b",
    r"\bcollapse(?:s|d)?\b",
    r"\bminimize(?:s|d)?\b",
    r"\bmaximize(?:s|d)?\b",
    r"\bfullscreen\b",
    r"\bpopup\b",
    r"\bmodal\b",
    r"\btoast\b",
    r"\bbanner\b",
    r"\bsnackbar\b",
    r"\bdialog\b",
    r"\bsidebar\b",
    r"\bdrawer\b",
    r"\bpanel\b",
    r"\btab\b",
    r"\baccordion\b",
    r"\bcarousel\b",
    r"\bslider\b",
    r"\bproduces?\b",
    r"\boutputs?\b",
    r"\byields?\b",
    r"\breturns?\b",
    r"\bemits?\b",
]


def _is_falsifiable(claim: str) -> bool:
    """Return True if the claim is falsifiable (not vacuous marketing copy).

    A claim is NOT falsifiable if:
    1. It is empty or whitespace-only.
    2. It contains any banned marketing phrase.
    3. It contains no verb (no observable action or result).
    """
    stripped = claim.strip()
    if not stripped:
        return False

    # Check for banned phrases (case-insensitive)
    lower = stripped.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lower:
            return False

    # Must contain at least one verb-like token
    for pattern in _VERB_PATTERNS:
        if re.search(pattern, stripped, re.IGNORECASE):
            return True

    return False


def _load_spec(
    spec_obj_or_path: Any,
) -> tuple[UnifiedSpec | None, Path | None, str | None]:
    """Load and parse a UnifiedSpec.

    Returns (spec, spec_path, error_message).
    On failure, spec is None and error_message is non-empty.
    """
    if spec_obj_or_path is None:
        return None, None, "spec_obj_or_path is None"

    if isinstance(spec_obj_or_path, UnifiedSpec):
        return spec_obj_or_path, None, None

    if isinstance(spec_obj_or_path, (str, Path)):
        path = Path(spec_obj_or_path)
        if not path.exists():
            return None, path, f"File not found: {path}"
        try:
            text = path.read_text()
            if path.suffix.casefold() == ".json":
                raw = json.loads(text)
            else:
                raw = yaml.safe_load(text)
        except Exception as exc:
            return None, path, f"Could not read/parse file: {exc}"
        try:
            from pydantic import ValidationError

            spec = UnifiedSpec.model_validate(raw)
            return spec, path, None
        except Exception as exc:
            # Return None + path so validate() can produce the structured error
            return None, path, None  # let validate() handle pydantic errors

    # dict or other mapping → pass directly to validate
    return None, None, None  # let validate() handle it


def spec_qa(
    spec_obj_or_path: Any,
    why_brief_path: str | None = None,
) -> Verdict:
    """Run structural QA on a UnifiedSpec.

    Delegates structural + semantic rules to ``validate("unified_spec", ...)``
    (which covers persona-defined, provenance-to-spine-id, and required-field
    checks), then adds QA-specific falsifiability checks on every
    ``Scene.concept_claim`` that ``validate`` does not enforce.

    Parameters
    ----------
    spec_obj_or_path:
        Either a ``UnifiedSpec`` instance, a ``Path`` / string path to a
        YAML or JSON file containing a UnifiedSpec, or a plain dict.
    why_brief_path:
        Optional explicit path to the why_brief file.  When supplied and the
        spec has a relative ``why_brief`` field, the validator resolves
        provenance against this file.  (Currently passed for documentation /
        future use; the core provenance check is done by validate() using the
        spec file's own ``why_brief`` field.)

    Returns
    -------
    Verdict
        ``verdict="pass"`` if all structural rules pass.
        ``verdict="fail"`` with ``blocking_reason`` listing every violation.
        Never raises — missing files and parse/validation errors are returned
        as a ``fail`` Verdict.
    """
    # ------------------------------------------------------------------ guard
    if spec_obj_or_path is None:
        return Verdict(
            schema_version=1,
            dimensions={},
            overall_score=0.0,
            verdict="fail",
            blocking_reason="spec_obj_or_path is None",
            fix_recommendation="Provide a valid UnifiedSpec object or path.",
        )

    # -------------------------------------------------------------- delegate
    # validate() handles loading, Pydantic validation, persona check, and
    # provenance cross-check.  We collect its problems and add our own.
    _ok, _validate_problems = validate("unified_spec", spec_obj_or_path)
    violations: list[str] = list(_validate_problems)

    # ------------------------------------------------- load spec for QA checks
    # We need the parsed spec object to run QA-specific checks.
    # If validate() already failed on loading, we may not be able to parse.
    spec: UnifiedSpec | None = None

    if isinstance(spec_obj_or_path, UnifiedSpec):
        spec = spec_obj_or_path
    elif isinstance(spec_obj_or_path, (str, Path)):
        path = Path(spec_obj_or_path)
        if path.exists():
            try:
                text = path.read_text()
                if path.suffix.casefold() == ".json":
                    raw = json.loads(text)
                else:
                    raw = yaml.safe_load(text)
                from pydantic import ValidationError

                try:
                    spec = UnifiedSpec.model_validate(raw)
                except ValidationError:
                    spec = None  # structural errors already captured via validate()
            except Exception:
                spec = None  # loading errors already captured via validate()
        # else: file not found — validate() already captured the error
    elif isinstance(spec_obj_or_path, dict):
        try:
            spec = UnifiedSpec.model_validate(spec_obj_or_path)
        except Exception:
            spec = None

    # --------------------------------------------------- QA-specific checks
    if spec is not None:
        for scene in spec.scenes:
            claim = scene.concept_claim
            if not _is_falsifiable(claim):
                if not claim.strip():
                    violations.append(
                        f"scene '{scene.title}': concept_claim is empty — "
                        "must describe an observable, falsifiable outcome"
                    )
                else:
                    violations.append(
                        f"scene '{scene.title}': concept_claim is not falsifiable — "
                        f"'{claim[:80]}' uses marketing language or has no verb; "
                        "write a specific, observable outcome instead"
                    )

    # --------------------------------------------------------------- verdict
    if not violations:
        return Verdict(
            schema_version=1,
            dimensions={},
            overall_score=1.0,
            verdict="pass",
            blocking_reason=None,
            fix_recommendation=None,
        )

    blocking_reason = "; ".join(violations)
    return Verdict(
        schema_version=1,
        dimensions={},
        overall_score=0.0,
        verdict="fail",
        blocking_reason=blocking_reason,
        fix_recommendation=(
            "Fix the listed violations before running the concept judge. "
            "Each concept_claim must describe a specific, observable, falsifiable "
            "outcome — e.g. 'Users can filter the task list by status and see only "
            "open tasks' not 'a world-class seamless experience'. "
            "Persona must be defined in the personas dict. "
            "Provenance must match a SpineItem.id in the linked why_brief. "
            "All required fields (name, narrative, base_url, personas, scenes) must be present."
        ),
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print(
            "Usage: python -m scripts.ddd.spec_qa <spec_path> [why_brief_path]",
            file=sys.stderr,
        )
        sys.exit(2)

    _spec_path = sys.argv[1]
    _why_brief_path = sys.argv[2] if len(sys.argv) == 3 else None

    _result = spec_qa(_spec_path, why_brief_path=_why_brief_path)

    if _result.verdict == "pass":
        print("spec_qa: pass")
        sys.exit(0)
    else:
        print("spec_qa: fail")
        print(f"  blocking_reason: {_result.blocking_reason}")
        if _result.fix_recommendation:
            print(f"  fix_recommendation: {_result.fix_recommendation}")
        sys.exit(1)
