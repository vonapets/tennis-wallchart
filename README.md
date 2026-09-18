# Tennis Wallchart

Every ATP and WTA tournament worth listing — 250, 500, 1000, the Slams and both
Finals, plus the WTA 125s and the top two Challenger tiers — on one chart, from
today to the end of 2027, with the Challengers ranked. **Main draws only:
qualifying is excluded everywhere.**

Sibling to [football-calendar](https://github.com/vonapets/football-calendar)
and [cricket-calendar](https://github.com/vonapets/cricket-calendar); same
shape, a third sport, and a set of feeds that lie in a new way.

Open `calendar.html` from disk. One self-contained file, no server, no network.

> Not to be confused with `~/tennis-calendar`, which is still live and still
> useful: that is the **tactical** 14-week launch plan for 21 Sep – 31 Dec 2026,
> one Challenger a week in slot 1. This is the **season wallchart** — all tiers,
> both tours, fifteen months. The measured numbers here are copied from that
> project with their provenance, not re-derived.

## What is on it

| | |
|---|---|
| Tour | ATP and WTA, 250 / 500 / 1000, the four Slams, both Finals |
| Sub-tour | WTA 125, ATP Challenger 175 and 125 |
| Excluded | **all qualifying**, doubles, ITF, Challenger 100 and below |
| Window | 18 Sep 2026 → 31 Dec 2027, including anything still on court today |
| Combined events | 17 of them are **one row with two draws**, not two rows |

Four views: **Season** (a Gantt of the whole window), **Months** (calendar
grid), **List**, and **Challenger picks** (the ranking, with its evidence).

## The feeds, and the four ways they lie

No single source covers tennis, so there are three, and every one of them fails
*silently* — a wrong answer, never an error.

| Source | Covers | Gives |
|---|---|---|
| `api.wtatennis.com` | WTA, incl. 125 | official; exact **main-draw** dates and real tier labels |
| ESPN `site.api.espn.com` | ATP | dates and draws, and **no tier at all** |
| Wikipedia (parsed once) | Challenger 175/125 | a static table; nothing publishes Challenger draws as a feed |

**1. ESPN's year query truncates.** `?dates=2026` returns about a hundred events
and stops. Asked that way the WTA season ends on 5 October and the WTA Finals,
Wuhan, Ningbo and Tokyo do not exist — 25 tournaments deleted without one failed
request. Every ESPN pull is windowed a month at a time and merged by id.

**2. The ESPN event date is *sometimes* the qualifying start — and only
sometimes.** The US Open is published as 24 August; its main draw began on the
30th. Roland Garros is published as 18 May and starts on the 24th. But Chengdu,
Hangzhou, Tokyo and Beijing are published on the exact day their main draw
begins. The difference is whether **qualifying has been scheduled yet**: ESPN
extends an event's window backwards once it adds qualifying rounds, and before
that the event date already *is* the main-draw Monday.

Getting this wrong is a silent one-day error on every undrawn tournament, which
is what an earlier version of this did. So the date is resolved in three steps,
and every row says which one it used:

| `start_source` | Meaning |
|---|---|
| `official` | the WTA API's own main-draw date — exact |
| `drawn` | ESPN has timed the real main draw; earliest non-qualifying match |
| `undrawn` | no qualifying rows exist, so ESPN's event date is the main draw |
| `estimated` | qualifying is on the board but the main draw is not timed yet |

Only `estimated` uses an offset, and the offsets are **measured, not assumed**:
the median gap across every 2026 event that carries both a qualifying date and a
real main draw — **+7 for a Slam, +2 for everything else**. All four categories
were checked against Flashscore and agree to the day.

**3. ESPN carries no tier.** No 250, no 500, no 1000; `major` is true only for
the four Slams. ATP tiers come from `config.json`, keyed on the ESPN tournament
id, which is stable across seasons — 441 is Chengdu every year. The counts
reconcile exactly with Wikipedia's own totals: **9 Masters 1000, 16 ATP 500,
29 ATP 250**. The WTA needs none of this: its own API states the level.

**4. ESPN refuses a User-Agent.** It returns *Access Denied* for a custom agent
**and** for a browser one, and serves JSON only to curl's own default. The WTA
API is the opposite and wants to be told who is calling. `get()` takes the
agent per source for exactly this reason.

atptour.com is Cloudflare-blocked to scripted requests, including its own
calendar PDF, which is why the ATP side goes through ESPN at all.

## 2027 is projected, and drawn as such

**No source publishes any 2027 tennis yet.** Neither ESPN nor the WTA API returns
a single event for it. Without projection this chart would empty out in November
and stay near-empty through Q1 2027 — which is exactly the period a launch
decision is made in.

So the whole 2026 season is shifted forward **364 days** — 52 weeks exactly, so
a tournament keeps its weekday *and* its week of the year — and drawn **hatched
and faded**, with `~` after the name. Real fixtures replace it the moment a feed
has them, historically in December. The toggle above the chart hides it.

This is why `fetch_start` in `config.json` is earlier than `window_start`: the
projection needs a whole season to shift, so January onward is pulled even
though only September onward is shown. Without it, 2027 would have no
Australian Open, no Wimbledon and no US Open.

## The Challenger picks

Ranked, not sized — and the distinction is the whole point.

**Every Challenger row is `[E] none`.** No individual Challenger has settled
history on Polymarket or Kalshi. A dollar figure here would look like evidence,
and there is none, so the output is an order of preference built from three
things:

| Factor | Weight | What it rests on |
|---|---|---|
| Tier | 175 > 125 | a 175 draws a materially stronger field |
| North America | ×2.38 | NA Challengers median **$83.9M** on Kalshi against **$35.2M** elsewhere |
| A clear week | ×1.25 | a Challenger sharing a week with a Slam or a Masters is fighting for attention it will not get |

**The North America factor is a tiebreaker, not a law.** That cohort is
confounded with Kalshi's 11 July product launch, and the playbook it comes from
says so in as many words. It is the third input for a reason.

Tour events are sized differently, because they *can* be: each carries the
class-A Polymarket benchmark for its tier, which is a measurement. Confidence
labels are the sibling projects': `measured`, `range`, `none`.

## Running it

```bash
python3 sync.py            # pull all three sources, diff against yesterday
python3 sync.py --dry-run  # pull and diff, write nothing
python3 picks.py           # rank the Challengers
python3 build.py           # rebuild the page
open calendar.html
```

Stdlib only, no dependencies, no key. `./run.sh` does the lot with logging.

## Safety rails

`sync.py` will not publish bad data. It keeps the previous snapshot if both
live sources come back empty, refuses to overwrite when a pull returns under
**60%** of the previous tournament count — a gutted fetch, not a quiet week —
and records per-feed failures in the payload so the page can say so rather than
quietly show less. It also diffs against the last snapshot, so a moved
main draw is recorded in `data/changes.json` rather than silently applied.

## What the pieces do

| File | What it is |
|---|---|
| `config.json` | Tiers, colours, the Challenger table, the benchmarks and the pick weights. **Edit this, not the code.** |
| `sync.py` | Pulls the three sources, merges combined events, strips qualifying, projects 2027. |
| `picks.py` | Ranks the Challengers and sizes the tour events. |
| `build.py` | Turns the data into `calendar.html`. |
| `template.html` | The page. Only touch this to change how it looks. |
| `data/fixtures.json` | Today's snapshot. |
| `data/changes.json` | Every main draw that has moved. Never overwritten. |

### Changing what counts

`launch_tiers` is the full tier list; `default_on` is what the page shows before
anyone clicks anything (tour level only — the 125s and Challengers are one click
away). `city_aliases` exists because the sources disagree about place names: the
WTA calls Wimbledon *Wimbledon* and ESPN calls it *London*, and without the alias
the tournament is listed twice.
