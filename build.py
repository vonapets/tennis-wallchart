#!/usr/bin/env python3
"""
Join data/fixtures.json and data/picks.json into calendar.html.

  python3 build.py

One self-contained file with the data embedded, so it opens from disk, from
Pages, or from an emailed copy, with no server and no network.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CFG = json.loads((ROOT / "config.json").read_text())


def main() -> int:
    fx = DATA / "fixtures.json"
    if not fx.exists():
        print("no data/fixtures.json - run sync.py first")
        return 1
    payload = json.loads(fx.read_text())
    rows = payload["tournaments"]
    picks = {}
    if (DATA / "picks.json").exists():
        picks = json.loads((DATA / "picks.json").read_text())

    live = [r for r in rows if not r.get("projected") and r["src"] != "wikipedia-static"]
    proj = [r for r in rows if r.get("projected")]
    chal = [r for r in rows if r["src"] == "wikipedia-static"]
    combined = [r for r in rows if len(r.get("tours", [])) > 1]

    pulled = payload["generated"][:10]
    subtitle = (
        f"<b>{len(rows)}</b> tournaments from {payload['window'][0]} to "
        f"{payload['window'][1]} — <b>{len(live)}</b> published, "
        f"<b>{len(proj)}</b> projected into 2027, <b>{len(chal)}</b> Challenger. "
        f"Main draws only; qualifying is excluded everywhere. "
        f"<b>{len(combined)}</b> combined ATP+WTA events are one row, not two. "
        f"Pulled {pulled}."
    )

    blob = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "subtitle": subtitle,
        "window": payload["window"],
        "tier_colors": CFG["tier_colors"],
        "launch_tiers": CFG["launch_tiers"],
        "core_tiers": CFG["core_tiers"],
        "default_on": CFG["default_on"],
        "tournaments": rows,
        "picks": picks,
    }

    html = (ROOT / "template.html").read_text()
    html = html.replace("__DATA__", json.dumps(blob, separators=(",", ":")))
    (ROOT / "calendar.html").write_text(html)
    (ROOT / "index.html").write_text(html)

    print(f"calendar.html written ({len(html):,} bytes)")
    print(f"   {len(rows)} tournaments | {len(live)} live | {len(proj)} projected "
          f"| {len(chal)} challenger | {len(combined)} combined")
    if picks:
        print(f"   {len(picks.get('challenger_picks', []))} challenger picks ranked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
