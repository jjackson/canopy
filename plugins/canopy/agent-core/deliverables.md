# Agent storage → the shared AI-Agents drive — the fleet-canonical filing standard

> **Fleet-canonical process (canopy agent-core).** Every agent files what it produces and what it
> must remember into **one shared Google Drive**, in a fixed per-agent layout. Your agent's
> `gdoc-writer` (or equivalent publishing skill) is a thin stub that (a) points here and (b)
> declares your agent-specifics: your Drive root (vault-resolved, see below) and the exact
> publishing mechanism. To change THIS standard for the whole fleet, PR canopy
> (`plugins/canopy/agent-core/deliverables.md` + `canopy version bump`).

There are two kinds of thing an agent keeps outside its repo, and both live in the same shared
place so the team can find them and they survive across turns/worktrees:

- **Deliverables** — any work product a human is meant to read, review, or keep (a brief, a draft,
  a concept note, a research summary, a form submission). The point of publishing is that the team
  can **find it, comment on it, and rely on it surviving.**
- **Process state** — the durable operational memory a recurring job needs across turns (a
  meeting-prep tracker so prep isn't duplicated, a run log, a registry). A repo-local file is the
  wrong home: a fresh worktree/branch each turn recreates or loses it.

A doc in the agent's personal My Drive root, or a loose local file, serves neither: it's invisible
to the team and dies with the agent identity / the worktree.

## The shared layout (non-negotiable)

**One shared root — `AI-Agents` (`1EgS0aqdOgjlmOjTsn6IYHQP_N9kDjLrO`)** — holds **one top-level
folder per agent** (`Ace/`, `Ada/`, `Echo/`, `Eva/`, `Hal/`, …). Each agent's folder is its
Drive root — resolved from its own 1Password vault, never committed — and under it sit two
standing areas (more may be added
as we learn what agents need to keep):

```
AI-Agents/  (1EgS0aqdOgjlmOjTsn6IYHQP_N9kDjLrO)
└── <Agent>/                     ← $GDRIVE_ROOT_FOLDER (op://Agent-<Slug>/gdrive-root-folder)
    ├── Projects/                ← deliverables, ONE subfolder per project/task
    │   └── <Project or counterpart>/   ← reuse across turns; never dump flat in Projects/
    └── Process State/           ← durable trackers / run logs / registries
```

1. **Never My Drive root. Never a loose local file. Never flat at the shared root.** Everything
   lands under **your `<Agent>/` folder**, owned/co-owned so the team can reach it. Work dumped
   directly under `AI-Agents/` (not inside an agent folder) is the exact mistake this layout fixes.
2. **One subfolder per project.** Deliverables file into a **per-project subfolder** under
   `<Agent>/Projects/`, NOT flat in `Projects/`.
   - **Reuse** the project's existing folder if one exists (search first); **iterate the same doc
     in place** rather than spawning a new doc each turn (`--replace <id>` keeps the link stable).
   - **Create** the subfolder if it doesn't — name it for the project / counterpart / initiative,
     stable across sessions so the next turn re-uses it.
3. **Process state goes in `Process State/`.** A recurring job's tracker/registry/run-log is a
   Drive artifact under `<Agent>/Process State/`, so it persists across turns and isn't duplicated.
4. **Share with the requester, then CONFIRM — before you hand over the link.** A raw Drive link
   grants no access; and the agent's `@dimagi-ai.com` mailbox is a *different domain* from a
   `@dimagi.com` recipient, so a doc is a **dead link** to them until explicitly shared. Share the
   subfolder (or at least the doc) with the requester + any named recipients, then verify the
   recipient actually appears in the permission list before sending the link. Broader/link-anyone
   sharing still follows the outbound gate; sharing the deliverable with the human who requested it
   is part of delivery, not a separate favor.
5. **Link, don't paste.** Chat/email carry the doc **link** + a 1–2 line summary — never a wall of
   pasted text, never "it's in a local file."

**ACE is the one carve-out.** ACE already files opportunity artifacts into its own working Drive
locations — **do not override those.** ACE's *agentic* storage (ad-hoc projects, process state) may
also live under `Ace/` here; its opportunity pipeline stays where it is.

## How you file (the `canopy gdoc` engine does the layout for you)

The shared `canopy gdoc` engine resolves the layout from your Drive root — you name the
project, it finds-or-creates the subfolder:

```bash
# a deliverable → <Agent>/Projects/<project>/  (find-or-create, reused next turn)
canopy gdoc publish --md <file>.md --name "<Doc title>" --project "<Project>" --share domain

# a durable tracker → <Agent>/Process State/
canopy gdoc publish --md <file>.md --name "<Tracker>" --area "Process State"

# iterate in place — same id, same link, same permissions
canopy gdoc publish --md <file>.md --replace <docId>
```

- `--project` files into `Projects/<project>`; `--area "Process State"` (optionally with
  `--project`) files a tracker. `--parent <id>` bypasses resolution when you already have the id.
- Emits JSON `{id, url, shared, verified}` — share the `url`; `verified: true` means the share
  landed. Agents that still publish with raw `gog drive upload` pass `--parent <subfolder-id>`
  explicitly (resolve/create the `<Agent>/Projects/<project>` folder first).

## Why this is enforced, not just written

Per the operating model, hard behavioral rules don't live in prose alone — prose relies on the
model choosing to comply, which fails under load (origin: 2026-07-20, an agent created a brief in
My Drive root and handed the requester a link they couldn't open — the doc was fine, the filing +
share were skipped; 2026-07-23, a fresh session dumped work flat at the shared root instead of
under its agent folder). So the "never My Drive root / never flat at root" invariant is a
**fleet-baseline gating rail** for the tool where the mistake happens:

- Agents that publish with **`gog drive upload`** mount the **`gws`** channel in their
  `config/gating.json` `channels` list. The baseline rail then blocks a converting upload that has
  no `--parent` (i.e. a doc headed for My Drive root) and names the right path.
- Agents whose publishing **helper always parents** into a resolved `<Agent>/Projects/<project>`
  subfolder (e.g. `canopy gdoc --project …`, or a `bin/*_gdoc.py` defaulting `--parent`) are
  compliant **by construction** — the parentless path is unreachable — so they need the guidance
  here but not the rail.

## What each agent's `gdoc-writer` stub declares

- **Your Drive root** — your `<Agent>/` folder id under the shared root. It is **environment-
  specific, so it lives in your agent's 1Password vault**, never in git:
  `op://Agent-<Slug>/gdrive-root-folder/credential`, referenced from your `config/secrets.yaml`
  (or `.env.tpl`) and materialized into `~/.<agent>/.env` as `$GDRIVE_ROOT_FOLDER` by
  `canopy provision`. Everything files beneath it via `Projects/` + `Process State/`.
  See `agent-core/agent-runtime.md`.
- **Publishing mechanism** — the exact command (`canopy gdoc publish --project …`, or
  `gog drive upload --convert --parent <subfolder>`), plus the render-verify + share-verify steps.
- **Whether it mounts the `gws` rail** — yes if it uses raw `gog drive upload`; not needed if it
  publishes through `canopy gdoc` (which always resolves a parent).

## Related

- `turn.md` — the turn procedure; its reply-quality rules already say deliverables are gdocs, not
  local files. This doc is the *filing* standard behind that.
- your agent's `gdoc-writer` — the thin per-agent stub that implements this.
