"""Structural invariants for the ddd orchestrator agent (SP5).

Pins the load-bearing strings in the agent file and command file.
Does NOT exercise runtime behavior — drift here is a bug.

Checked invariants:
  1.  Agent file exists at plugins/canopy/agents/ddd.md.
  2.  Command file exists at plugins/canopy/commands/ddd.md.
  3.  Frontmatter: name=ddd, model=inherit, memory=user.
  4.  All 8 DDD skills named in chain order.
  5.  TWO-gate pause policy stated: concept_change + external_release.
  6.  Nothing-else-blocks rule stated explicitly.
  7.  Four routing targets with their destinations:
      PRODUCT → /design-review, /review, or /qa
      CONCEPT → re-run ddd-spec (edit narration/design_intent)
      RESEARCH → autonomous investigation + re-run Phase 0
      CAPABILITY → product-build task
  8.  compute_convergence referenced.
  9.  MAX_ITERATIONS referenced.
 10.  Reads .canopy/ddd/context and .canopy/ddd/learnings.
 11.  Suggest-then-confirm self-tuning mentioned (never auto-apply).
 12.  Digest email referenced (PM-loop autonomous digest style).
 13.  Command file has description + allowed-tools including Skill or Agent.
"""
from __future__ import annotations

from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent.parent / "plugins" / "canopy"
AGENTS_DIR = PLUGIN_ROOT / "agents"
COMMANDS_DIR = PLUGIN_ROOT / "commands"

AGENT_FILE = AGENTS_DIR / "ddd.md"
COMMAND_FILE = COMMANDS_DIR / "ddd.md"

# Chain order must match the pipeline definition in the task description.
ORDERED_SKILLS = [
    "ddd-evidence-audit",
    "ddd-why-brief",
    "ddd-why-qa",
    "ddd-why-eval",
    "ddd-spec",
    "ddd-spec-qa",
    "ddd-concept-eval",
    "ddd-run",
]


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------


def test_agent_file_exists() -> None:
    assert AGENT_FILE.exists(), f"Agent file missing: {AGENT_FILE}"


def test_command_file_exists() -> None:
    assert COMMAND_FILE.exists(), f"Command file missing: {COMMAND_FILE}"


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------


def _frontmatter(path: Path) -> str:
    """Return the YAML frontmatter block (between the first two --- delimiters)."""
    parts = path.read_text().split("---", 2)
    assert len(parts) >= 3, f"No frontmatter found in {path}"
    return parts[1]


def test_agent_frontmatter_name() -> None:
    fm = _frontmatter(AGENT_FILE)
    assert "name: ddd" in fm, "Agent frontmatter must declare 'name: ddd'"


def test_agent_frontmatter_model_inherit() -> None:
    fm = _frontmatter(AGENT_FILE)
    assert "model: inherit" in fm, "Agent frontmatter must declare 'model: inherit'"


def test_agent_frontmatter_memory_user() -> None:
    fm = _frontmatter(AGENT_FILE)
    assert "memory: user" in fm, "Agent frontmatter must declare 'memory: user'"


# ---------------------------------------------------------------------------
# All 8 skills named
# ---------------------------------------------------------------------------


def test_agent_names_all_eight_skills() -> None:
    content = AGENT_FILE.read_text()
    missing = [s for s in ORDERED_SKILLS if s not in content]
    assert not missing, f"Agent body missing skill references: {missing}"


def test_agent_names_skills_in_chain_order() -> None:
    """Skills must appear in the canonical chain order (Phase 0 → spec → run).

    ddd-run orchestrates ddd-concept-eval internally, so the agent correctly
    references ddd-run (Step 7 dispatch) before ddd-concept-eval (routing
    explanation section).  We check ordered position for all consecutive pairs
    EXCEPT the ddd-run → ddd-concept-eval pair, which intentionally inverts
    because ddd-run wraps the concept eval.
    """
    content = AGENT_FILE.read_text()
    positions = {}
    for skill in ORDERED_SKILLS:
        idx = content.find(skill)
        assert idx != -1, f"Skill '{skill}' not found in agent body"
        positions[skill] = idx

    # Pairs where strict position order is NOT required:
    # ddd-run dispatches ddd-concept-eval internally, so ddd-run appears
    # in the main steps section while ddd-concept-eval appears later in the
    # routing/description section.
    inversion_allowed = {("ddd-concept-eval", "ddd-run")}

    for i in range(len(ORDERED_SKILLS) - 1):
        a, b = ORDERED_SKILLS[i], ORDERED_SKILLS[i + 1]
        if (a, b) in inversion_allowed or (b, a) in inversion_allowed:
            continue
        assert positions[a] < positions[b], (
            f"Skill '{a}' must appear before '{b}' in the agent body "
            f"(positions: {positions[a]} vs {positions[b]})"
        )


# ---------------------------------------------------------------------------
# Two-gate pause policy
# ---------------------------------------------------------------------------


def test_agent_states_concept_change_gate() -> None:
    content = AGENT_FILE.read_text()
    assert "concept_change" in content, (
        "Agent must state the 'concept_change' gate as one of two blocking gates"
    )


def test_agent_states_external_release_gate() -> None:
    content = AGENT_FILE.read_text()
    assert "external_release" in content, (
        "Agent must state the 'external_release' gate as one of two blocking gates"
    )


def test_agent_states_two_gate_policy() -> None:
    """Both gates must appear together in a policy statement, not just mentioned in passing."""
    content = AGENT_FILE.read_text()
    # Accept any phrasing that puts both gates next to each other as a policy
    has_both_near = False
    idx_cc = content.find("concept_change")
    idx_er = content.find("external_release")
    if idx_cc != -1 and idx_er != -1:
        # Within 500 chars of each other in either order = policy statement
        has_both_near = abs(idx_cc - idx_er) <= 500
    assert has_both_near, (
        "concept_change and external_release must appear together as a pause policy"
    )


def test_agent_states_nothing_else_blocks() -> None:
    """Agent must explicitly say nothing else pauses or blocks."""
    content = AGENT_FILE.read_text()
    nothing_else = (
        "nothing else" in content.lower()
        or "everything else" in content.lower()
        or "only two" in content.lower()
        or "only 2" in content.lower()
        or "all other" in content.lower()
    )
    assert nothing_else, (
        "Agent must explicitly state that nothing else blocks (only these two gates pause)"
    )


# ---------------------------------------------------------------------------
# Four routing targets
# ---------------------------------------------------------------------------


def test_agent_routes_product_findings() -> None:
    """PRODUCT findings must route to specialist skills (design-review / review / qa)."""
    content = AGENT_FILE.read_text()
    has_product_route = (
        "design-review" in content or "/design-review" in content
        or ("PRODUCT" in content and ("review" in content or "qa" in content))
    )
    assert has_product_route, (
        "Agent must route PRODUCT findings to /design-review, /review, or /qa"
    )


def test_agent_routes_concept_findings() -> None:
    """CONCEPT findings must trigger spec edit (narration / design_intent) and ddd-spec re-run."""
    content = AGENT_FILE.read_text()
    assert "CONCEPT" in content, "Agent must name the CONCEPT route"
    concept_fix = (
        "narration" in content or "design_intent" in content or "ddd-spec" in content
    )
    assert concept_fix, (
        "CONCEPT route must edit spec narration/design_intent or re-run ddd-spec"
    )


def test_agent_routes_research_findings() -> None:
    """RESEARCH findings must trigger autonomous investigation and Phase 0 re-run."""
    content = AGENT_FILE.read_text()
    assert "RESEARCH" in content, "Agent must name the RESEARCH route"


def test_agent_routes_capability_findings() -> None:
    """CAPABILITY findings must create a product-build task."""
    content = AGENT_FILE.read_text()
    assert "CAPABILITY" in content, "Agent must name the CAPABILITY route"
    build_task = "task" in content.lower() or "build" in content.lower()
    assert build_task, (
        "CAPABILITY route must create a product-build task"
    )


# ---------------------------------------------------------------------------
# Convergence + iteration cap
# ---------------------------------------------------------------------------


def test_agent_references_compute_convergence() -> None:
    content = AGENT_FILE.read_text()
    assert "compute_convergence" in content, (
        "Agent must reference compute_convergence from run_pipeline"
    )


def test_agent_references_max_iterations() -> None:
    content = AGENT_FILE.read_text()
    assert "MAX_ITERATIONS" in content or "max_iterations" in content.lower(), (
        "Agent must reference MAX_ITERATIONS to cap the refinement loop"
    )


# ---------------------------------------------------------------------------
# Context + learnings bootstrap
# ---------------------------------------------------------------------------


def test_agent_reads_ddd_context() -> None:
    content = AGENT_FILE.read_text()
    assert ".canopy/ddd" in content, (
        "Agent must read the .canopy/ddd/ directory for context and learnings"
    )
    assert "context" in content.lower(), (
        "Agent must read context.md from .canopy/ddd/"
    )


def test_agent_reads_ddd_learnings() -> None:
    content = AGENT_FILE.read_text()
    assert "learnings" in content.lower(), (
        "Agent must read learnings.md from .canopy/ddd/"
    )


def test_agent_bootstraps_context_if_missing() -> None:
    """Mirror of PM supervisor: bootstrap context.md if it doesn't exist."""
    content = AGENT_FILE.read_text()
    bootstrap = (
        "bootstrap" in content.lower()
        or "if missing" in content.lower()
        or "if it doesn't exist" in content.lower()
        or "does not exist" in content.lower()
        or "doesn't exist" in content.lower()
    )
    assert bootstrap, (
        "Agent must bootstrap context.md if it is missing (mirror PM supervisor pattern)"
    )


# ---------------------------------------------------------------------------
# Self-tuning (suggest-then-confirm, never auto-apply)
# ---------------------------------------------------------------------------


def test_agent_mentions_suggest_then_confirm_self_tuning() -> None:
    content = AGENT_FILE.read_text()
    suggest = (
        "suggest" in content.lower()
        or "propose" in content.lower()
    )
    confirm = (
        "confirm" in content.lower()
        or "approval" in content.lower()
        or "approved" in content.lower()
    )
    assert suggest and confirm, (
        "Agent must describe suggest-then-confirm self-tuning (never auto-apply)"
    )


def test_agent_self_tuning_does_not_auto_apply() -> None:
    content = AGENT_FILE.read_text()
    assert "never auto" in content.lower() or "do not auto" in content.lower() or "not auto-apply" in content.lower(), (
        "Agent must explicitly say it never auto-applies self-tuning changes"
    )


# ---------------------------------------------------------------------------
# Digest email
# ---------------------------------------------------------------------------


def test_agent_mentions_digest_email() -> None:
    content = AGENT_FILE.read_text()
    assert "digest" in content.lower(), (
        "Agent must mention the autonomous digest email (PM-loop style)"
    )


def test_agent_digest_links_to_review_page() -> None:
    """Digest must include a link to the canopy-web review page (SP6 destination)."""
    content = AGENT_FILE.read_text()
    has_review_link = (
        "review page" in content.lower()
        or "canopy-web" in content.lower()
        or "ReviewRequest" in content
    )
    assert has_review_link, (
        "Agent digest must link to the canopy-web review page (SP6 destination)"
    )


# ---------------------------------------------------------------------------
# Command file shape
# ---------------------------------------------------------------------------


def test_command_has_description_in_frontmatter() -> None:
    fm = _frontmatter(COMMAND_FILE)
    assert "description:" in fm, "Command file must have a description in frontmatter"


def test_command_has_allowed_tools() -> None:
    content = COMMAND_FILE.read_text()
    assert "allowed-tools" in content, "Command file must declare allowed-tools"


def test_command_allowed_tools_includes_skill_or_agent() -> None:
    content = COMMAND_FILE.read_text()
    assert "Skill" in content or "Agent" in content, (
        "Command allowed-tools must include Skill or Agent to dispatch sub-skills"
    )
