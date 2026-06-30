import { describe, it, expect } from "vitest";
import {
  resolveAnchors,
  buildActionWarp,
  composeWithSegments,
  planActionWarp,
  RATE_MIN,
  RATE_MAX,
  type ActionMark,
} from "./actionsync";

// A tiny resolver: a map of word → VO seconds.
const resolver = (m: Record<string, number>) => (w: string) =>
  w in m ? m[w] : null;

describe("resolveAnchors", () => {
  it("binds each mark to the first candidate word that resolves", () => {
    const marks: ActionMark[] = [
      { on_seconds: 4, words: ["nope", "description"] },
      { on_seconds: 12, words: ["contact", "email"] },
    ];
    const anchors = resolveAnchors(marks, resolver({ description: 6, contact: 12 }), 21);
    expect(anchors).toEqual([
      { src: 4, out: 6 },
      { src: 12, out: 12 },
    ]);
  });

  it("drops inversions (a later field whose word is spoken earlier)", () => {
    const marks: ActionMark[] = [
      { on_seconds: 4, words: ["description"] },
      { on_seconds: 10, words: ["timeline"] }, // spoken BEFORE description → inversion
      { on_seconds: 16, words: ["contact"] },
    ];
    const anchors = resolveAnchors(
      marks,
      resolver({ description: 6, timeline: 3, contact: 12 }),
      21,
    );
    // timeline@3 inverts after description@6 → dropped; description + contact kept.
    expect(anchors).toEqual([
      { src: 4, out: 6 },
      { src: 16, out: 12 },
    ]);
  });

  it("collapses duplicate-src marks (scroll_to + fill on same field)", () => {
    const marks: ActionMark[] = [
      { on_seconds: 4, words: ["description"], kind: "scroll_to" },
      { on_seconds: 6, words: ["description"], kind: "fill" },
    ];
    const anchors = resolveAnchors(marks, resolver({ description: 6 }), 21);
    expect(anchors).toEqual([{ src: 4, out: 6 }]); // earliest src wins, same out dropped
  });

  it("ignores words resolving outside [0, voSec]", () => {
    const marks: ActionMark[] = [{ on_seconds: 4, words: ["late"] }];
    expect(resolveAnchors(marks, resolver({ late: 99 }), 21)).toEqual([]);
  });
});

describe("buildActionWarp", () => {
  it("returns [] with no resolvable anchors (caller falls back)", () => {
    const marks: ActionMark[] = [{ on_seconds: 4, words: ["unknown"] }];
    expect(
      buildActionWarp({
        marks,
        resolveWord: resolver({}),
        footageOnscreenSec: 28,
        voSec: 21,
        beatSec: 28,
      }),
    ).toEqual([]);
  });

  it("warps footage so the field lands on its word (the core fix)", () => {
    // Footage: 28s; VO: 21s. 'contact' (#9 of ~16 fields) is at on-screen 20s in
    // footage but spoken at 12s in VO. The warp should SPEED the footage before
    // 'contact' so it arrives by 12s, then slow after.
    const marks: ActionMark[] = [{ on_seconds: 20, words: ["contact"] }];
    const pieces = buildActionWarp({
      marks,
      resolveWord: resolver({ contact: 12 }),
      footageOnscreenSec: 28,
      voSec: 21,
      beatSec: 28,
    });
    // two pieces: [0,12]→src[0,20] (rate 20/12≈1.667), [12,28]→src[20,28] (rate 8/16=0.5→clamped 0.7)
    expect(pieces.length).toBe(2);
    expect(pieces[0]).toMatchObject({ outStartSec: 0, outDurSec: 12, srcStartSec: 0 });
    expect(pieces[0].rate).toBeCloseTo(20 / 12, 2);
    // first piece is faster than 1× (UI catches up to the VO) — the whole point
    expect(pieces[0].rate).toBeGreaterThan(1);
    expect(pieces[1].outStartSec).toBeCloseTo(12, 3);
  });

  it("clamps the rate into [RATE_MIN, RATE_MAX]", () => {
    // extreme: tiny footage span must map to a big output gap → rate floored
    const pieces = buildActionWarp({
      marks: [{ on_seconds: 1, words: ["w"] }],
      resolveWord: resolver({ w: 20 }),
      footageOnscreenSec: 2,
      voSec: 21,
      beatSec: 24,
    });
    for (const p of pieces) {
      expect(p.rate).toBeGreaterThanOrEqual(RATE_MIN);
      expect(p.rate).toBeLessThanOrEqual(RATE_MAX);
    }
  });

  it("output pieces are contiguous and cover the beat", () => {
    const pieces = buildActionWarp({
      marks: [
        { on_seconds: 6, words: ["a"] },
        { on_seconds: 18, words: ["b"] },
      ],
      resolveWord: resolver({ a: 5, b: 14 }),
      footageOnscreenSec: 28,
      voSec: 21,
      beatSec: 28,
    });
    expect(pieces[0].outStartSec).toBe(0);
    for (let i = 1; i < pieces.length; i++) {
      const prevEnd = pieces[i - 1].outStartSec + pieces[i - 1].outDurSec;
      expect(pieces[i].outStartSec).toBeCloseTo(prevEnd, 2);
    }
    const last = pieces[pieces.length - 1];
    expect(last.outStartSec + last.outDurSec).toBeCloseTo(28, 1);
  });
});

describe("composeWithSegments", () => {
  it("single segment (teach scene) maps on-screen→master with start offset", () => {
    const pieces = [
      { outStartSec: 0, outDurSec: 12, srcStartSec: 0, rate: 1.667 },
      { outStartSec: 12, outDurSec: 16, srcStartSec: 20, rate: 0.7 },
    ];
    const segs = [{ start_seconds: 100, duration_seconds: 28 }]; // master starts at 100
    const out = composeWithSegments(pieces, segs);
    expect(out).toHaveLength(2);
    expect(out[0].assetStartSec).toBe(100); // on-screen 0 → master 100
    expect(out[0].rate).toBe(1.667);
    expect(out[1].assetStartSec).toBeCloseTo(120, 1); // on-screen 20 → master 120
  });

  it("splits a piece that straddles a de-dwell jump-cut", () => {
    // Two segments: master[100,110] then master[200,210] → on-screen [0,10],[10,20].
    const segs = [
      { start_seconds: 100, duration_seconds: 10 },
      { start_seconds: 200, duration_seconds: 10 },
    ];
    // One piece at rate 1 spanning on-screen [5,15] → must split at the boundary (10).
    const pieces = [{ outStartSec: 0, outDurSec: 10, srcStartSec: 5, rate: 1 }];
    const out = composeWithSegments(pieces, segs);
    expect(out).toHaveLength(2);
    expect(out[0].assetStartSec).toBeCloseTo(105, 3); // 5s into seg1 → master 105
    expect(out[0].outDurSec).toBeCloseTo(5, 3);
    expect(out[1].assetStartSec).toBeCloseTo(200, 3); // boundary → seg2 start (jump-cut)
    expect(out[1].outDurSec).toBeCloseTo(5, 3);
  });
});

describe("planActionWarp (end-to-end)", () => {
  it("produces master-domain pieces for a teach-scene field bind", () => {
    const out = planActionWarp({
      marks: [{ on_seconds: 20, words: ["contact"] }],
      resolveWord: resolver({ contact: 12 }),
      footageOnscreenSec: 28,
      voSec: 21,
      beatSec: 28,
      segments: [{ start_seconds: 50, duration_seconds: 28 }],
    });
    expect(out.length).toBeGreaterThan(0);
    expect(out[0].assetStartSec).toBe(50);
    expect(out[0].rate).toBeGreaterThan(1); // UI sped up to meet the VO
  });

  it("empty when nothing resolves", () => {
    expect(
      planActionWarp({
        marks: [{ on_seconds: 5, words: ["x"] }],
        resolveWord: resolver({}),
        footageOnscreenSec: 10,
        voSec: 8,
        beatSec: 10,
        segments: [{ start_seconds: 0, duration_seconds: 10 }],
      }),
    ).toEqual([]);
  });
});
