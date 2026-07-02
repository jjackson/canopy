import { describe, it, expect } from "vitest";
import {
  capBeatDuration,
  settlePointFromFreezeSpans,
  interiorExciseRanges,
  spliceSegments,
  mergeFreezeSpans,
  BREATH_SECONDS,
  DEAD_THRESHOLD_SECONDS,
  FLICKER_MERGE_GAP_SECONDS,
} from "./deadair";

describe("interiorExciseRanges", () => {
  // beat: click motion → frozen spinner [5,25] → result motion; total 35s; VO 12s.
  it("cuts a silent interior loading wait, keeping a lead-in after the VO", () => {
    const cuts = interiorExciseRanges([[5, 25]], 12, 35, { leadInSeconds: 1.2 });
    // silent part starts at vo=12; keep 1.2s lead-in → cut [13.2, 25]
    expect(cuts).toEqual([[13.2, 25]]);
  });
  it("does NOT cut a frozen span fully under the voiceover (a deliberate hold)", () => {
    // span [2,10] entirely within VO=12 → no silent dead air.
    expect(interiorExciseRanges([[2, 10]], 12, 35)).toEqual([]);
  });
  it("does NOT cut a trailing frozen tail (left to the trailing cap)", () => {
    // span reaches the end (34.8 within endEpsilon 0.6 of total 35) → trailing.
    expect(interiorExciseRanges([[20, 34.8]], 12, 35)).toEqual([]);
  });
  it("does NOT cut a sub-threshold silent span (new 0.8s default)", () => {
    // silent part = 18−17.4 = 0.6s, not STRICTLY > 0.8 → keep.
    expect(interiorExciseRanges([[10, 18]], 17.4, 35)).toEqual([]);
  });
  it("cuts only the silent tail of a span that straddles the VO end", () => {
    // span [8,25], VO 12 → silent [12,25] (>3); keep lead-in → cut [13.2,25]
    expect(interiorExciseRanges([[8, 25]], 12, 35, { leadInSeconds: 1.2 })).toEqual([[13.2, 25]]);
  });
  it("merges overlapping cut ranges", () => {
    const cuts = interiorExciseRanges([[5, 20], [18, 28]], 0, 40, { leadInSeconds: 1.2 });
    // [6.2,20] and [19.2,28] overlap → [6.2,28]
    expect(cuts).toEqual([[6.2, 28]]);
  });
});

describe("mergeFreezeSpans (flicker robustness)", () => {
  it("is empty on empty input and identity on a single span", () => {
    expect(mergeFreezeSpans([])).toEqual([]);
    expect(mergeFreezeSpans([[5, 9]])).toEqual([[5, 9]]);
  });
  it("merges spans split by a sub-gap cursor twitch into one frozen span", () => {
    // A held frame flickers: freezes [10,11] and [11.5,12.5] split by a 0.5s
    // twitch (< 0.8 default) → one dead span [10,12.5].
    expect(mergeFreezeSpans([[10, 11], [11.5, 12.5]])).toEqual([[10, 12.5]]);
  });
  it("does NOT merge across a real motion gap wider than the merge gap", () => {
    // 1.2s of genuine motion (11→12.2) separates two holds → kept distinct.
    expect(mergeFreezeSpans([[10, 11], [12.2, 14]])).toEqual([[10, 11], [12.2, 14]]);
  });
  it("respects the exported flicker gap constant", () => {
    expect(FLICKER_MERGE_GAP_SECONDS).toBe(0.8);
  });

  it("flicker: twitch-split spans that each escape the excise are cut once merged", () => {
    // Two silent-frozen spans, each ~1.0s (passes the 0.8 gate but the 1.2s
    // lead-in swallows the whole cut → no cut individually):
    const raw: [number, number][] = [[10, 11.0], [11.5, 12.5]];
    expect(interiorExciseRanges(raw, 10, 30, { leadInSeconds: 1.2 })).toEqual([]);
    // Merged across the 0.5s twitch they form one 2.5s dead span → cut past the
    // lead-in. This is exactly the mid-beat "flicker" dead air the raw path missed.
    const merged = mergeFreezeSpans(raw);
    expect(merged).toEqual([[10, 12.5]]);
    expect(interiorExciseRanges(merged, 10, 30, { leadInSeconds: 1.2 })).toEqual([[11.2, 12.5]]);
  });
});

describe("spliceSegments", () => {
  it("cuts a range inside a single segment → two segments with correct master starts", () => {
    // one segment master[100,135] (35s on-screen); cut on-screen [13,25]
    const out = spliceSegments([{ start_seconds: 100, duration_seconds: 35 }], [[13, 25]]);
    expect(out).toEqual([
      { start_seconds: 100, duration_seconds: 13 },
      { start_seconds: 125, duration_seconds: 10 }, // master 100+25=125, on-screen 25..35
    ]);
  });
  it("cuts a range spanning two segments", () => {
    // segs: master[0,10] then master[200,210]; on-screen 0..10, 10..20; cut [6,14]
    const out = spliceSegments(
      [{ start_seconds: 0, duration_seconds: 10 }, { start_seconds: 200, duration_seconds: 10 }],
      [[6, 14]],
    );
    expect(out).toEqual([
      { start_seconds: 0, duration_seconds: 6 },
      { start_seconds: 204, duration_seconds: 6 }, // master 200+(14-10)=204, on-screen 14..20
    ]);
  });
  it("is a no-op on empty cut ranges", () => {
    const segs = [{ start_seconds: 5, duration_seconds: 8 }];
    expect(spliceSegments(segs, [])).toEqual(segs);
  });
});

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
    // footage motion ends at 23.7s, VO 15.7s, beat holds 24.5s.
    // cap = max(23.7, 15.7) + 0.4 = 24.1; excess = 0.4 < 0.8 → unchanged.
    const capped = capBeatDuration({
      current: 24.5,
      footageMotionEnd: 23.7,
      vo: 15.7,
    });
    expect(capped).toBeCloseTo(24.5, 3);
  });

  it("trims a ~2.4s frozen tail that the old 3.0s threshold let survive", () => {
    // The tightening: footage motion ends 23.7s, VO 15.7s, beat holds 26.5s.
    // cap = 24.1; excess = 2.4 — under the OLD 3.0 (kept) but over 0.8 → shrink.
    const capped = capBeatDuration({
      current: 26.5,
      footageMotionEnd: 23.7,
      vo: 15.7,
    });
    expect(capped).toBeCloseTo(24.1, 3);
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

  it("leaves a sub-threshold settle (<0.8s excess) alone", () => {
    // cap = max(8, 5.9) + 0.4 = 8.4; current 8.9 → excess 0.5 < 0.8 → unchanged.
    const capped = capBeatDuration({
      current: 8.9,
      footageMotionEnd: 8.0,
      vo: 5.9,
    });
    expect(capped).toBeCloseTo(8.9, 3);
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
    expect(DEAD_THRESHOLD_SECONDS).toBe(0.8);
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
