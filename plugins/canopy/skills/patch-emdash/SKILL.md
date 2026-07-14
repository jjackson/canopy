---
name: patch-emdash
description: Make emdash automation runs appear as live tasks in their project sidebar (not just under Automations). Re-apply after any emdash update, which wipes the patch. Use when canopy-runner-triggered turns don't show live under an agent's project, or right after emdash auto-updates.
---

# Patch emdash for live automation-run tasks

emdash tags automation-created tasks `type='automation-run'`, and its renderer
**hides** those from the project sidebar (they appear only under *Automations*).
The canopy runner triggers agent turns via an emdash automation, so those turns
never show up live under their agent's project — you have to click into
Automations to see them.

This skill flips **one line** in emdash's main bundle so automation tasks are
born `type='task'`. They then flow through emdash's own `createTask` path — a
normal `task:created` event, live sidebar appearance — while still linking to
their run via `automationRunId` (exactly what emdash's own "convert to task"
button does, just automatic). The runner's DB `type`-flip becomes a redundant
no-op; no runner change is needed.

## Why this is safe (no re-signing)

The patch is a **same-length byte substitution** on `app.asar`: the archive
header offsets and the `app.asar.unpacked` native modules are untouched and the
total file size is unchanged, so the archive stays structurally valid. We
**never run `codesign`**:

- emdash ships with the `EnableEmbeddedAsarIntegrityValidation` Electron fuse
  **Disabled**, so Electron never hash-checks `app.asar` at runtime (the
  Info.plist asar hash is dormant).
- The app is non-quarantined and already trusted, so macOS does not re-run
  Gatekeeper bundle assessment on normal launch — the stale `CodeResources`
  seal is never consulted.
- `app.asar` is a data file, not a Mach-O, so AMFI/the hardened runtime never
  validates it; only the main executable is checked, and we leave its Team-ID
  signature **pristine**. (Ad-hoc re-signing would swap that identity and
  **break keychain access** — which is exactly why we don't sign.)

**Idempotent + fail-closed:** no-op if already patched; aborts loudly if the
anchor line isn't present exactly once (emdash changed internals → re-vet the
anchor against current source before forcing anything).

**Auto-update wipes it.** A Squirrel update replaces the whole bundle, dropping
the patch. Re-run this skill after any emdash update.

**Restore anytime:** `mv "<Emdash.app>/Contents/Resources/app.asar.canopy-pre-patch" "<...>/app.asar"`.

## When to use

- canopy-runner-triggered turns appear under *Automations* but not live under
  the agent's project sidebar.
- Right after emdash updates/auto-updates (the patch is gone).
- New machine running the canopy laptop runner.

## Run

**emdash must be quit** (Cmd-Q) — a running app holds `app.asar` open. Run this
from a plain Terminal, not from a Claude session hosted inside emdash.

```bash
set -euo pipefail
APP="${EMDASH_APP:-/Applications/Emdash.app}"
ASAR="$APP/Contents/Resources/app.asar"
BACKUP="$APP/Contents/Resources/app.asar.canopy-pre-patch"
[ -f "$ASAR" ] || { echo "✗ app.asar not found at $ASAR — is Emdash installed?"; exit 1; }
if pgrep -x Emdash >/dev/null 2>&1; then
  echo "✗ Emdash is running. Quit it (Cmd-Q) and re-run."; exit 1
fi
python3 - "$ASAR" "$BACKUP" <<'PY'
import sys, pathlib
asar, backup = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
data = asar.read_bytes()
SENTINEL = b"canopy-auto-task"
OLD = b'params.automationRunId ? "automation-run" : "task"'
if SENTINEL in data:
    print("✓ already patched — no-op"); sys.exit(0)
n = data.count(OLD)
if n != 1:
    print(f"✗ anchor found {n} times (expected 1) — emdash internals changed;")
    print("  re-vet the createTask line against current source. Aborting."); sys.exit(2)
core = b'"task"'
pad = len(OLD) - len(core)
comment = b"/*" + SENTINEL + b"-" * (pad - 4 - len(SENTINEL)) + b"*/"
new = core + comment
assert len(new) == len(OLD)
backup.write_bytes(data)                          # restore point = current unpatched asar
patched = data.replace(OLD, new)
assert len(patched) == len(data), "length changed — refusing to write"
asar.write_bytes(patched)
chk = asar.read_bytes()
assert chk.count(SENTINEL) == 1 and OLD not in chk and len(chk) == len(data)
print("✓ patched app.asar (same-length byte edit; size unchanged)")
print(f"  restore: mv '{backup}' '{asar}'")
PY
echo "✓ done. Relaunch Emdash — automation runs now appear as live sidebar tasks."
```

## Notes

- **Never `codesign`** the bundle here (see "Why this is safe"). If you ever see
  a "damaged app" dialog it means Gatekeeper re-assessed (e.g. the app got
  quarantined); restore from the `app.asar.canopy-pre-patch` backup and
  investigate — do not ad-hoc-sign.
- The anchor is `type: params.automationRunId ? "automation-run" : "task"` in
  emdash's `createTask` builder (main bundle). If a future emdash refactors it,
  this skill aborts (exit 2) rather than guess — update the anchor then.
- Companion to the agent-execution harness (`apps/harness` + `canopy_runner`).
