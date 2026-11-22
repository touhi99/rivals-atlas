# Design notes

Reasons behind rules in the code that names alone do not explain. The overall flow is in
[how-it-works.md](how-it-works.md).

## Data conventions

- Mode ids: `2` ranked, `1` quick play, `0` both. A filter with mode `0` adds no mode condition.
- A map has one id in ranked and another in quick play; filters and the hero-map table treat both ids as one map
  (`names.same_map_ids`, `names.canonical_map_id`).
- Hero id `0` marks a game left before any hero was played. It is not a hero and is skipped in hero tallies.
- In the hero graph, map nodes have negative ids, so they cannot collide with hero ids. Every hero stays a node,
  even one without links, so search finds it.
- Tallies are `[games, wins, losses]` or `[wins, losses, games]` per group; rates use decided games only.
- Matches the site's history list does not cover yet have no map and are grouped as "No map data", sorted last.
- A teammate with at least `REGULAR_GAMES` (5) games on the tracked player's side is a regular. Party size counts
  regulars: `0` none, `1` duo, `2` trio.
- A session ends after a gap of `SESSION_GAP` (90 minutes) between matches, whatever the result. Session position is
  numbered per mode; `POSITION_CAP` (5) means the fifth game or later.
- Rank points exist only in ranked. Quick play has a hidden rating that the site does not show.
- In `parse.py`, the hero of a match is the one with the most play time; on a tie the later line wins.

## Ingest

- Fetch pace is 1 s (`normal`) or 3 s (`gentle`) between requests.
- Refresh: the site's own Update button stays disabled for `REFRESH_COOLDOWN` (30 minutes) after a request. A refresh
  is polled every 10 s, for at most 180 s.
- Page files are named `m{mode}_s{season}_skip{skip}.json`, since modes do not share pages.
- New matches shift every page, so all pages of a season are read again while that season is current or was still
  current at the last run. Once a run has read a season's later pages while a newer season already existed, nothing
  can be added to it and those pages are read from disk.
- `player.json` is stored as received, since it may hold platform and visibility fields.
- The hero meta is optional: a failure to read it is reported, and the matches are still imported.
- A team-up's site win rate is shown only after `MIN_TEAMUP` (200) matches across all ranks.
- POST requests go out only through the real transport or one passed in explicitly, so a fake GET transport in a
  test does not reach the network.

## Ladders

- A ladder chain continues when a match's start score equals the previous end score within `TOL` (1.6 points).
- `MIN_GAP` is in tiers.
- A chain is a side chain when the main ladder has matches both before and after it.

## Statistics and patterns

- Pattern cards apply a Bonferroni correction across each card's buckets.
- A week needs `TREND_MIN` (8) decided games to get a point on the trend line.
- The party table has 2^n rows, so it is limited to `MAX_PARTY` (5) teammates.
- Explore draws at most `MATCH_LIMIT` (200) table rows, `TIMELINE_LIMIT` (400) timeline dots and `RELATION_EDGES` (36)
  hero-map links. Ban filters take up to `MAX_BANS` heroes in each list: all banned, or none banned.
- The Explore graph ranks partners by a weighted win rate pulled toward 50% by `K` phantom games (default 16), so
  83% over 6 games does not outrank 62% over 45. The list still shows the raw rate and the game count.
- `COUNTER` edges are directed: the wins are hero `a`'s.
- The side of the second hero in a graph lens is chosen by code from the relation name, not from request text.

## Database and graph file

- The web app opens one SQLite connection per request and uses it one call at a time. FastAPI may run the dependency
  and the handler on different worker threads, so the connection is opened with `check_same_thread=False`.
- A missing table in an old database reads as empty.
- The graph file is stale when a query hits a property it lacks (a file built before a schema change); a rebuilt
  file drops every cached Explore entry.
- With no database yet, the app creates an empty one so every page can render its empty state.
- `core/filters.py` and `web/v1.py` import late to break import cycles.

## Agents

- `MAX_STEPS` (12) caps model calls per agent run, so one question cannot loop and run up cost.
- The Ask tab calls the Cartographer directly; going through the Coordinator costs two more model calls (about 7 s).
- The Cartographer has no claim tool: its rows are printed from the data by `Ledger.report`, and asking the model to
  also write one claim per row cost about 6 s of output tokens. Its prompt uses `_rules_cartographer.md`, without the
  claim rule. Its schema text is generated from the graph file.
- `squad_synergy` and `matchup_advisor` prompts exist only for the insights run.
- An agent result keeps the model's own words (`framing`, not checked) apart from the checked claims (`report`).
  Numbers in the model's text that no tool result contains are listed as unverified.
- A rate in a claim matches a tool result within `RATE_TOLERANCE` (0.005), so a claim rounded to a whole percent
  still matches. For `cypher_query`, `n` is a row count, not a sample size, so it is not added to the text.
- Tool errors (bad arguments, Cypher syntax, timeouts) go back to the model as text so it can retry.
- Tool `n` is decided games for rates, and items or points for other tools; `enough` means `n` reaches
  `stats.MIN_GAMES` for rates, or that there is anything to report.
- An observation of relation "similar" needs both 95% ranges narrower than `MAX_SIMILAR_WIDTH` (0.2, about 100
  games). "No clear difference" counts as a failed insight, so similar observations are dropped and older saved runs
  that hold them are filtered on display.
- The insights scope (ranked, quick play or both) is enforced by the app, whatever the model chose to look at. Each
  scope has its own saved file; a saved file in an older format reads as missing and the agents must run again.
- Tool results go to the model without their match id lists: a count, plus the 5 most recent ids for agents that have
  `match_lookup`. The ledger keeps every id for the evidence links. The full lists were 95% or more of each result and are
  re-sent on every agent step, so one Insights run reached millions of input tokens.
- Insights run only when asked (Run now or the CLI). A fetch marks saved insights stale instead, since every run calls
  the model several times and costs tokens.
- One insights job runs at a time, whatever its scope.
- The Anthropic generator is created without `temperature`, which that SDK does not take.
- `rivals_atlas.agents.usage_report` is an optional module outside this repository; the app runs without it.

## macOS OpenSSL patch

- The patch rewrites these Mach-O load commands: `LC_LOAD_DYLIB`, `LC_ID_DYLIB`, `LC_LOAD_WEAK_DYLIB`,
  `LC_REEXPORT_DYLIB`, `LC_LAZY_LOAD_DYLIB`.
- The copied library is made writable first, since the Homebrew copy is read-only, and its quarantine flag is removed,
  since the launcher folder comes from a downloaded zip.
- It runs before anything imports LadybugDB.

## Front end

- FastAPI serves the built app. In development, Vite proxies `/api` to the Python server.
- POST requests carry the header that `web/guard.py` checks.
- The filter lives in the URL, so a view can be bookmarked and older pages can link into it.
- Pages keep showing the previous data while a new filter loads.
- In Ask tables, a column named `...rate` holds a fraction and `...pct` a percentage.
- A question still running when the Ask page closes has no answer to come back to and is marked as such.
- Recharts tooltips use the theme's popover colours for the text, since the default is black on any background.
