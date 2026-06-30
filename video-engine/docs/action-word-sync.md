# Action↔word voiceover sync

**Problem.** A DDD walkthrough scene binds VO to footage only at the *beat* (=scene)
boundary: one ElevenLabs VO clip is laid over one footage range, anchored at the
beat's start frame. Within a beat the two run on independent clocks. A scene that
narrates a form — "she adds a description, the type, timeline, scale and contact"
— speaks ~10 field names in one compact ~21s sentence while the footage
demonstrates 16 fields one-by-one over ~28s. The spoken field name races ahead of
the cursor: the VO says "contact" while the UI is still ~9 fields north of it.
(Symptom report: "the voice over is moving faster than the UI when it's describing
what fields it's on.")

**Fix.** Bind individual footage actions to the moment the VO speaks the matching
word, and piecewise time-warp the footage so each named field lands on its word.

## Data flow

1. **Recorder** (`scripts/walkthrough/_lib/orchestrator.py`) already knows each
   action's start time (`action_start_mono - recording_epoch`). It now serializes
   it as `ActionResult.start_seconds` (raw master-clip seconds) into the
   run-report `actions[]`.
2. **Snippets** (`scripts/ddd/snippets.py`) maps each action's raw `start_seconds`
   through the same de-dwell + load-wait excision the footage gets, into
   **on-screen** seconds, and attaches `action_marks[]` to the walkthrough beat,
   each carrying `{on_seconds, words[], target, kind}`. `words` are lowercased
   candidate narration words derived from the field target id + the action note
   (first that resolves against the VO wins); an action may also declare an
   explicit `word:`/`say:` for summary words ("deadline" field ↔ "timeline" word).
3. **Spec** (`video-engine/src/lib/spec.ts`) carries `action_marks` on the
   walkthrough beat schema.
4. **Render** (`video-engine/scripts/render.ts`) already pulls per-character VO
   timings from ElevenLabs (`voiceover.ts:wordStartSeconds`, today used only for
   the marketing cycle keywords). For each beat with `action_marks`, it resolves
   each mark's word → VO seconds, builds a **warp plan** (`actionsync.ts`), and
   attaches it to the beat.
5. **Composition** (`video-engine/src/compositions/Walkthrough.tsx`) plays the
   warp plan's pieces as nested `<Sequence>`s of `<Video startFrom playbackRate>`,
   so footage between two word-anchors plays at the constant rate that lands the
   next field on its word. No marks / no resolved words → unchanged behavior.

## Warp planner (`actionsync.ts`, pure)

- Resolve marks → `(srcOnscreen, voSeconds)` anchors; drop unresolved; sort by
  src and enforce strictly-increasing vo (drop inversions).
- Add endpoints `(0,0)` and `(footageOnscreen, beatSeconds)`.
- Between consecutive anchors emit a constant-rate piece
  `rate = srcΔ / outΔ`, clamped to `[RATE_MIN, RATE_MAX]` so a field-fill demo
  never speeds/slows past natural-looking bounds; leftover footage at the tail
  freezes on the last frame (existing hold-last-frame contract).
- `composeWithSegments()` splits each piece at de-dwell segment boundaries so a
  constant-rate piece never straddles a jump-cut (teach scenes are single-segment,
  so this is a no-op there — and the problem scenes are `pace: teach`).

Graceful degradation: zero resolved marks ⇒ no warp plan ⇒ today's playback.
