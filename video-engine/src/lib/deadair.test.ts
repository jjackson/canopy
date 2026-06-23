import { describe, it, expect } from "vitest";
import {
  capBeatDuration,
  settlePointFromFreezeSpans,
  BREATH_SECONDS,
  DEAD_THRESHOLD_SECONDS,
} from "./deadair";

describe("settlePointFromFreezeSpans", () => {
  it("returns dur when there are no freeze spans (footage moves throughout)", () => {
    expect(settlePointFromFreezeSpans([], 30)).toBe(30);
  });

  it("returns dur when the footage un-freezes near the end (motion to the end)", () => {
    // Last freeze ends at 25, footage runs to 30 → moving at the end.
    expect(settlePointFromFreezeSpans([[5, 10], [20, 25]], 30)).toBe(30);
  });

  it("finds the start of a frozen tail that runs to the end", () => {
    // A clean frozen tail [23.7, 27.1] reaching the end → settle at 23.7.
    expect(settlePointFromFreezeSpans([[5, 8], [23.7, 27.1]], 27.1)).toBeCloseTo(23.7, 2);
  });

  it("merges dense micro-motion at the tail into one frozen settle point", () => {
    // The SG s6 tail: freezes at [13.46,17.46],[17.46,18.54],[18.58,19.3],
    // [20.42,23.66],[23.7,27.1] — separated by <0.8s motion blips — collapse
    // into one frozen tail starting ~13.46 (or after the last >mergeGap motion).
    const spans: [number, number][] = [
      [13.46, 17.46],
      [17.46, 18.54],
      [18.58, 19.3],
      [20.42, 23.66],
      [23.7, 27.1],
    ];
    const settle = settlePointFromFreezeSpans(spans, 27.1, { mergeGap: 1.2 });
    // The gaps between these freezes (≤1.12s) are all < mergeGap, so they merge
    // into a single frozen tail beginning at 13.46.
    expect(settle).toBeCloseTo(13.46, 2);
  });

  it("does NOT merge across a real motion gap larger than mergeGap", () => {
    // A 3s motion gap (10→13) separates an early freeze from the tail freeze;
    // the tail is [13,20] reaching the end. Settle at the tail start (13).
    expect(settlePointFromFreezeSpans([[2, 8], [13, 20]], 20, { mergeGap: 1.2 })).toBeCloseTo(13, 2);
  });
});

describe("capBeatDuration", () => {
  it("leaves a beat alone when the dead tail is at/under the threshold", () => {
    // footage motion ends at 23.7s, VO 15.7s, beat holds 26.5s.
    // cap = max(23.7, 15.7) + 0.4 = 24.1; excess = 2.4 < 3.0 → unchanged.
    const capped = capBeatDuration({
      current: 26.5,
      footageMotionEnd: 23.7,
      vo: 15.7,
    });
    expect(capped).toBeCloseTo(26.5, 3);
  });

  it("shrinks once the dead tail strictly exceeds the threshold", () => {
    // beat holds 30s, footage motion ends at 23.7s, VO 15.7s.
    // cap = 23.7 + 0.4 = 24.1; excess = 30 - 24.1 = 5.9 > 3.0 → shrink to 24.1.
    const capped = capBeatDuration({
      current: 30.0,
      footageMotionEnd: 23.7,
      vo: 15.7,
    });
    expect(capped).toBeCloseTo(24.1, 3);
  });

  it("NEVER cuts a beat below its VO (held overrun is under the voice, not dead)", () => {
    // VO (41.1s) outlasts footage motion (20s). The held frame plays under
    // the voice — that is not dead air. Cap = max(20, 41.1) + 0.4 = 41.5.
    const capped = capBeatDuration({
      current: 48.3,
      footageMotionEnd: 20.0,
      vo: 41.1,
    });
    expect(capped).toBeCloseTo(41.5, 3);
    expect(capped).toBeGreaterThanOrEqual(41.1);
  });

  it("leaves a sub-threshold settle (<3s excess) alone", () => {
    // cap = max(8, 5.9) + 0.4 = 8.4; current 10 → excess 1.6 < 3 → unchanged.
    const capped = capBeatDuration({
      current: 10.0,
      footageMotionEnd: 8.0,
      vo: 5.9,
    });
    expect(capped).toBeCloseTo(10.0, 3);
  });

  it("only ever shrinks — a beat shorter than its cap is never grown", () => {
    // current 5 is already below cap (max(8,6)+0.4=8.4) → leave at 5.
    const capped = capBeatDuration({
      current: 5.0,
      footageMotionEnd: 8.0,
      vo: 6.0,
    });
    expect(capped).toBeCloseTo(5.0, 3);
  });

  it("uses VO as the floor when footage motion end is unknown (0)", () => {
    // footageMotionEnd 0 (probe failed): cap = max(0, vo) + breath.
    const capped = capBeatDuration({
      current: 30.0,
      footageMotionEnd: 0,
      vo: 12.0,
    });
    expect(capped).toBeCloseTo(12.4, 3);
  });

  it("respects custom breath and threshold", () => {
    const capped = capBeatDuration({
      current: 30.0,
      footageMotionEnd: 20.0,
      vo: 10.0,
      breath: 1.0,
      threshold: 1.0,
    });
    // cap = max(20,10)+1.0 = 21; excess 9 > 1 → shrink to 21.
    expect(capped).toBeCloseTo(21.0, 3);
  });

  it("exposes the product-call constants", () => {
    expect(DEAD_THRESHOLD_SECONDS).toBe(3.0);
    expect(BREATH_SECONDS).toBe(0.4);
  });

  it("backward-compat: a beat with no real dead air is byte-unchanged", () => {
    // Mirrors the SG spec's s1/s2/s3 where beat.seconds == footage and VO
    // ≤ footage by < threshold: footage and voice fill the hold, no cap.
    for (const [current, foot, vo] of [
      [4.8, 4.8, 3.8],
      [5.8, 5.8, 3.8],
      [8.0, 8.0, 5.9],
    ] as const) {
      expect(capBeatDuration({ current, footageMotionEnd: foot, vo })).toBe(current);
    }
  });

  it("backward-compat: a VO-overrun beat (held under the voice) is unchanged", () => {
    // s7-shape: VO (11.7s) outlasts footage (6.9s). The held frame plays under
    // the voice — not dead air — and the beat is already shorter than the cap,
    // so it is never grown and never cut.
    expect(capBeatDuration({ current: 6.9, footageMotionEnd: 6.9, vo: 11.7 })).toBe(6.9);
  });
});
