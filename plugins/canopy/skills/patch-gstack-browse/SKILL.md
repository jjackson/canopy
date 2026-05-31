---
name: patch-gstack-browse
description: Use when the gstack `browse` headless browser fails to render WebGL/Mapbox/three.js/deck.gl ("Failed to initialize WebGL"), or right after a gstack update/upgrade overwrites the browse source — re-applies the SwiftShader WebGL patch and rebuilds the binary.
---

# Patch gstack browse for headless WebGL

gstack `browse` drives headless Chromium, which has no GPU. WebGL context
creation fails there, so any page built on WebGL — **Mapbox GL, three.js,
deck.gl, regl, PixiJS-WebGL** — throws `Failed to initialize WebGL` on init and
the page's script aborts. That makes map/canvas QA impossible via `browse`.

This skill patches `browse/src/browser-manager.ts` to launch Chromium with
`--enable-unsafe-swiftshader` (plus `--use-angle=swiftshader` and
`--ignore-gpu-blocklist`). **SwiftShader** is Chromium's CPU implementation of
the GL APIs — it renders WebGL on the CPU with no GPU present, visually
identical (just slower), which is exactly right for headless screenshot QA.
Chrome deprecated the *automatic* SwiftShader fallback (it JITs in the GPU
process, a risk only for untrusted content), so the explicit flag is required.

**Why a skill:** the patch lives in a vendored tool. A `gstack` self-update
(`/gstack-upgrade`) overwrites `browser-manager.ts` and rebuilds, silently
dropping the patch. Re-run this skill after any gstack update to restore
headless WebGL. It is **idempotent** — safe to run anytime; a no-op if already
patched.

## When to use

- `browse` console shows `Failed to initialize WebGL` / a Mapbox/three.js page
  renders blank or its init script never completes.
- Right after `gstack` updates/upgrades (the patch gets overwritten).
- Setting up a new machine where headless map QA is needed.

## Run

Idempotent: applies the patch only if missing, rebuilds only if it changed,
then restarts the daemon and verifies WebGL works. Local opt-out at runtime:
`BROWSE_DISABLE_WEBGL=1`.

```bash
set -e
GSTACK="${GSTACK_DIR:-$HOME/.claude/skills/gstack}"
SRC="$GSTACK/browse/src/browser-manager.ts"
BIN="$GSTACK/browse/dist/browse"
[ -f "$SRC" ] || { echo "browse source not found at $SRC — is gstack installed?"; exit 1; }

if grep -q -- '--enable-unsafe-swiftshader' "$SRC"; then
  echo "✓ already patched ($SRC)"
  CHANGED=0
else
  # Insert the SwiftShader flag block right after `let useHeadless = true;`
  # in the headless launch path (launchArgs is already declared above it).
  python3 - "$SRC" <<'PY'
import sys, io
path = sys.argv[1]
src = io.open(path, encoding="utf-8").read()
anchor = "let useHeadless = true;"
assert anchor in src, "anchor not found — browse internals changed; patch by hand"
block = """let useHeadless = true;

    // [canopy:patch-gstack-browse] Headless WebGL via SwiftShader.
    // Headless Chromium has no GPU, so WebGL context creation fails and pages
    // built on it (Mapbox GL, three.js, deck.gl) crash on init. SwiftShader is
    // Chromium's CPU GL implementation; Chrome deprecated the automatic
    // fallback, hence the explicit flag. Opt out at runtime: BROWSE_DISABLE_WEBGL=1.
    // NOTE: a gstack update overwrites this file — re-run /canopy:patch-gstack-browse.
    if (!process.env.BROWSE_DISABLE_WEBGL) {
      launchArgs.push(
        '--enable-unsafe-swiftshader',
        '--use-angle=swiftshader',
        '--ignore-gpu-blocklist',
      );
    }"""
src = src.replace(anchor, block, 1)
io.open(path, "w", encoding="utf-8").write(src)
print("✓ patched", path)
PY
  CHANGED=1
fi

# Rebuild the compiled binary when the source changed (or the binary is stale).
if [ "$CHANGED" = 1 ] || [ "$SRC" -nt "$BIN" ]; then
  command -v bun >/dev/null || { echo "bun not found; install bun then re-run"; exit 1; }
  echo "Building browse binary…"
  ( cd "$GSTACK" && bun run build )
  # macOS arm64: bun --compile can produce a signature macOS SIGKILLs; re-sign.
  if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
    codesign --remove-signature "$BIN" 2>/dev/null || true
    codesign -s - -f "$BIN" 2>/dev/null || true
  fi
  [ -x "$BIN" ] && "$BIN" restart >/dev/null 2>&1 || true
fi

# Verify WebGL now initializes headlessly (offline; uses about:blank).
"$BIN" goto about:blank >/dev/null 2>&1 || true
RESULT=$("$BIN" js "(()=>{const c=document.createElement('canvas');const gl=c.getContext('webgl2')||c.getContext('webgl');return gl?('WEBGL_OK '+gl.getParameter(gl.VERSION)):'NO_WEBGL';})()" 2>/dev/null | tail -1)
echo "$RESULT"
case "$RESULT" in
  *WEBGL_OK*) echo "✓ headless WebGL working";;
  *) echo "⚠ WebGL still failing — check that the daemon restarted and the build succeeded"; exit 1;;
esac
```

## Notes

- The patch only affects the **headless** launch path; headed mode already has a
  real GPU.
- A daemon **restart drops imported auth cookies** — if you were using an
  authenticated session (e.g. labs prod), re-import them after running this.
- Target path override: set `GSTACK_DIR` for a non-default install (e.g. a
  repo-vendored `.claude/skills/gstack`).
