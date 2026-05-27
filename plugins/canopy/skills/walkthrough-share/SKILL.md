---
name: walkthrough-share
description: |
  Upload a walkthrough artifact (HTML slideshow or MP4 video) to a canopy-web
  instance so it can be shared via URL. Per-walkthrough visibility: private
  (dimagi-OAuth gate) or link (anyone with the token).
  Use when asked to "share this walkthrough", "upload to canopy-web",
  "make a share link for the walkthrough", or "walkthrough-share <path>".
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash ~/emdash-projects/canopy/scripts/canopy-update-check.sh 2>/dev/null || true)
if [ -n "$_CANOPY_UPD" ]; then echo "$_CANOPY_UPD"; fi
```

If output shows `UPGRADE_AVAILABLE <old> <new>`, mention it once and continue.

# Walkthrough Share

Uploads a finished walkthrough to canopy-web. HTML walkthroughs get their
relative screenshot/CSS references inlined as base64 data URIs before upload,
so the single file renders standalone inside the canopy-web viewer's iframe.
MP4 videos upload as-is.

The viewer page (`/w/<id>`) lets the owner toggle visibility, copy a share
link, rotate the token, or delete. Non-owners just see the player.

## Required state

- **PAT** at `~/.claude/canopy/workbench-token` (or `CANOPY_WEB_PAT` env
  var). Mint with `/canopy:canopy-web-pat-mint` — gh-style loopback flow,
  one click in the browser. The PAT identifies the human caller; uploaded
  walkthroughs are owned by whoever minted the token, no separate `--as`
  flag needed.
- **Canopy-web reachability**: defaults to the production deploy. Override
  with `CANOPY_WEB_API_URL` env var (e.g. for local dev against
  `http://localhost:8000`).

## Modes

```bash
# Upload (private — only visible to logged-in dimagi users)
python3 ~/emdash-projects/canopy/scripts/walkthrough-share/upload.py \
  screenshots/walkthroughs/my-demo.html \
  --title "My Demo" \
  --project canopy-web

# Upload + mint a share link (anyone with the URL can view)
python3 ~/emdash-projects/canopy/scripts/walkthrough-share/upload.py \
  screenshots/walkthroughs/my-demo.html \
  --title "My Demo" \
  --project canopy-web \
  --public

# Upload a video (kind auto-detected from .mp4 extension)
python3 ~/emdash-projects/canopy/scripts/walkthrough-share/upload.py \
  screenshots/walkthroughs/my-demo.mp4 \
  --public
```

The script prints:

```
inlining HTML assets from <dir>…
uploading <N> MB to <api>…
View: <api>/w/<uuid>
Share: <api>/w/<uuid>?t=<token>   # only with --public
```

Pass the `Share:` line back to the user verbatim.

## Argument map

| Flag | Required | Notes |
|---|---|---|
| `<path>` (positional) | yes | `.html`, `.htm`, or `.mp4`. Other types rejected. |
| `--title <str>` | no | Defaults to filename stem. Max 200 chars on the server. |
| `--description <str>` | no | Optional long-form description. |
| `--project <slug>` | no | Links the walkthrough to a canopy-web project tile. Must match an existing slug (no server-side validation today; bad slug = no link, no error). |
| `--public` | no | Sets visibility=link and prints a `?t=<token>` URL. Default is private. |
| `--api-url <url>` | no | Override canopy-web base URL (also via `CANOPY_WEB_API_URL`). |

## First-time setup

If `~/.claude/canopy/workbench-token` doesn't exist (or the token is expired),
mint one:

```
/canopy:canopy-web-pat-mint
```

That command opens your browser to canopy-web's authorize page (signing you
in via Google if needed), captures the minted PAT on a one-shot localhost
listener, and writes it to `~/.claude/canopy/workbench-token` (chmod 600).
Same token is used by the post-tool-use hook and `/canopy:canopy-doctor`.

## Error handling

The script exits non-zero with a one-line `error: ...` message on stderr:

- Missing PAT → tells you to run `/canopy:canopy-web-pat-mint`.
- HTTP 401 → PAT is expired or revoked. Re-mint via the slash command.
- HTTP 500 with `Drive not configured` → canopy-web is missing
  `CANOPY_DRIVE_SA_KEY_JSON` / `CANOPY_DRIVE_ROOT_FOLDER_ID`. Deployment
  problem, not a client problem.
- HTTP 413 → file exceeds `WALKTHROUGH_MAX_UPLOAD_BYTES` (default 75 MB on
  the server). For HTML, shrink the screenshots before re-running.

## After uploading

If you uploaded with `--public`, paste the `Share:` URL into the channel /
DM you want to share it in. The URL is unguessable — but treat it like any
other unlisted-link share (don't paste in public unless you mean it).

To revoke a share link without deleting the walkthrough, visit the viewer
page at `/w/<uuid>` and click "Rotate token" — the old URL stops working
immediately.

## Used by

- `/canopy:walkthrough` — at the end of a successful run, optionally calls
  this skill to publish the deck.
