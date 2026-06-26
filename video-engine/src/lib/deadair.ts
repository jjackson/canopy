/**
 * Dead-air prevention — pure cap math (Layer 1).
 *
 * "Dead air" = a span where the video is FROZEN (no on-screen motion) AND there
 * is no voiceover. It happens because a recorded beat's on-screen hold is a
 * fixed length set BEFORE the VO length is known; when the hold outlasts both
 * the footage motion and the narration, the tail is a frozen + silent frame.
 *
 * The fix (proven by hand, now codified): cap each beat's on-screen duration to
 *
 *     cap = max(footageMotionEnd, vo) + BREATH
 *
 * A held frame then only lasts as long as the voice playing over it (or the
 * footage motion, whichever is longer), plus one breath — so no silent frozen
 * tail. Two invariants make this safe on the SHARED render path:
 *
 *   1. ONLY shrink. A beat already shorter than its cap is never grown — that
 *      is `realignTimelineToAudio`'s job (it grows beats so VO never clips).
 *   2. Only shrink when the excess STRICTLY exceeds DEAD_THRESHOLD, so sub-3s
 *      settles ("leave anything under 3s") are left untouched and a video with
 *      no real dead air renders byte-comparably.
 *
 * Because the cap floors at `vo`, a beat is NEVER cut below its narration: a
 * held frame UNDER the voice is not dead air and must be preserved.
 *
 * The music bed is looped over the full (capped) duration at mix time
 * (`-stream_loop -1`), so a shorter total simply re-laps continuously — no
 * chop. That is why the fix is a (re-)render via duration caps, never a raw
 * mp4 cut.
 */

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";

/** Excess (current hold beyond the cap) must STRICTLY exceed this to shrink.
 * Product call: "leave anything under 3s" — sub-3s settles are intentional. */
export const DEAD_THRESHOLD_SECONDS = 3.0;

/** One breath of settled frame kept after the longer of footage-motion / VO. */
export const BREATH_SECONDS = 0.4;

export interface CapBeatArgs {
  /** The beat's current on-screen duration (seconds). */
  current: number;
  /** Last on-screen MOTION time within the beat's footage (seconds). 0 if
   * unknown (probe failed) — then the VO alone floors the cap. */
  footageMotionEnd: number;
  /** The beat's synthesized voiceover duration (seconds). 0 if no VO. */
  vo: number;
  /** Settled-frame breath kept after max(motion, vo). Default 0.4s. */
  breath?: number;
  /** Strict-excess threshold below which the beat is left alone. Default 3.0s. */
  threshold?: number;
}

/**
 * Compute the capped on-screen duration for one beat.
 *
 * Returns `current` unchanged unless the dead tail (current − cap) strictly
 * exceeds `threshold`, in which case it returns the cap. The result is always
 * ≥ `vo` (never cuts the voice) and always ≤ `current` (only shrinks).
 */
export function capBeatDuration(args: CapBeatArgs): number {
  const {
    current,
    footageMotionEnd,
    vo,
    breath = BREATH_SECONDS,
    threshold = DEAD_THRESHOLD_SECONDS,
  } = args;
  const cap = Math.max(footageMotionEnd, vo) + breath;
  const excess = current - cap;
  if (excess > threshold) {
    // Shrink to the cap — but never below the VO (the floor is baked into
    // `cap` via max(_, vo), so `cap >= vo + breath`; this min is belt-and-
    // suspenders for callers that pass a tiny custom breath).
    return Math.max(cap, vo);
  }
  return current;
}

/** Freeze threshold for the freezedetect motion probe (dB) — a frame within
 * this noise floor of the previous frame counts as "no motion". Matches the
 * post-render detector so render-time caps and the QA report agree. */
const FREEZE_NOISE_DB = -55;
/** Minimum freeze span (seconds) freezedetect must see before it reports one. */
const FREEZE_MIN_SECONDS = 0.7;

/** Gaps of on-screen motion shorter than this (seconds) between two freeze
 * spans are treated as micro-motion (a cursor twitch / hover) and merged, so a
 * near-static dashboard tail that flickers reads as one settled frozen tail
 * rather than "still moving". Tuned so the SG dashboard tails collapse. */
const TAIL_MERGE_GAP_SECONDS = 1.2;
/** A frozen tail is only a "settle" if it reaches within this of the range end
 * (i.e. the footage really has settled, not paused mid-action). */
const TAIL_END_EPSILON_SECONDS = 0.6;

/**
 * The footage "settle point": the on-screen time after which the footage is, for
 * practical purposes, frozen for the rest of the range — i.e. where a sustained
 * frozen tail begins. Returns the range `dur` when the footage keeps moving to
 * the end (no settled tail). PURE — operates on parsed freeze spans.
 *
 * Why not "last motion timestamp"? A recorded dashboard is near-static and
 * flickers (cursor moves, hovers) right up to the end, so the literal last
 * motion is ~the range end and yields no useful cap. We instead walk freeze
 * spans from the end, merging any separated by < `mergeGap` of motion, and
 * return the start of that merged frozen tail — but only if the tail reaches
 * the range end (`endEpsilon`). This is exactly the frozen tail the post-render
 * detector flags as dead air once the VO underneath it has ended.
 */
export function settlePointFromFreezeSpans(
  spans: [number, number][],
  dur: number,
  opts: { mergeGap?: number; endEpsilon?: number } = {},
): number {
  const mergeGap = opts.mergeGap ?? TAIL_MERGE_GAP_SECONDS;
  const endEpsilon = opts.endEpsilon ?? TAIL_END_EPSILON_SECONDS;
  if (spans.length === 0) return dur;
  const sorted = [...spans].sort((a, b) => a[0] - b[0]);
  const [lastStart, lastEnd] = sorted[sorted.length - 1];
  // The final freeze must reach the range end to count as a settled tail.
  if (dur - lastEnd > endEpsilon && dur - lastStart > endEpsilon) return dur;
  // Walk backwards, absorbing earlier freezes whose motion gap to the running
  // tail start is < mergeGap (micro-motion).
  let tailStart = lastStart;
  for (let i = sorted.length - 2; i >= 0; i--) {
    const [s, e] = sorted[i];
    if (tailStart - e < mergeGap) {
      tailStart = Math.min(tailStart, s);
    } else {
      break; // a real motion gap — the settled tail starts after it.
    }
  }
  return Math.max(0, Math.min(tailStart, dur));
}

/**
 * Footage settle-time (seconds, relative to the segment range) within a clip
 * sub-range, via ffmpeg `freezedetect`. See {@link settlePointFromFreezeSpans}
 * for the semantics: returns where a sustained frozen tail begins, or the range
 * `dur` when the footage keeps moving to the end.
 *
 * Returns `null` on any ffmpeg/parse failure (caller treats null as "unknown"
 * and uses the VO floor only — never widening a beat).
 */
export function footageMotionEndSeconds(
  clipPath: string,
  start: number,
  dur: number,
): number | null {
  const spans = freezeSpansForRange(clipPath, start, dur);
  if (spans === null) return null;
  return settlePointFromFreezeSpans(spans, dur);
}

/**
 * Raw freeze spans (seconds, relative to the sub-range) within a clip sub-range,
 * via ffmpeg `freezedetect`. Returns `null` on any ffmpeg/parse failure. Shared
 * by the trailing settle-point probe and the interior-excise probe.
 */
export function freezeSpansForRange(
  clipPath: string,
  start: number,
  dur: number,
): [number, number][] | null {
  if (!existsSync(clipPath) || dur <= 0) return null;
  // freezedetect prints its spans to stderr; capture it regardless of exit
  // code (the null muxer EOF makes some ffmpeg builds exit non-zero).
  const res = spawnSync(
    "ffmpeg",
    [
      "-hide_banner", "-nostats",
      "-ss", start.toFixed(3),
      "-t", dur.toFixed(3),
      "-i", clipPath,
      "-vf", `freezedetect=n=${FREEZE_NOISE_DB}dB:d=${FREEZE_MIN_SECONDS},metadata=print`,
      "-an", "-f", "null", "-",
    ],
    { encoding: "utf8", timeout: 120_000 },
  );
  if (res.error) return null; // ffmpeg not found / spawn failure.
  return parseFreezeSpansFromLog(res.stderr ?? "", dur);
}

/** Parse freezedetect (start,end) pairs from an ffmpeg stderr log; a final
 * unmatched start closes at `dur`. Dedupes the doubled metadata prints. */
function parseFreezeSpansFromLog(log: string, dur: number): [number, number][] {
  const starts = [...log.matchAll(/freeze_start[:=]\s*([0-9.]+)/g)].map((m) => Number(m[1]));
  const ends = [...log.matchAll(/freeze_end[:=]\s*([0-9.]+)/g)].map((m) => Number(m[1]));
  const spans: [number, number][] = [];
  for (let i = 0; i < starts.length; i++) {
    const s = starts[i];
    const e = i < ends.length ? ends[i] : dur;
    if (spans.length === 0 || spans[spans.length - 1][0] !== s) spans.push([s, e]);
  }
  return spans;
}

/** One walkthrough beat's footage range into the master clip — a list of
 * de-dwelled motion sub-ranges (segments) OR a single start/duration. */
export interface BeatFootage {
  segments?: { start_seconds: number; duration_seconds: number }[];
  start_seconds?: number;
  duration_seconds?: number;
}

/**
 * Footage motion-end for a beat that plays a LIST of master-clip segments.
 *
 * The renderer plays the segments back-to-back, so on-screen time is the
 * running sum of segment durations. We probe each segment for its motion-end
 * and return the on-screen time at which the LAST motion occurs across the
 * concatenation (sum of all prior full segments + the last segment's own
 * motion-end). Returns `null` if every probe fails.
 */
export function footageMotionEndForBeat(
  masterClipPath: string,
  footage: BeatFootage,
): number | null {
  const segs =
    footage.segments && footage.segments.length > 0
      ? footage.segments
      : footage.duration_seconds
        ? [{ start_seconds: footage.start_seconds ?? 0, duration_seconds: footage.duration_seconds }]
        : [];
  if (segs.length === 0) return null;
  let onScreen = 0;
  let lastMotionOnScreen: number | null = null;
  for (const s of segs) {
    const me = footageMotionEndSeconds(masterClipPath, s.start_seconds, s.duration_seconds);
    if (me !== null) lastMotionOnScreen = onScreen + me;
    onScreen += s.duration_seconds;
  }
  return lastMotionOnScreen;
}

// ---------------------------------------------------------------------------
// Layer 1b — VO-aware INTERIOR dead-air excision.
//
// The trailing cap above removes a frozen tail AFTER the last motion. It can't
// touch an INTERIOR frozen span — a loading wait ("Generating…"/"Reviewing…")
// that sits BETWEEN a click and the result: motion follows it, so it survives.
// The de-dweller can't either (it's motion-only — a spinner and a deliberate
// held frame both read as "no motion" — and it's disabled for `pace: teach`).
//
// The one signal that separates a loading WAIT from a deliberate HOLD is the
// VOICEOVER: a frozen span with NO voice over it is dead air to cut; a frozen
// span UNDER the voice is a hold to keep. VO timing is known post-TTS, exactly
// where this runs. We excise the silent interior frozen spans (keeping a short
// lead-in so the cut reads as intentional) by SPLITTING the beat's footage
// segments — the renderer plays the spliced segments back-to-back as a jump-cut.
// ---------------------------------------------------------------------------

/** Brief beat of the spinner kept after the voice ends before cutting to the
 * result — so a collapsed loading wait reads as a deliberate jump-cut. */
export const INTERIOR_LEAD_IN_SECONDS = 1.2;

const round3 = (n: number) => Math.round(n * 1000) / 1000;

export interface InteriorExciseOpts {
  /** Spinner kept after the VO ends before the cut. Default 1.2s. */
  leadInSeconds?: number;
  /** Silent-frozen span must STRICTLY exceed this to be cut. Default 3.0s. */
  thresholdSeconds?: number;
  /** A span whose end is within this of the total is a trailing tail (left to
   * the trailing cap), not an interior wait. Default 0.6s. */
  endEpsilon?: number;
}

/**
 * On-screen ranges to EXCISE for interior loading waits. PURE.
 *
 * A freeze span `[a,b]` (on-screen seconds) is cut iff:
 *   1. INTERIOR — `b` is not within `endEpsilon` of `totalSeconds` (a trailing
 *      frozen tail is the trailing cap's job, not this).
 *   2. Its SILENT portion `b − max(a, voSeconds)` strictly exceeds
 *      `thresholdSeconds` (a span fully under the VO is a deliberate hold).
 * The cut range is `[max(a, voSeconds) + leadIn, b]`. Overlaps merged.
 */
export function interiorExciseRanges(
  freezeSpans: [number, number][],
  voSeconds: number,
  totalSeconds: number,
  opts: InteriorExciseOpts = {},
): [number, number][] {
  const leadIn = opts.leadInSeconds ?? INTERIOR_LEAD_IN_SECONDS;
  const threshold = opts.thresholdSeconds ?? DEAD_THRESHOLD_SECONDS;
  const endEpsilon = opts.endEpsilon ?? TAIL_END_EPSILON_SECONDS;
  const cuts: [number, number][] = [];
  for (const [a, b] of freezeSpans) {
    if (totalSeconds - b <= endEpsilon) continue; // trailing tail — leave to the cap.
    const silentStart = Math.max(a, voSeconds); // the part of the freeze with no voice.
    if (b - silentStart <= threshold) continue; // under VO or too short — keep.
    const cutStart = silentStart + leadIn;
    if (b - cutStart > 1e-6) cuts.push([cutStart, b]);
  }
  cuts.sort((x, y) => x[0] - y[0]);
  const merged: [number, number][] = [];
  for (const [s, e] of cuts) {
    const last = merged[merged.length - 1];
    if (last && s <= last[1] + 1e-6) last[1] = Math.max(last[1], e);
    else merged.push([s, e]);
  }
  return merged;
}

/**
 * Remove on-screen ranges from a list of master-clip segments. PURE.
 *
 * On-screen time is the running sum of segment durations. Each kept on-screen
 * range maps back to a master sub-range `start_seconds + (onscreen − segStart)`.
 * Handles cuts inside a segment, cuts spanning multiple segments, and produces
 * the minimal kept-segment list.
 */
export function spliceSegments(
  segments: { start_seconds: number; duration_seconds: number }[],
  exciseOnScreen: [number, number][],
): { start_seconds: number; duration_seconds: number }[] {
  if (!exciseOnScreen.length) return segments.map((s) => ({ ...s }));
  const total = segments.reduce((a, s) => a + s.duration_seconds, 0);
  const cuts = [...exciseOnScreen].sort((a, b) => a[0] - b[0]);
  // Build the KEEP ranges (on-screen) = [0,total] minus the cuts.
  const keep: [number, number][] = [];
  let pos = 0;
  for (const [cs0, ce0] of cuts) {
    const cs = Math.max(0, Math.min(cs0, total));
    const ce = Math.max(0, Math.min(ce0, total));
    if (cs > pos + 1e-6) keep.push([pos, cs]);
    pos = Math.max(pos, ce);
  }
  if (pos < total - 1e-6) keep.push([pos, total]);
  // Map each kept on-screen range back to master sub-ranges across segments.
  const out: { start_seconds: number; duration_seconds: number }[] = [];
  for (const [ks, ke] of keep) {
    let segStart = 0;
    for (const seg of segments) {
      const segEnd = segStart + seg.duration_seconds;
      const ovS = Math.max(ks, segStart);
      const ovE = Math.min(ke, segEnd);
      if (ovE > ovS + 1e-6) {
        out.push({
          start_seconds: round3(seg.start_seconds + (ovS - segStart)),
          duration_seconds: round3(ovE - ovS),
        });
      }
      segStart = segEnd;
    }
  }
  return out;
}

/**
 * Excise interior loading waits from a beat's footage. Probes each segment for
 * freeze spans, maps them to on-screen time, cuts the silent interior ones
 * (see {@link interiorExciseRanges}), and splices the segments. Best-effort:
 * any ffmpeg failure returns the footage unchanged. The master clip lives at
 * `masterClipPath`; `voSeconds` is the beat's synthesized VO duration.
 */
export function exciseInteriorDeadAir(
  masterClipPath: string,
  footage: BeatFootage,
  voSeconds: number,
  opts: InteriorExciseOpts = {},
): { segments: { start_seconds: number; duration_seconds: number }[]; onScreenSeconds: number; excisedSeconds: number } {
  const segs =
    footage.segments && footage.segments.length > 0
      ? footage.segments
      : footage.duration_seconds
        ? [{ start_seconds: footage.start_seconds ?? 0, duration_seconds: footage.duration_seconds }]
        : [];
  const total = segs.reduce((a, s) => a + s.duration_seconds, 0);
  const unchanged = { segments: segs.map((s) => ({ ...s })), onScreenSeconds: round3(total), excisedSeconds: 0 };
  if (segs.length === 0 || total <= 0) return unchanged;
  // Freeze-detect each segment → freeze spans in ON-SCREEN time.
  const spans: [number, number][] = [];
  let onScreen = 0;
  for (const s of segs) {
    const segSpans = freezeSpansForRange(masterClipPath, s.start_seconds, s.duration_seconds);
    if (segSpans === null) return unchanged; // probe failed — best-effort no-op.
    for (const [a, b] of segSpans) spans.push([onScreen + a, onScreen + b]);
    onScreen += s.duration_seconds;
  }
  const cuts = interiorExciseRanges(spans, voSeconds, total, opts);
  if (cuts.length === 0) return unchanged;
  const newSegs = spliceSegments(segs, cuts);
  const newTotal = newSegs.reduce((a, s) => a + s.duration_seconds, 0);
  return { segments: newSegs, onScreenSeconds: round3(newTotal), excisedSeconds: round3(total - newTotal) };
}
