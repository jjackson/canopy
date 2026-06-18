#!/usr/bin/env python3
"""Per-beat VO-vs-footage overrun report for a connect-videos render.

Makes the "VO overruns the clips" timing warning precise and repeatable:
for every beat it cross-references the footage length (from the spec) with
the ACTUAL synthesized voiceover duration (from the ElevenLabs audio-cache
sidecars the render already wrote) and the narration text. A body beat whose
VO is longer than its clip is held on a frozen last frame for the difference
— this report shows exactly which beats, by how much, and at what speaking
rate, so the overrun is a number you can act on, not a vibe.

Usage:
    python vo_report.py --spec programs/<slug>/runs/<run>/spec.yaml
    python vo_report.py --spec <spec.yaml> --audio-cache assets/audio

Footage per beat:
  - body_walkthrough: walkthrough.<id>.duration_seconds (the clip range), or
    the beat's `seconds` if no walkthrough entry.
  - other beats (intro_title/outro_card/…): the beat's `seconds` (a fixed card
    length, not footage) — shown for completeness; VO is compared against it.

VO per beat: the audio-cache sidecar whose `text` matches narration.by_beat[id]
(exact match after whitespace/quote normalization). `duration_sec` is the real
synthesized length.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent


def _norm(s: str) -> str:
    """Normalize for matching: collapse whitespace, unify quote glyphs."""
    s = (s or "").strip()
    s = s.replace("“", '"').replace("”", '"')
    s = s.replace("‘", "'").replace("’", "'")
    s = re.sub(r"\s+", " ", s)
    return s


def _word_count(s: str) -> int:
    return len(re.findall(r"\S+", s or ""))


def load_audio_index(cache_dir: Path) -> dict[str, dict]:
    """Map normalized VO text -> {duration_sec, words} from the audio cache."""
    index: dict[str, dict] = {}
    for j in sorted(cache_dir.glob("*.json")):
        try:
            d = json.loads(j.read_text())
        except Exception:
            continue
        text = d.get("text")
        dur = d.get("duration_sec")
        if text is None or dur is None:
            continue
        index[_norm(text)] = {"duration_sec": float(dur), "file": j.name}
    return index


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--spec", required=True, help="path to the rendered run's spec.yaml")
    p.add_argument("--audio-cache", default=None,
                   help="audio-cache dir (default <engine>/assets/audio)")
    p.add_argument("--rate", type=float, default=2.2,
                   help="reference speaking rate (words/sec) for eleven_turbo_v2 (default 2.2)")
    args = p.parse_args()

    import yaml  # PyYAML required (engine ships it)

    spec = yaml.safe_load(Path(args.spec).read_text())
    cache = Path(args.audio_cache) if args.audio_cache else ENGINE_DIR / "assets" / "audio"
    audio = load_audio_index(cache)

    beats = spec.get("beats") or []
    walkthrough = spec.get("walkthrough") or {}
    by_beat = (spec.get("narration") or {}).get("by_beat") or {}

    rows = []
    tot_footage = tot_vo = tot_overrun = 0.0
    for b in beats:
        bid = b.get("id")
        kind = b.get("kind", "")
        # footage / card length
        wt = walkthrough.get(bid) or {}
        footage = float(wt.get("duration_seconds") if wt.get("duration_seconds") is not None
                        else b.get("seconds", 0) or 0)
        vo_text = by_beat.get(bid, "") or ""
        words = _word_count(vo_text)
        hit = audio.get(_norm(vo_text)) if vo_text.strip() else None
        vo = hit["duration_sec"] if hit else 0.0
        matched = bool(hit) if vo_text.strip() else None  # None = no VO for this beat
        overrun = max(0.0, vo - footage)
        wps = (words / vo) if vo else 0.0
        rows.append((bid, kind, footage, vo, words, wps, overrun, matched))
        tot_footage += footage
        tot_vo += vo
        tot_overrun += overrun

    # ---- print ----
    print(f"VO overrun report — {spec.get('slug', '?')}")
    print(f"  spec: {args.spec}")
    print(f"  audio cache: {cache}  ({len(audio)} clips indexed)\n")
    hdr = f"{'beat':<8}{'kind':<18}{'footage':>9}{'VO':>8}{'words':>7}{'w/s':>6}{'overrun':>9}  match"
    print(hdr)
    print("-" * len(hdr))
    for bid, kind, footage, vo, words, wps, overrun, matched in rows:
        m = "—" if matched is None else ("ok" if matched else "MISS")
        flag = "  <<" if overrun > 3 else ""
        print(f"{bid:<8}{kind:<18}{footage:>8.1f}s{vo:>7.1f}s{words:>7}{wps:>6.1f}{overrun:>8.1f}s  {m}{flag}")
    print("-" * len(hdr))
    print(f"{'TOTAL':<8}{'':<18}{tot_footage:>8.1f}s{tot_vo:>7.1f}s"
          f"{'':>7}{'':>6}{tot_overrun:>8.1f}s")
    overall_wps = (sum(r[4] for r in rows) / tot_vo) if tot_vo else 0.0
    print(f"\n  measured speaking rate: {overall_wps:.2f} words/sec "
          f"(report assumes {args.rate} w/s)")
    print(f"  sum of per-beat held-frame overrun: {tot_overrun:.1f}s")
    miss = [r[0] for r in rows if r[7] is False]
    if miss:
        print(f"  ⚠ unmatched VO (no audio-cache hit) for beats: {', '.join(miss)} "
              f"— re-render so the cache holds this run's audio, or check text drift.")
    # Per-beat trim guidance: to fit footage at the measured rate, target words.
    print("\n  To fit footage (trim narration), target word counts at measured rate:")
    for bid, kind, footage, vo, words, wps, overrun, matched in rows:
        if overrun > 3 and footage > 0 and overall_wps > 0:
            target_words = int(footage * overall_wps)
            print(f"    {bid}: {words} words → ~{target_words} words "
                  f"(cut ~{words - target_words}) to fit {footage:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
