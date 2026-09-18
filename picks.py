#!/usr/bin/env python3
"""
Rank the Challengers, and size every tour event, into data/picks.json.

  python3 picks.py

The calendar says what is on. This says what is worth listing, and it is the
half that can be wrong quietly, so every row carries what its number rests on.

The method is the one the 17 September launch playbook arrived at, applied to a
whole season instead of one quarter. Nothing here is re-derived; the measured
inputs are copied into `config.benchmarks` with their provenance.

  * **Tour events are sized from their tier.** The class-A Polymarket benchmark
    for the tier, which is a measurement, not a guess.

  * **Challengers cannot be sized at all.** No individual Challenger has
    settled history on either venue, so every Challenger row is `[E] none` --
    the strongest honest label available. The ranking between them is a prior
    built from three things:

      tier        a 175 draws a materially stronger field than a 125
      geography   North American Challengers median $83.9M on Kalshi against
                  $35.2M elsewhere. This is a TIEBREAKER, not a law: the
                  cohort is confounded with Kalshi's 11 July launch, and the
                  playbook says so in as many words.
  Note what is deliberately NOT a factor: a clash with a big tour event. The
  playbook this comes from never penalised one -- it ran a Challenger in slot 1
  every single week, including Shanghai week 2, Paris Masters week, the WTA
  Finals and the ATP Finals. The 175s in particular are scheduled alongside
  Masters events on purpose, which is where their top-100 fields come from, so
  a clash penalty would cut straight against the tier weight.

The output is deliberately a rank, not a dollar figure. A number here would
look like evidence, and there is none.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CFG = json.loads((ROOT / "config.json").read_text())
P = CFG["picks"]
B = CFG["benchmarks"]

# a Challenger in the same week as one of these is competing for attention
LOUD = {"Grand Slam", "ATP 1000", "WTA 1000", "ATP Finals", "WTA Finals"}

TIER_BENCH = {
    "Grand Slam": ("SLAM_ATP", "SLAM_WTA"),
    "ATP 1000": ("1000_ATP", None), "WTA 1000": (None, "1000_WTA"),
    "ATP 500": ("500_ATP", None), "WTA 500": (None, "500_WTA"),
    "ATP 250": ("250_ATP", None), "WTA 250": (None, "250_WTA"),
}


def iso_week(d: str) -> tuple[int, int]:
    x = datetime.strptime(d, "%Y-%m-%d").isocalendar()
    return (x[0], x[1])


def main() -> int:
    fx = DATA / "fixtures.json"
    if not fx.exists():
        print("no data/fixtures.json - run sync.py first")
        return 1
    rows = json.loads(fx.read_text())["tournaments"]

    # which weeks already carry a headline tour event
    loud_weeks: dict[tuple, list[str]] = {}
    for r in rows:
        t = r.get("headline_tier")
        if t in LOUD:
            loud_weeks.setdefault(iso_week(r["start"]), []).append(r["name"])

    na = {c.lower() for c in P["north_america"]}
    picks = []
    for r in rows:
        if r.get("tour") != "Challenger":
            continue
        tier = r["tier"]
        w = iso_week(r["start"])
        clash = loud_weeks.get(w, [])
        country = (r.get("country") or "").lower()
        is_na = any(n in country for n in na)

        score = P["tier_weight"].get(tier, 1.0)
        why = [f"{tier}"]
        if is_na:
            score *= P["na_premium"]
            why.append(f"North America (x{P['na_premium']} Kalshi median, tiebreaker only)")
        # the clash is recorded for context but NOT scored -- see the module note
        if clash:
            why.append("runs alongside " + ", ".join(sorted(set(clash))[:2]))

        picks.append({
            "name": r["name"], "tier": tier, "venue": r.get("venue", ""),
            "start": r["start"], "end": r.get("end"),
            "surface": r.get("surface", ""),
            "projected": bool(r.get("projected")),
            "score": round(score, 3),
            "north_america": is_na,
            "runs_alongside": bool(clash),
            "clash": sorted(set(clash))[:3],
            "evidence": P["evidence_default"],
            "confidence": P["confidence_default"],
            "why": why,
        })

    picks.sort(key=lambda p: (-p["score"], p["start"]))
    for i, p in enumerate(picks, 1):
        p["rank"] = i

    # tour events, sized from the class-A tier benchmark
    tour = []
    for r in rows:
        t = r.get("headline_tier")
        if t not in TIER_BENCH:
            continue
        atp_k, wta_k = TIER_BENCH[t]
        vals = [B["polymarket_classA"][k] for k in (atp_k, wta_k)
                if k and k in B["polymarket_classA"]]
        tour.append({
            "name": r["name"], "tier": t, "tours": r.get("tours", []),
            "start": r["start"], "end": r.get("end"),
            "venue": r.get("venue", ""), "projected": bool(r.get("projected")),
            "benchmark": max(vals) if vals else None,
            "confidence": "range",
            "basis": "class-A Polymarket benchmark for the tier",
        })
    tour.sort(key=lambda x: x["start"])

    out = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": P["_method"],
        "caveat": P["_confidence_note"],
        "na_premium_caveat": P["_na_premium_note"],
        "challenger_picks": picks,
        "tour_events": tour,
    }
    (DATA / "picks.json").write_text(json.dumps(out, indent=1))

    print(f"picks: {len(picks)} challengers ranked, {len(tour)} tour events sized")
    print()
    print("  TOP 12 CHALLENGER PICKS")
    for p in picks[:12]:
        flag = "NA" if p["north_america"] else "  "
        print(f"   {p['rank']:>2}. {p['start']} {p['tier']:15s} {flag} "
              f"{p['name'][:32]:34s} {p['venue'][:24]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
