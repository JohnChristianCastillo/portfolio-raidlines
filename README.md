# Raidline

Read how the best parses spend their cooldowns, then copy the timing.

Pick a boss, a difficulty and a spec. Raidline pulls the top ten ranked parses from
Warcraft Logs and lays each one out as a timeline against a shared scale, so ten logs
of different lengths can be compared at a glance. Click any player and you get their
cooldown usage as a Method Raid Tools reminder note, ready to paste into the game.

Inspired by [lorrgs.io](https://lorrgs.io), deliberately narrower: one curated spell
list per spec rather than everything, self-hosted, no accounts.

> A timeline is a reference, not a script. Copying someone's timings without knowing
> why they fell where they did will not make them work for your group.

## Status

MVP. Subtlety Rogue, one tier at a time, absolute-time reminder export.

| Working | Not yet |
|---|---|
| Boss / difficulty / spec selection, driven by the live Warcraft Logs zone list | More specs (the catalog is per-spec already, they just need authoring) |
| Top 10 parses per boss and difficulty, cooldown timelines on one shared scale | Phase-relative MRT anchors (`{time:0:05,pg2}`) |
| Per-group spell toggles, filtered client-side | Boss ability track above the player rows |
| MRT reminder export, scoped to the toggled spells | Load an arbitrary log to compare yourself against |
| Trinkets detected automatically, labelled and toggled by item | Buff duration bars, rather than cast markers alone |
| Equipped trinkets and hero talent tree shown per row | Filtering or grouping the board by hero tree |
| Talent loadout export, pasteable into the game | |
| Offline fixture mode, so it runs with no API credentials at all | |

## Running it locally

Two processes. The backend serves the data API on 8600, Vite serves the SPA on 5173
and proxies `/api` to it.

```
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python tools\make_demo_fixtures.py
.venv\Scripts\python -m uvicorn app.main:app --port 8600
```

```
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

With no credentials configured it runs on generated demo fixtures and says so in a
banner. That is enough to exercise the whole UI: eight bosses, three difficulties,
ten parses each.

## Live data

Raidline reads the public Warcraft Logs v2 API. Register a client at
[warcraftlogs.com/api/clients](https://www.warcraftlogs.com/api/clients/) with
**Public Client unchecked**, then:

```
cp backend/.env.example backend/.env
# fill in RAIDLINE_WCL_CLIENT_ID and RAIDLINE_WCL_CLIENT_SECRET
```

The redirect URL the form insists on is never used. Raidline uses the client
credentials flow against `/api/v2/client`, which is public data and involves no
browser redirect. The authorization-code flow and its redirect URL are only for
reading a signed-in user's own private reports, which Raidline never does.

The rate limit is point-based (3600/hour by default), so every response is cached to
disk under `backend/data/cache`. Cast queries are deliberately unfiltered: measured
against the live API a filtered and an unfiltered cast query both cost 2 points, so
narrowing them bought nothing and cost the trinket detection. `GET /api/budget`
reports what is left.

## Adding spells

`backend/app/spells.py` is the only file that knows which spells exist. Add an entry
and it becomes a toggle, gets fetched, and can be exported. Remove it and it vanishes
from all three. Spell IDs come from the wowhead URL: `/spell=185313/shadow-dance`.

Potions and trinkets are not in the catalog. Both are discovered per board from what
the ranked players actually used: trinkets from gear slots 12 and 13 matched against
casts, potions from the alchemy and potion icon families. Gear is matched first,
since Freightrunner's Flask is a trinket carrying an alchemy flask icon.

For the groups that are hand-curated, get IDs from a real log rather than from
memory, because a wrong one does not error, it silently matches nothing:

```
python tools\discover.py --encounter <boss id> --difficulty 5
```

That prints every ability the top parse actually cast, each as a catalog line ready
to paste in.

## API

| Endpoint | Returns |
|---|---|
| `GET /health` | liveness, and whether live data or fixtures are in use |
| `GET /api/meta` | specs, difficulties, the tracked-spell catalog |
| `GET /api/zones` | raid tiers and their bosses, newest first |
| `GET /api/timelines?encounter=&difficulty=&spec=` | the board, plus the spell groups for it |
| `GET /api/talents?code=&fight=&actor=` | one player's talent loadout string |
| `GET /api/budget` | remaining Warcraft Logs point budget |

## Layout

```
backend/
  app/
    config.py            settings, credentials, cache TTLs
    spells.py            the tracked-spell catalog, the file you edit
    wcl/                 OAuth, GraphQL, disk cache, fixture fallback
    services/            zones and boss list; ranking -> timeline
    routers/api.py       the HTTP surface
    fixtures/            recorded or generated responses (not committed)
  tools/
    make_demo_fixtures.py  synthetic offline demo data
    capture.py             record real responses as fixtures
    discover.py            list what a real parse actually cast, to curate spells.py
    herotrees.py           check the configured hero trees against live parses
frontend/
  src/
    api.ts               backend types and calls
    mrt.ts               the reminder-string format
    components/          controls, toggles, timeline, modal
    styles/app.css       all styling
```

## Notes and limitations

- A pre-pull potion falls outside the logged fight window, so it does not appear on
  the timeline. Everything from the pull onward does.
- Some trinkets surface twice, as the item's own cast and as its effect. Both are
  real cast events, so both are shown rather than guessing which to hide.
- Private, deleted or unreadable reports cost that one row rather than the page; the
  board says which player was dropped and why.
- Only `cast` events are drawn. `begincast` is discarded, otherwise every ability
  with a cast time would appear twice.
