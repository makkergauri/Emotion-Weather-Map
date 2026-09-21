# Architecture

How the pieces fit, and the reasoning behind the two decisions that shape
everything else: the cache and the two-tier fetch.

---

## The shape of it

```
NewsAPI ──┐
          ├──> fetchers ──> dedupe ──> analyzer ──> weather_mapper ──> SQLite ──> API ──> React
RSS ──────┘                                                              ^
                                                                         └── most requests stop here
```

The last arrow is the important one. In steady state, almost no request from the
frontend reaches an external API at all.

---

## 1. Caching

### Why it exists

**Rate limits.** NewsAPI's free tier allows 100 requests a day. Without a cache,
external calls would scale with *traffic* — twelve requests every time someone
loaded the page. Nine visitors would exhaust the daily budget, and a portfolio
piece that dies when three people open it at once is worse than no portfolio
piece. With the cache, external calls scale with *time*: twelve countries every
four hours is 72 requests a day, regardless of whether one person visits or a
thousand.

**Cost.** The same argument holds for any paid tier, just with money instead of a
quota.

**Performance.** A cache read is sub-millisecond. A cold NewsAPI fetch plus
sentiment scoring for 40 headlines is closer to a second. The map should feel
immediate.

**Honesty about the data.** News moves slowly at this granularity. A country's
mean headline sentiment doesn't meaningfully change in ten minutes, so re-fetching
that often would burn quota to display noise.

### How it works

SQLite, three tables:

| Table | Holds |
| --- | --- |
| `country_sentiment` | Current reading per country, overwritten on refresh |
| `city_sentiment` | Current reading per city, same |
| `daily_snapshot` | One row per country per day, for the 7-day strip |

The third table is an addition to the brief's two. The first two only ever hold
the *current* reading — a refresh overwrites the row — so history needed somewhere
that survives that.

The TTL check happens before any external call, in `pipeline.py`. `is_fresh()`
takes `now` as an argument rather than reading the clock internally, which is what
lets the tests verify the four-hour boundary without waiting four hours or
patching `datetime` globally.

Timestamps are timezone-aware UTC throughout, converted at both boundaries.
SQLite has no date type and will happily store a naive string that later compares
wrong against an aware one — a bug that shows up as a cache that never expires, or
one that expires instantly.

### Failure handling

The requirement is that a failed fetch marks a region as "no data" rather than
crashing or showing something wrong. The implementation has one wrinkle worth
explaining.

Writing a `no_data` row into the cache would be the obvious approach, but it
means a transient blip blanks that country for the full four-hour TTL. Instead,
failures are held in an in-memory cooldown for ten minutes:

- **No cached reading** → serve `no_data`, and don't retry for ten minutes.
- **Cached reading exists** → keep serving it through the cooldown. It's minutes
  stale at worst, which beats a grey pin.

Nothing is persisted, so a restart clears the cooldown. Every failure mode
upstream — HTTP errors, rate limits, malformed XML, an expired key — is funnelled
into a single `FetchError` type, so `pipeline.py` has one thing to catch and one
response to make.

### Warm-up

On an empty cache the server schedules a background warm-up: countries fetched
sequentially with a configurable pause between each. Sequential rather than
gathered, because twelve simultaneous requests is exactly the pattern that gets a
free-tier key throttled.

It's scheduled, not awaited, so uvicorn accepts connections immediately instead of
spending thirty seconds in startup. A module-level guard ensures only one warm-up
runs at a time — without it, a dozen page loads against a cold cache would each
start their own and multiply the request count by twelve.

---

## 2. The two-tier fetch

Country and city readings come from different sources because they answer
different questions. The full reasoning is in
[methodology.md](methodology.md#3-why-country-and-city-use-different-sources);
architecturally, what matters is that both fetchers return the same `RawHeadline`
shape. Everything downstream — dedupe, scoring, mapping, caching, serving — is
identical for both tiers and doesn't know which source it's handling.

### Fallback chain

Country readings try NewsAPI first and fall through to RSS when it returns
nothing or errors. Only when *both* fail does a region become `no_data`. The
source that answered is persisted alongside the reading — recomputing it later is
impossible, since a cached row has no memory of which fetcher produced it.

That persistence needed a new `source` column on both reading tables. Because
`CREATE TABLE IF NOT EXISTS` won't alter a table that already exists, `init_db()`
checks `PRAGMA table_info` and adds missing columns on startup. Without that,
upgrading would mean deleting `cache.db` and losing the daily snapshot history
the forecast strip is built from.

The two tiers also have different loading strategies, and that difference is
deliberate:

**Countries are warmed on boot.** There are twelve, they're all visible on the
first screen, and the world map should never be empty.

**Cities are fetched on demand.** There are up to sixty, and warming all of them
would mean sixty RSS requests nobody asked for. The drill-down pays the cost for
the five cities actually opened, and `useCitiesWeather` fires them in parallel and
fills pins in as each lands, rather than blocking the layer on the slowest feed.

---

## 3. Request handling

Read endpoints split by cost:

**`/api/countries` and `/api/global-summary` never block on a fetch.** They answer
from cache and schedule stale work in the background. The map paints in
milliseconds even on a cold start, showing grey pins that fill in. Blocking would
mean a thirty-second blank screen on first load.

**Single-region endpoints fetch inline when stale.** That's one external call, and
the user is looking directly at the thing they're waiting for.

---

## 4. Module layout

Three modules aren't in the brief's structure:

**`pipeline.py`** — orchestration. Cache checks, failure policy, cooldowns,
model assembly. Without it this lands in `main.py`, which should stay a routing
table; separating it also means the fetch-and-fail logic can be tested without
going through HTTP.

**`config.py`** — environment read once at import. Plain module constants rather
than a settings library: there are eight values, and adding a dependency to parse
eight strings isn't a trade worth making.

**`regions.py`** — loads and indexes `regions.json`. The file is read once per
process instead of once per request, and city lookups arrive from URL paths in
arbitrary case, so case-insensitive matching lives in one place rather than five.

`weather_mapper.py` is deliberately the only module with no I/O, no clock and no
config — pure functions over a bounded input range. That's what makes it the one
piece that can be tested exhaustively, and it's why the thresholds live there
rather than being scattered through the pipeline.

---

## 5. Frontend

**One `MapContainer` for the whole app.** Drilling into a country doesn't mount a
new map; it flies the camera and fades the city layer in over receded country
pins. Two maps would break the continuity that the transition exists to create.

**Two pieces of navigation state.** `drilledInto` is where the camera is;
`selection` is what the panel shows. They're separate because closing the panel
shouldn't zoom you back out — impossible to express with one variable.

**Markers are React rendered once to static HTML.** Leaflet wants an HTML string.
`buildMarkerIcon` runs the icon component through `renderToStaticMarkup`, which
means the markup Leaflet inserts is inert — no React events, no re-renders. Clicks
are wired on the Leaflet `Marker` instead, and the icon animations live in the
stylesheet rather than in component state, because CSS is the only thing that
still applies inside that inert markup.

**No data-fetching library.** Four endpoints, none paginated. The real
requirements are "don't set state after unmount" and "let the user retry", and an
`AbortController` in a small hook covers both. Aborting matters more than it
looks: clicking through three countries quickly would otherwise let a slow first
response overwrite the third.

**Design tokens are CSS custom properties.** Condition colours are referenced as
`var(--sunny)` everywhere including inside dynamically built marker gradients, so
retheming is a change in one block. The one duplication across the stack is the
threshold values in `conditions.ts`, which the legend needs in order to state the
scale it's explaining — shipping a config endpoint to move four numbers would be
worse than the duplication.


---

## Manual checklist

Leaflet needs a real viewport, so the map can't be meaningfully unit tested. Walk
this before calling a change done:

- [ ] Twelve pins, each with a weather icon and country name
- [ ] Icons animate — rain falls, sun rays pulse, clouds drift
- [ ] Strong sentiment glows brighter; low-confidence pins look dimmer
- [ ] Clicking a country flies the camera in smoothly rather than jumping
- [ ] City pins appear and fill in one by one from grey
- [ ] Other countries recede but stay visible
- [ ] Panel shows condition, score, headlines with sources, and the 7-day strip
- [ ] Headline links open the publisher in a new tab
- [ ] Breadcrumb reads `World / India`, then `World / India / Bhopal`
- [ ] Zooming all the way out returns the breadcrumb to `World`
- [ ] `Escape` steps out one level at a time
- [ ] Closing the panel leaves the camera where it is
- [ ] On a cold backend, grey pins fill in without reloading the page
- [ ] An unreachable country shows a dashed grey pin and an explanation
- [ ] The station strip names its source (`SRC NEWSAPI` or `SRC RSS`)
- [ ] The panel doesn't cover the planet-mood readout
- [ ] At mobile width the panel becomes a bottom sheet
- [ ] With reduced motion enabled, transitions are instant and icons hold still