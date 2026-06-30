import { describe, it, expect } from "vitest";
import { evaluateTiming, evaluateBeat, type TimingBeatInput } from "./timingeval";
import type { ActionMark as AM } from "./actionsync";

const resolver = (m: Record<string, number>) => (w: string) => (w in m ? m[w] : null);

function beat(marks: AM[], words: Record<string, number>, voSec = 21): TimingBeatInput {
  return { beatId: "s3", marks, resolveWord: resolver(words), voSec };
}

describe("evaluateBeat", () => {
  it("counts anchored fields and the lag the warp removes", () => {
    const s = evaluateBeat(
      beat(
        [
          { on_seconds: 6, words: ["description"] }, // src 6 → vo 6 (lag 0)
          { on_seconds: 20, words: ["contact"] }, // src 20 → vo 12 (lag 8)
        ],
        { description: 6, contact: 12 },
      ),
    );
    expect(s.anchored).toBe(2);
    expect(s.wordMatchable).toBe(2);
    expect(s.worstLagRemovedS).toBeCloseTo(8, 1);
    expect(s.meanLagRemovedS).toBeCloseTo(4, 1);
    expect(s.droppedInversions).toBe(0);
  });

  it("flags inversions: word matchable but dropped for order", () => {
    const s = evaluateBeat(
      beat(
        [
          { on_seconds: 6, words: ["description"] }, // vo 6
          { on_seconds: 10, words: ["scale"] }, // vo 3 — spoken BEFORE description → inversion
        ],
        { description: 6, scale: 3 },
      ),
    );
    expect(s.wordMatchable).toBe(2);
    expect(s.anchored).toBe(1);
    expect(s.droppedInversions).toBe(1);
  });

  it("a field the narration never names is not word-matchable", () => {
    const s = evaluateBeat(beat([{ on_seconds: 5, words: ["unsaid"] }], { other: 3 }));
    expect(s.wordMatchable).toBe(0);
    expect(s.anchored).toBe(0);
  });
});

describe("evaluateTiming", () => {
  it("full coverage ⇒ pass, score 5", () => {
    const v = evaluateTiming([
      beat([{ on_seconds: 6, words: ["description"] }, { on_seconds: 20, words: ["contact"] }], { description: 6, contact: 12 }),
    ]);
    expect(v.coverage).toBe(1);
    expect(v.verdict).toBe("pass");
    expect(v.overallScore).toBe(5);
    expect(v.syncedFields).toBe(2);
  });

  it("half the named fields drift ⇒ warn, score ~2.5", () => {
    // 4 named fields, only 2 monotonic → coverage 0.5
    const v = evaluateTiming([
      beat(
        [
          { on_seconds: 2, words: ["a"] }, // vo 1
          { on_seconds: 4, words: ["b"] }, // vo 2
          { on_seconds: 6, words: ["c"] }, // vo 1.5 — inversion
          { on_seconds: 8, words: ["d"] }, // vo 1.8 — inversion
        ],
        { a: 1, b: 2, c: 1.5, d: 1.8 },
      ),
    ]);
    expect(v.wordMatchableFields).toBe(4);
    expect(v.syncedFields).toBe(2);
    expect(v.coverage).toBe(0.5);
    expect(v.verdict).toBe("warn");
    expect(v.overallScore).toBe(2.5);
    expect(v.findings.join(" ")).toMatch(/different ORDER/);
  });

  it("very low coverage ⇒ fail", () => {
    const v = evaluateTiming([
      beat(
        [
          { on_seconds: 2, words: ["a"] },
          { on_seconds: 4, words: ["b"] },
          { on_seconds: 6, words: ["c"] },
          { on_seconds: 8, words: ["d"] },
          { on_seconds: 10, words: ["e"] },
        ],
        { a: 1, b: 0.9, c: 0.8, d: 0.7, e: 0.6 }, // descending vo → only first anchors
      ),
    ]);
    expect(v.coverage).toBeLessThan(0.4);
    expect(v.verdict).toBe("fail");
  });

  it("no named field anywhere ⇒ n/a (null score, pass)", () => {
    const v = evaluateTiming([beat([{ on_seconds: 5, words: ["unsaid"] }], { other: 3 })]);
    expect(v.coverage).toBeNull();
    expect(v.overallScore).toBeNull();
    expect(v.verdict).toBe("pass");
    expect(v.findings.join(" ")).toMatch(/n\/a/);
  });

  it("empty walkthrough ⇒ n/a pass", () => {
    const v = evaluateTiming([]);
    expect(v.verdict).toBe("pass");
    expect(v.totalFieldMarks).toBe(0);
  });
});
