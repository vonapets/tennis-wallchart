#!/usr/bin/env python3
"""
Pull the ATP and WTA calendars and write data/fixtures.json.

  python3 sync.py            # pull, diff against yesterday, write
  python3 sync.py --dry-run  # pull and diff, write nothing

Three sources, because no single one covers the sport:

  WTA         api.wtatennis.com   official; exact dates AND real tier labels
  ATP         ESPN public feed    dates and draws; carries NO tier at all
  Challenger  static table        nothing publishes Challenger draws as a feed

Four things about these feeds decide the shape of this file. Each one fails
silently -- a wrong answer, never an error -- so each is handled explicitly.

  * **ESPN's year query truncates.** `?dates=2026` returns about a hundred
    events and stops. Asked that way the WTA season ends on 5 October and the
    WTA Finals, Wuhan, Ningbo and Tokyo do not exist: 25 tournaments deleted
    without one failed request. Every ESPN pull here is windowed a month at a
    time and merged by id.

  * **The ESPN event date is the QUALIFYING start.** The US Open is published
    as 24 August and its main draw began on the 30th; Roland Garros is
    published as 18 May and starts on the 24th. This calendar is explicitly
    main-draw only, so the main-draw Monday is derived from the rounds and the
    qualifying date is kept beside it rather than shown.

  * **A combined event is one tournament, not two.** Indian Wells is 411-2026
    in both the ATP and the WTA feed. Rows merge on id and carry a `tours` list.

  * **ESPN has no tier.** No 250, no 500, no 1000; `major` is true only for the
    four Slams. ATP tiers come from `config.json`, keyed on the ESPN tournament
    id, which is stable across seasons (441 is Chengdu every year). The WTA does
    not need that crutch -- its own API states the level.
"""
from __future__ import annotations

import calendar as _cal
import json
import subprocess
import sys
import time
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
CFG = json.loads((ROOT / "config.json").read_text())

ESPN = "https://site.api.espn.com/apis/site/v2/sports/tennis/{lg}/scoreboard"
WTA_API = "https://api.wtatennis.com/tennis/tournaments/"
UA = "tennis-wallchart/1.0"
PAUSE, TIMEOUT = 0.25, 40

WTA_LEVELS = {"Grand Slam": "Grand Slam", "Finals": "WTA Finals",
              "WTA 1000": "WTA 1000", "WTA 500": "WTA 500",
              "WTA 250": "WTA 250", "WTA 125": "WTA 125"}


def log(m: str) -> None:
    print(m, flush=True)


def get(url: str, ua: str | None = None):
    """Shell out to curl: ESPN answers it but 403s urllib.

    Do NOT send a User-Agent to ESPN. It returns "Access Denied" for a custom
    agent *and* for a browser one, and serves JSON only to curl's own default.
    The WTA API is the opposite and wants to be told who is calling.
    """
    cmd = ["curl", "-s", "--max-time", str(TIMEOUT)]
    if ua:
        cmd += ["-H", f"User-Agent: {ua}"]
    r = subprocess.run(cmd + [url], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError("no response")
    return json.loads(r.stdout)


# ------------------------------------------------------------------ WTA
def pull_wta() -> tuple[list[dict], int]:
    """Official API. Authoritative for dates and tier; ITF rows are dropped."""
    rows, fails = [], 0
    for page in range(14):
        q = urllib.parse.urlencode({"page": page, "pageSize": 100,
                                    "from": CFG.get("fetch_start", CFG["window_start"]),
                                    "to": CFG["window_end"]})
        try:
            d = get(f"{WTA_API}?{q}", ua=UA)
        except Exception as exc:                                  # noqa: BLE001
            log(f"   ! WTA page {page}: {exc}")
            fails += 1
            break
        got = (d or {}).get("content") or (d if isinstance(d, list) else None)
        if not got:
            break
        for x in got:
            level = x.get("level") or ((x.get("tournamentGroup") or {}).get("level"))
            if level not in WTA_LEVELS:
                continue                       # ITF and anything unlabelled
            start, end = x.get("startDate"), x.get("endDate")
            if not start:
                continue
            # "Qatar TotalEnergies Open 2026 - Doha, Qatar" -> the name only
            title = re.sub(r"\s*-\s*[^-]+,\s*[A-Za-z ]+$", "",
                           (x.get("title") or "")).strip()
            title = re.sub(r"\s+20\d\d$", "", title)
            city = (x.get("city") or "").title()
            rows.append({
                "key": f"wta:{x.get('liveScoringId') or title}:{start}",
                "name": title or city, "tour": "WTA", "tier": WTA_LEVELS[level],
                "venue": ", ".join(p for p in [city, x.get("country")] if p),
                "city": city, "start": start, "end": end or start,
                "surface": x.get("surface") or "",
                "draw": x.get("singlesDrawSize"),
                "prize": x.get("prizeMoney"),
                # the WTA API publishes the MAIN DRAW date, not qualifying
                "start_source": "official", "src": "api.wtatennis.com",
            })
        time.sleep(PAUSE)
        if len(got) < 100:
            break
    return rows, fails


# ------------------------------------------------------------------ ATP
def is_qualifying(comp: dict) -> bool:
    return ((comp.get("round") or {}).get("displayName", "")
            .strip().lower().startswith("qualif"))


def pull_atp_season(year: int) -> tuple[dict, int]:
    """Month-windowed. See the note about the year query truncating."""
    events, fails = {}, 0
    for month in range(1, 13):
        last = _cal.monthrange(year, month)[1]
        url = (f"{ESPN.format(lg='atp')}"
               f"?dates={year}{month:02d}01-{year}{month:02d}{last}")
        try:
            payload = get(url)
        except Exception as exc:                                  # noqa: BLE001
            log(f"   ! ATP {year}-{month:02d}: {exc}")
            fails += 1
            continue
        for e in payload.get("events", []):
            events[e["id"]] = e
        time.sleep(PAUSE)
    return events, fails


def pull_atp() -> tuple[list[dict], int]:
    tiers = CFG["atp_tiers"]
    offsets = CFG["main_draw_offset_days"]
    rows, fails = [], 0
    for year in CFG["season_years"]:
        events, f = pull_atp_season(year)
        fails += f
        log(f"   ATP {year}: {len(events)} tournaments"
            + (f"  ({f} month(s) failed)" if f else ""))
        for e in events.values():
            tid = e["id"].split("-")[0]
            tier = tiers.get(tid)
            if not tier:
                continue                       # not a tour-level event we map
            venue, main, singles, quals = "", [], 0, 0
            for g in e.get("groupings", []):
                slug = (g.get("grouping") or {}).get("slug", "")
                for c in g.get("competitions", []):
                    if not venue:
                        venue = (c.get("venue") or {}).get("fullName", "") or ""
                    if is_qualifying(c):
                        quals += 1
                        continue
                    if "singles" not in slug:
                        continue
                    singles += 1
                    # timeValid marks a slot ESPN has really scheduled;
                    # placeholder rows before a draw all carry the event date
                    # and would drag the start back onto qualifying week.
                    if c.get("timeValid") and c.get("date"):
                        main.append(c["date"][:10])
            qual_start = e.get("date", "")[:10]
            if main:
                start, how = min(main), "drawn"
            else:
                days = offsets.get(tier, offsets["_default"])
                start = (datetime.strptime(qual_start, "%Y-%m-%d")
                         + timedelta(days=days)).strftime("%Y-%m-%d")
                how = "estimated"
            rows.append({
                "key": f"atp:{e['id']}", "espn_id": tid, "name": e.get("name", ""),
                "tour": "ATP", "tier": tier, "venue": venue,
                "start": start, "end": e.get("endDate", "")[:10],
                "qualifying_start": qual_start, "main_draw_matches": singles,
                "qualifying_matches": quals,
                "start_source": how, "src": "espn",
            })
    return rows, fails


# ------------------------------------------------------------ challengers
def pull_challengers() -> list[dict]:
    out = []
    for c in CFG["challengers"]:
        if c["tier"] not in ("Challenger 175", "Challenger 125"):
            continue                      # 100s and below are not launch candidates
        start = c.get("week") or ""
        if not start:
            continue
        end = (datetime.strptime(start, "%Y-%m-%d")
               + timedelta(days=6)).strftime("%Y-%m-%d")
        out.append({
            "key": f"chal:{c['name']}:{start}", "name": c["name"],
            "tour": "Challenger", "tier": c["tier"],
            "venue": f"{c['city']}, {c['country']}",
            "country": c["country"], "start": start, "end": end,
            "surface": c.get("surface", ""),
            "start_source": "static", "src": "wikipedia-static",
        })
    return out


# ------------------------------------------------------------------ merge
def merge_combined(rows: list[dict]) -> list[dict]:
    """Indian Wells is one tournament with two draws, not two tournaments."""
    by_slot: dict[tuple, dict] = {}
    for r in rows:
        if r["tour"] == "Challenger":
            by_slot[r["key"]] = r
            continue
        # same host city in the same ISO week => one combined event with two
        # draws. Slicing the date string instead would put Beijing's WTA start
        # (30 Sep) and its ATP start (1 Oct) in different buckets and list the
        # China Open twice.
        city = (r.get("city") or (r.get("venue") or "").split(",")[0]).strip().lower()
        city = CFG.get("city_aliases", {}).get(city, city)
        try:
            iso = datetime.strptime(r["start"], "%Y-%m-%d").isocalendar()
            slot = (city, iso[0], iso[1])
        except ValueError:
            slot = (city, r["start"])
        cur = by_slot.get(slot)
        if not cur:
            r = dict(r)
            r["tours"] = [r["tour"]]
            r["tiers"] = {r["tour"]: r["tier"]}
            by_slot[slot] = r
            continue
        if r["tour"] not in cur["tours"]:
            cur["tours"].append(r["tour"])
        cur["tiers"][r["tour"]] = r["tier"]
        # prefer the official WTA dates where the two disagree
        if r.get("start_source") == "official":
            cur["start"], cur["end"] = r["start"], r["end"]
            cur["start_source"] = "official"
        cur["name"] = cur.get("name") or r.get("name")
    out = []
    for v in by_slot.values():
        v.setdefault("tours", [v.get("tour", "")])
        v.setdefault("tiers", {v.get("tour", ""): v.get("tier")})
        order = CFG["launch_tiers"]
        present = [t for t in v["tiers"].values() if t in order]
        v["headline_tier"] = min(present, key=order.index) if present else v.get("tier")
        out.append(v)
    return out


def project(rows: list[dict]) -> list[dict]:
    cfg = CFG["projection"]
    if not cfg.get("enabled"):
        return []
    shift = timedelta(days=cfg["shift_days"])
    have_years = {(r["start"] or "")[:4] for r in rows}
    if str(cfg["to_season"]) in have_years:
        # the feed has started publishing the next season; project only what
        # it has not reached yet
        published = {(r.get("name"), (r["start"] or "")[:4]) for r in rows}
    else:
        published = set()
    out = []
    for r in rows:
        if not (r["start"] or "").startswith(str(cfg["from_season"])):
            continue
        # the Challenger table is static 2026, but the Challenger calendar is
        # as stable week-to-week as the tour one, and without this the window
        # from 18 Sep holds only nine of the forty-five 175s and 125s. Projected
        # rows carry BOTH caveats: static source and projected date.
        if (r.get("name"), str(cfg["to_season"])) in published:
            continue
        n = json.loads(json.dumps(r))
        n["projected"] = True
        n["key"] = f"proj:{r['key']}"
        for k in ("start", "end"):
            if r.get(k):
                n[k] = (datetime.strptime(r[k], "%Y-%m-%d") + shift).strftime("%Y-%m-%d")
        n["start_source"] = "projected"
        out.append(n)
    return out


def diff(old: list[dict], new: list[dict]) -> list[dict]:
    before = {r["key"]: r for r in old}
    seen = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    changes = []
    for r in new:
        p = before.get(r["key"])
        if not p or p.get("projected") or r.get("projected"):
            continue
        if p.get("start") != r.get("start") and p.get("start_source") != "estimated":
            changes.append({"key": r["key"], "name": r["name"], "field": "start",
                            "from": p.get("start"), "to": r.get("start"), "seen": seen})
    return changes


def main() -> int:
    dry = "--dry-run" in sys.argv
    log("tennis-wallchart sync")
    wta, f1 = pull_wta()
    log(f"   WTA: {len(wta)} tournaments (official API)")
    atp, f2 = pull_atp()
    chal = pull_challengers()
    log(f"   Challenger 175/125: {len(chal)} (static table, no feed exists)")

    if not wta and not atp:
        log("!! both live sources empty - keeping the previous snapshot")
        return 1

    rows = merge_combined(wta + atp) + chal
    for r in rows:
        r.setdefault("projected", False)
    rows += project(rows)

    lo, hi = CFG["window_start"], CFG["window_end"]
    # everything above is pulled from fetch_start so the projection has a whole
    # season to shift; only now is the display window applied.
    rows = [r for r in rows if r.get("start") and lo <= r["start"] <= hi]
    rows.sort(key=lambda r: (r["start"], r.get("name") or ""))

    out = DATA / "fixtures.json"
    prev = json.loads(out.read_text()).get("tournaments", []) if out.exists() else []
    floor = CFG["safety"]["min_fraction_of_previous"]
    if prev and len(rows) < len(prev) * floor:
        log(f"!! only {len(rows)} rows against {len(prev)} last time "
            f"- refusing to overwrite a good snapshot")
        return 1

    changes = diff(prev, rows)
    if dry:
        log(f"   dry run: {len(rows)} rows, {len(changes)} change(s), nothing written")
        return 0

    cp = DATA / "changes.json"
    hist = json.loads(cp.read_text()) if cp.exists() else []
    hist.extend(changes)
    cp.write_text(json.dumps(hist, indent=1))

    out.write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window": [lo, hi],
        "feed_failures": f1 + f2,
        "tournaments": rows,
    }, indent=1))

    live = sum(1 for r in rows if not r["projected"] and r["src"] != "wikipedia-static")
    log(f"   wrote {len(rows)} rows "
        f"({live} live, {sum(1 for r in rows if r['projected'])} projected 2027, "
        f"{sum(1 for r in rows if r['src'] == 'wikipedia-static')} challenger)")
    log(f"   changes this run: {len(changes)} (total recorded {len(hist)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
