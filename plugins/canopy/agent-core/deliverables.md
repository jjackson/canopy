# Deliverables → Drive — the fleet-canonical filing standard

> **Fleet-canonical process (canopy agent-core).** Every agent that publishes a work product to
> Google Drive follows this. Your agent's `gdoc-writer` (or equivalent publishing skill) is a thin
> stub that (a) points here and (b) declares your agent-specifics: your shared **Projects root**
> folder id and the exact publishing mechanism you use. To change THIS standard for the whole
> fleet, PR canopy (`plugins/canopy/agent-core/deliverables.md` + `canopy version bump`).

A deliverable is any work product a human is meant to read, review, or keep — a brief, a draft,
a concept note, a research summary, a form submission. The point of publishing it is that the team
can **find it, comment on it, and rely on it surviving.** A doc in the agent's personal My Drive
root serves none of that: it's invisible to the team and dies with the agent identity.

## The rule (non-negotiable)

1. **Never My Drive root. Never a loose local file.** Every deliverable lands in the agent's
   **shared Projects area**, owned or co-owned such that the team can reach it.
2. **One subfolder per project.** Deliverables are filed in a **per-project subfolder** under the
   agent's shared **Projects root** (`<Agent> Projects`), NOT dumped flat in the root.
   - **Reuse** the project's existing folder if one already exists (search the root first).
   - **Create** the subfolder if it doesn't — name it for the project / counterpart / initiative,
     stable across sessions so the next turn re-uses it.
3. **Share with the requester, then CONFIRM — before you hand over the link.** A raw Drive link
   grants no access; and the agent's `@dimagi-ai.com` mailbox is a *different domain* from a
   `@dimagi.com` recipient, so a doc is a **dead link** to them until explicitly shared. Share the
   subfolder (or at least the doc) with the requester + any named recipients, then verify the
   recipient actually appears in the permission list before sending the link. Broader/link-anyone
   sharing still follows the outbound gate; sharing the deliverable with the human who requested it
   is part of delivery, not a separate favor.
4. **Link, don't paste.** Chat/email carry the doc **link** + a 1–2 line summary — never a wall of
   pasted text, never "it's in a local file."

## Why this is enforced, not just written

Per the operating model, hard behavioral rules don't live in prose alone — prose relies on the
model choosing to comply, which fails under load (origin: 2026-07-20, an agent created a brief in
My Drive root and handed the requester a link they couldn't open — the doc was fine, the filing +
share were skipped). So the "never My Drive root" invariant is a **fleet-baseline gating rail** for
the tool where the mistake happens:

- Agents that publish with **`gog drive upload`** mount the **`gws`** channel in their
  `config/gating.json` `channels` list. The baseline rail then blocks a converting upload that has
  no `--parent` (i.e. a doc headed for My Drive root) and names the right path.
- Agents whose publishing **helper always parents into the shared root** (e.g. a `bin/*_gdoc.py`
  that defaults `--parent` to a shared-drive folder id) are compliant **by construction** — the
  parentless path is unreachable — so they need the guidance here but not the rail.

## What each agent's `gdoc-writer` stub declares

- **Shared Projects root** — the folder id everything files under (e.g. Eva → `Eva Projects`;
  Echo → its Connect-Marketing folder). Owned/shared so the team can reach it.
- **Publishing mechanism** — the exact command (`gog drive upload --convert --parent <subfolder>`,
  or `bin/<slug>_gdoc.py --parent …`), plus the render-verify + share-verify steps.
- **Whether it mounts the `gws` rail** — yes if it uses `gog drive upload`; not needed if its
  helper always parents.

## Related

- `turn.md` — the turn procedure; its reply-quality rules already say deliverables are gdocs, not
  local files. This doc is the *filing* standard behind that.
- your agent's `gdoc-writer` — the thin per-agent stub that implements this.
