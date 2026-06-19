import { AbsoluteFill, Freeze, Sequence, Video, staticFile, useVideoConfig } from "remotion";
import { theme } from "../theme";
import { Lower3rd } from "../components/Lower3rd";
import type { ProgramSpec, WalkthroughBeat } from "../lib/spec";

/**
 * One walkthrough section of the connect-ddd-walkthrough arc. Plays a RANGE
 * of one master clip full-bleed (objectFit: cover, `startFrom` honoring
 * the beat's start_seconds in the source), overlays a single
 * lower-third, and lets the top-level CaptionBar + per-beat VO ride on
 * top.
 *
 * The beat's on-screen DURATION is the Sequence length given to it by
 * Root.tsx (b.durationFrames) — i.e. the beat's `seconds` from the
 * spec's `beats:` list, which the audio-aligner STRETCHES to fit the
 * narration. `start_seconds` is the IN-point into the master clip and
 * `duration_seconds` is how long the selected RANGE of footage runs.
 *
 * HOLD-LAST-FRAME: when the beat's on-screen length (durationInFrames)
 * runs LONGER than the selected range (duration_seconds), the clip would
 * otherwise keep playing past its range into the NEXT section's footage
 * (drift). We wrap the <Video> in <Freeze> so it plays only its range
 * [start_seconds, start_seconds + duration_seconds] and then freezes on
 * the last frame of that range for the remaining beat time — the section
 * stays on its own footage while the narration finishes.
 *
 * When duration_seconds is absent there's no defined range, so we fall
 * back to playing the whole beat (the original behavior).
 */
/**
 * Decide whether to hold the last frame and, if so, at which range frame.
 *
 * Returns the range length in frames when the beat's on-screen length
 * (`beatFrames`) runs LONGER than the selected range (`durationSeconds`)
 * — i.e. when footage would otherwise drift into the next section.
 * Returns null (play the whole beat unchanged) when `durationSeconds` is
 * absent or the range is at least as long as the beat.
 */
export function freezeRangeFrames(
  durationSeconds: number | undefined,
  fps: number,
  beatFrames: number
): number | null {
  if (durationSeconds == null) return null;
  const rangeFrames = Math.max(1, Math.round(durationSeconds * fps));
  return rangeFrames < beatFrames ? rangeFrames : null;
}

/**
 * The sub-ranges of the master clip a beat plays, in order. Prefers the
 * de-dwelled ``segments`` list (motion spans with dead-air gaps collapsed →
 * jump-cuts); falls back to the single ``start_seconds``/``duration_seconds``
 * range for older / non-de-dwelled specs. ``duration_seconds`` may be
 * undefined in the single-range fallback (= play the whole beat).
 */
export function beatSegments(
  wt: WalkthroughBeat
): { start_seconds: number; duration_seconds?: number }[] {
  if (wt.segments && wt.segments.length > 0) return wt.segments;
  return [{ start_seconds: wt.start_seconds ?? 0, duration_seconds: wt.duration_seconds }];
}

export const Walkthrough: React.FC<{ wt: WalkthroughBeat }> = ({ wt }) => {
  const { fps, durationInFrames } = useVideoConfig();
  const src = wt.asset.startsWith("http") ? wt.asset : staticFile(wt.asset);
  const segs = beatSegments(wt);

  const videoFrom = (startSeconds: number) => (
    <Video
      src={src}
      startFrom={Math.round(startSeconds * fps)}
      style={{ width: "100%", height: "100%", objectFit: "cover" }}
      onError={() => {
        /* Missing asset — render blank; drop the real file in the cache to fix */
      }}
    />
  );

  // Single open-ended range (no duration): the original whole-beat playback.
  if (segs.length === 1 && segs[0].duration_seconds == null) {
    return (
      <AbsoluteFill style={{ background: theme.colors.foreground }}>
        {videoFrom(segs[0].start_seconds)}
        {wt.lower_third ? <Lower3rd text={wt.lower_third} /> : null}
      </AbsoluteFill>
    );
  }

  // De-dwelled (or single ranged) playback: lay each segment back-to-back via
  // nested Sequences. The dropped gaps between segments are clean jump-cuts.
  // The LAST segment holds its final frame for any beat time beyond the summed
  // segment length (VO overrun) — same hold-last-frame contract as before.
  const segFrames = segs.map((s) => Math.max(1, Math.round((s.duration_seconds as number) * fps)));
  let offset = 0;
  const nodes = segs.map((s, i) => {
    const sf = segFrames[i];
    const isLast = i === segs.length - 1;
    const seqLen = isLast ? Math.max(sf, durationInFrames - offset) : sf;
    const vid = videoFrom(s.start_seconds);
    // Hold the last frame only on the final segment when the beat outruns it.
    const child =
      isLast && seqLen > sf ? (
        <Freeze frame={sf - 1} active={(f) => f >= sf}>
          {vid}
        </Freeze>
      ) : (
        vid
      );
    const node = (
      <Sequence key={i} from={offset} durationInFrames={seqLen}>
        {child}
      </Sequence>
    );
    offset += sf;
    return node;
  });

  return (
    <AbsoluteFill style={{ background: theme.colors.foreground }}>
      {nodes}
      {wt.lower_third ? <Lower3rd text={wt.lower_third} /> : null}
    </AbsoluteFill>
  );
};

/** Lookup helper — resolve a beat id to its walkthrough entry. */
export function walkthroughForBeat(
  spec: ProgramSpec,
  beatId: string
): WalkthroughBeat | undefined {
  return spec.walkthrough?.[beatId];
}
