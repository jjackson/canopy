# Agent runtime + secrets — the fleet-canonical config standard

> **Fleet-canonical process (canopy agent-core).** How an agent declares what it needs to run,
> and where every configuration value lives. The system is the **Agent Runtime Registry**
> (design: `canopy-web/docs/superpowers/specs/2026-07-20-agent-runtime-registry-design.md`;
> schema + reconciler: `canopy-web/packages/canopy_runtime/`). This doc is the *agent-author's*
> view — what to put where when you add a new secret or config value.

## The one rule

**No environment-specific value lives in git.** Not a password, not an API key — and *also not*
a Drive folder id, doc id, sheet id, or mailbox. The fleet runs in **multiple environments**
(your laptop, the cloud runner, a fresh box), and those ids differ per environment/Workspace.
A literal committed to a repo can't vary; a vault reference can. **1Password is the single
source of truth**, resolved identically on a laptop and in the cloud.

"It isn't sensitive" is **not** the test. The test is **"does this value differ between
environments?"** If yes → vault.

## Two-tier vault topology

| Vault | Holds |
|---|---|
| `Canopy-Shared` | values **every** canopy agent resolves (`gog-oauth-client`, `github-token`, `gdrive-shared-root`) |
| `Agent-<Slug>` | one per agent — its identity + integration values (`canopy-pat`, `claude-oauth-token`, `gog-token`, `gdrive-root-folder`, …) |

The reconciler resolves each reference against **`[Agent-<Slug>, Canopy-Shared]` in order**, so a
per-agent item **shadows** the shared one with no special-casing (that's how Echo runs its own
`gog-oauth-client` while everyone else uses the shared app). **The repo never names a vault** —
the topology is convention, not config.

Every item is an **API Credential** whose value sits in a single `credential` field, so a
reference resolves as `op://<vault>/<item>/credential`.

## `runtime.yaml` — the agent's self-declaration

Each agent ships a `runtime.yaml` in its own repo: plugins, tools, engine preference, the values
it needs (**by reference name only**), and the preflight that defines "ready". It is reviewed in
the agent's own PRs like a `package.json`, and **never contains a value**.

```yaml
secrets:
  - name: canopy-pat            # → op://Agent-<Slug>/canopy-pat/credential
    env: CANOPY_PAT
  - name: gdrive-root-folder    # the agent's <Agent> folder in the shared AI-Agents drive
    env: GDRIVE_ROOT_FOLDER
  - name: gog-oauth-client      # falls through to Canopy-Shared if not in the agent vault
    path: ~/.config/gogcli/credentials-<slug>.json
    optional: true
```

- `env:` injects the resolved value into that variable; `path:` writes it to a file (a gog
  credentials JSON). `optional: true` means absence is skipped rather than a "needs bootstrap" gap.
- The spec's separate top-level **`env:` block is for genuinely fixed, environment-invariant
  literals only.** In practice almost nothing qualifies — if it's an id, it varies per
  environment, so it belongs in `secrets:`. (Echo originally carried its Drive/doc ids as inline
  `env:` literals; they were moved into `Agent-Echo` for exactly this reason.)

## How values reach a turn

```
canopy-reconcile --agent <slug>
   ▼  read the repo's runtime.yaml (the declarative WHAT)
   ▼  resolve each secrets[] name against [Agent-<Slug>, Canopy-Shared]
   ▼  scan the box → diff vs. spec → apply only the gaps
   ▼  run the preflight
   └▶ inject env / write files, then run the turn
```

`python -m canopy_runtime.cli --agent <slug> [--print-env | --env-file F | --exec CMD…]` is the
reconciler's operational face — **the same command on a laptop and a cloud box**. The reconciler
holds the 1Password service-account token and resolves values into the engine's process env
*before* the turn — the model never handles raw credentials.

## Adding a new value (the recipe)

1. **Put it in the vault** — agent-specific → `Agent-<Slug>`; needed by every agent → `Canopy-Shared`:
   ```bash
   op item create --category "API Credential" --title "<name>" \
     --vault "Agent-<Slug>" "credential[password]=<value>"
   # already exists? edit instead:
   op item edit "<name>" --vault "Agent-<Slug>" "credential=<value>"
   ```
2. **Declare it** in the agent's `runtime.yaml` `secrets:` with the `env:`/`path:` its tools expect.
3. **Read it** in code/skills as the env var — never re-hardcode the value.
4. **Verify** it resolves: `op read "op://Agent-<Slug>/<name>/credential"`.

`deploy/secrets/bootstrap_1password.sh <slug…>` (canopy-web) idempotently creates the vaults +
placeholder items for a new agent; `migrate_echo.sh` is the worked example of copying values out
of the legacy flat `AI-Agents` vault.

## Rollout status (2026-07-23)

- **Vaults:** `Canopy-Shared` + `Agent-{Ace,Ada,Echo,Eva,Hal}` all exist, each with
  `canopy-pat` / `claude-oauth-token` / `gog-token` and now `gdrive-root-folder`.
- **`runtime.yaml`:** shipped for **Echo**; the other agents still need one (until then their
  values are resolvable in the vault but nothing declares them, so a turn won't auto-inject them).
- **Legacy:** the flat `AI-Agents` vault is still populated and untouched — migrate, don't trust
  it as the source of truth. `config/secrets.yaml` + `canopy provision` are the older imperative
  path that `runtime.yaml` + the reconciler supersede for the runtime layer.

## Related

- `deliverables.md` — the Drive filing standard; its `<Agent>` root is `$GDRIVE_ROOT_FOLDER`, a
  vault-resolved value under this standard.
- `turn.md` — the turn procedure the reconciler makes "ready".
