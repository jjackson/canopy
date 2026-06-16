---
name: share-session
description: |
  Share the current Claude Code session as a pretty, read-only web page on
  canopy-web. Auto-discovers the newest transcript for the current project,
  best-effort-scrubs secrets, and returns a link-by-default /share/<token>
  URL anyone can open (no dimagi login). The generic counterpart to ACE's
  upload-transcript. Use when asked to "share this session", "share my
  transcript", "make a link for this chat", or "share-session".
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash "$HOME/emdash-projects/canopy/plugins/canopy/scripts/canopy-update-check.sh" 2>/dev/null || bash "$HOME/.claude/plugins/marketplaces/canopy/plugins/canopy/scripts/canopy-update-check.sh" 2>/dev/null || true)
case "$_CANOPY_UPD" in UPGRADE_AVAILABLE*) echo "$_CANOPY_UPD" ;; esac
```

If output shows `UPGRADE_AVAILABLE <old> <new>`, mention it once and continue.

# Share Session

Uploads the current Claude Code session's `.jsonl` transcript to canopy-web,
which parses it into a chat-style view, scrubs obvious secrets, and (by
default) mints an anyone-with-link share URL. The result renders at
`/share/<token>` — a clean, read-only transcript anyone can open without a
dimagi account.

This is the generic version of `ace:upload-transcript`: not scoped to any
opportunity, just "share what I just did with someone".

## Required state

- **PAT** at `~/.claude/canopy/workbench-token` (or `CANOPY_WEB_PAT` env var).
  Mint with `/canopy:canopy-web-pat-mint` — gh-style loopback flow, one click.
  The PAT identifies the caller; shared sessions are owned by whoever minted it.
- **Canopy-web reachability**: defaults to the production deploy. Override with
  `CANOPY_WEB_API_URL` (e.g. `http://localhost:8000` for local dev).

## Run it

Resolve the uploader (dev checkout first, then the marketplace clone a portable
install pulls via `/canopy:update`). `upload.py` is pure stdlib, so bare
`python3` runs it. Run this in the same shell as the command below:

```bash
UPLOAD=""
for P in \
  ~/emdash-projects/canopy/scripts/share-session/upload.py \
  ~/.claude/plugins/marketplaces/canopy/scripts/share-session/upload.py; do
  [ -f "$P" ] && UPLOAD="$P" && break
done
[ -z "$UPLOAD" ] && echo "NOT_FOUND — run /canopy:update to sync the canopy checkout" && exit 1
```

```bash
# Share the current session (link-by-default — anyone with the URL can view).
# Auto-discovers the newest transcript for the current working directory.
python3 "$UPLOAD" --title "Generic session sharing"

# Share a SPECIFIC transcript file (skip auto-discovery)
python3 "$UPLOAD" ~/.claude/projects/-Users-me-proj/abc123.jsonl

# Share privately (only logged-in dimagi users can view)
python3 "$UPLOAD" --private
```

The script prints:

```
using transcript: <path>            # stderr — only on auto-discovery
uploading <N> KB to <api>…          # stderr
Share: <api>/share/<token>          # stdout — the link to hand out
<N> messages · <N> secrets redacted (best-effort)   # stderr
```

Pass the `Share:` line back to the user verbatim.

## Argument map

| Flag | Required | Notes |
|---|---|---|
| `<path>` (positional) | no | A transcript `.jsonl`. Default: newest for the current dir's session, found under `~/.claude/projects/<cwd-slash-encoded>/`. |
| `--title <str>` | no | Defaults to the transcript filename stem. Max 500 chars server-side. |
| `--project <slug>` | no | Groups the session under a project in the `/sessions` feed. Defaults to the current directory name. |
| `--private` | no | Upload as private (dimagi-only). Default is link-by-default. |
| `--api-url <url>` | no | Override canopy-web base URL (also via `CANOPY_WEB_API_URL`). |

## Secret scrubbing (best-effort, not a guarantee)

On upload the server runs a conservative scrub over every turn: provider API
keys (`sk-…`, `ghp_…`, AWS/Google/Slack tokens), JWTs, PEM private-key blocks,
`Authorization: Bearer …` headers, and sensitive `KEY=value` assignments are
replaced with `‹redacted:…›`. The printed count tells you how many fired.

This catches the common foot-guns but is **not** a guarantee — high-entropy
one-off secrets and unusual formats can slip through. For anything sensitive,
prefer `--private`, and remember a `link` URL is unguessable but unlisted: treat
it like any other secret-link share.

## Managing shared sessions

Owners manage their sessions at `<api>/sessions` (dimagi login): copy the link,
**Rotate** (invalidate the current link, mint a new one), **Make private**
(revoke sharing), or **Delete**. Re-running the skill on the same session is
idempotent — it returns the existing link instead of creating a duplicate.

## First-time setup

If `~/.claude/canopy/workbench-token` doesn't exist (or the token is expired):

```
/canopy:canopy-web-pat-mint
```

That opens canopy-web's authorize page (signing you in via Google if needed),
captures the minted PAT on a one-shot localhost listener, and writes it to
`~/.claude/canopy/workbench-token` (chmod 600).

## Error handling

The script exits non-zero with a one-line `error: …` on stderr:

- Missing PAT → run `/canopy:canopy-web-pat-mint`.
- HTTP 401 → PAT expired/revoked. Re-mint via the slash command.
- HTTP 413 → transcript exceeds the server cap (50 MB). Unusual for a session.
- "no Claude session log dir" → run the skill from the project where the
  session ran, or pass the transcript path explicitly.
