---
name: agent-turn-review
description: >
  The fleet-wide pre-send review every agent runs before ANY outbound deliverable / reply / PR.
  Audits the draft against the ORIGINAL request (fidelity) AND against your own capabilities
  (grounded commitments): extract each discrete ask, confirm the draft does exactly that, and
  confirm every "I'll do X" is something you can actually execute. Fix gaps before sending.
  Agents keep a thin `agent-turn-review` skill that invokes this and adds their own send-path +
  paired-reviewer specifics — the general discipline lives here so the fleet stays DRY.
---

# Agent turn review — does the deliverable match the brief, AND can you do what you claim?

The canonical fleet self-review. Run before EVERY outbound action (it is the thing that gets
dropped under load). Agent repos keep a thin `agent-turn-review` extension that invokes this and
adds agent-specifics (send path, paired reviewers); the general discipline lives here once.

## A. Fidelity — does the work match what was asked?
1. **Re-read the original request** — the actual message, not your memory of it.
2. **Extract EACH discrete ask** as a numbered checklist, verbatim where possible. Multi-part
   requests hide dropped items — list them ALL.
3. **For each ask, confirm the draft does EXACTLY that** — not a near-miss. Read any source/link
   they cited (open it; don't reconstruct from memory); never substitute your own summary for the
   thing they asked for (the classic: linking your scan when they asked for the report).
4. **Rate it, tough** — faithfulness-to-each-ask / source-verification / completeness / clarity,
   1–5 each, default 3. Anything under 5 on faithfulness → fix before sending.

## B. Grounded commitments — can you actually do what you're claiming?
5. **Scan the deliverable for every forward-looking claim** — "I'll X", "next I'll Y", "before Z
   I'll…". For EACH, name the concrete, executable mechanism (a command, a tool, a specific step)
   and confirm you can actually perform it — this turn or as a real, nameable next action. No
   mechanism and no rough WHEN → it's not a commitment, it's vapor; cut it.
6. **Vague coordination verbs about a PERSON are the red flag** — "sync with / coordinate with /
   loop in / check with / align with / run it by <someone>". They almost always hide a human
   dependency you have NO channel to execute, dressed up as a plan. Either **(a) convert it to
   something you can run** — the specific dedup check (open PRs + branches touching the exact files
   you'll change), or an explicit **draft-then-ask** message you will actually send via your
   sanctioned send path — or **(b) cut the claim.** Never promise a human-in-the-loop step you
   have no way to perform.
   - Running the concrete check often **CORRECTS a false premise** — grounding a claim surfaces
     facts, not just honesty. Origin: an agent wrote "I'll sync with Sarvesh, audit's a hot area";
     the check showed the feature lived in a different repo with zero in-flight PRs — wrong repo
     AND no conflict. (Jonathan, 2026-07-08.)

## C. Presentation
7. **Lead with what you DID** + your recommendation + what else we could do — not junior questions.
8. **Enumerate multiple asks**, one line each, showing how each was handled (✓ done / link / status).
9. **Substantial artifacts go in a shared doc the reply links** — never a wall of pasted text,
   never a loose local file; present the reply body itself inline for approval.
10. **Verify recipients** from the structured reader / `--reply-all`, never a raw text mail view
    (it hides `Cc:`). Confirm reply-all vs. direct on purpose.

## D. Revision check — full re-review + repetition pass, EVERY revision

> **§D is enforced for email, because it is the step that fails.** `canopy email send` blocks any
> body without a review receipt fingerprinted to THAT body, so a review of v1 cannot satisfy a send
> of v3 — revise, and the receipt stops matching. Record yours after reviewing:
> `canopy email review-receipt --repo . --body-file <the body you'll send> --caught "<findings>"`.
> Dry-runs are exempt. The `caught` list is the fleet's evidence about which reviews earn their
> keep — an honest "none" is fine, but only per §13 (after you have actually read it back).
11. **Re-run this whole review on every revision of a draft, not only the first.** A "delta check"
    of just your latest edits is how edit-introduced defects ship — the requester's corrections
    change the draft's context, so the whole thing gets re-reviewed.
12. **Then read the FULL draft top to bottom with fresh eyes for repetition:** the same phrase or
    fragment twice ("proposal… My proposal"), the same content announced twice (intro names the
    extras AND a later section re-introduces them), the same term leaned on 3+ times. Fix by
    varying or cutting — one announcement, one detail pass, per fact.
13. **Evidence before assertion — quote, don't claim.** This pass is trivially faked as a checklist:
    reporting "collapsed X, de-duped Y" without doing the read is how the misses survive. Quote each
    repetition you find verbatim; "none found" is valid only after you have read the final paragraph
    back to yourself. (Origin: an agent reported its repetition fixes done, then the requester
    immediately caught four it had missed — Jonathan, 2026-07-13.)

## Adopting it in an agent (the thin extension)
Keep a repo-local `skills/agent-turn-review/SKILL.md` that (a) says "invoke `canopy:agent-turn-review`
and apply it", and (b) lists only agent-specifics: the sanctioned send path (§B's draft-then-ask
target), where the turn gates it, and any paired reviewer (e.g. a `story-review`). The factory
(`canopy create-agent`) scaffolds this thin extension by default.
