# How it works

![Architecture](architecture.svg)

Four flows share one local data folder (`data/`): **ingest** brings the match history in, **serve** turns it into pages, **ask** answers
free-form questions from it, and **insights** lets agents point out what stands out in the matches.

## 1. Ingest: from the site to a database

| Step | What happens | Code |
|---|---|---|
| Fetch | One player's history and matches are read from rivalsmeta.com, 1 request every 3s, resumable | `ingest/fetch.py` |
| Keep | Every document is stored untouched under `data/raw/`, so the database can be rebuilt from it in seconds with `rivals-atlas import` | `data/raw/` |
| Import | Documents are checked for the expected shape, then written to SQLite; seasons the history list did not cover are inferred | `ingest/importer.py` |
| Derive | Hero-pair edges and team-up facts are computed; the graph file (LadybugDB) is rebuilt | `graph/` |

## 2. Serve: from the database to a page

| Layer | Role | Code |
|---|---|---|
| Queries | Every SQL statement, parameterised; the web app opens the database read-only | `core/queries.py` |
| Analysis | Win rates with ranges, patterns, Explore, hero pairs | `analysis/`, `graph/network.py` |
| Payloads | One function per page shapes the data as JSON | `web/payloads.py` |
| API | FastAPI routes and the app's single page | `web/api.py` |
| App | The React dashboard | `frontend/` |

## 3. Ask: from a question to a checked answer

| Step | What happens | Code |
|---|---|---|
| Agent | A Haystack agent that writes the query and calls the tools | `agents/` |
| Prompt | The model gets the graph schema and the hero, map and mode names, from plain text files | `prompts/` |
| Query | The model, Claude or a local one, writes **one** Cypher query | `agents/llm.py` |
| Guard | One read statement on a read-only database, 5s limit, 200 rows | `graph/store.py` |
| Answer | The rows are shown as a table straight from the data; the model's sentence is labelled unchecked | `web/ask.py` |
| Check | Numbers in the model's sentence that no query returned are flagged | `agents/evidence.py` |

## 4. Insights: the agents at work

The Ask tab of the Agents page uses one agent. Insights use a small team: a Coordinator asks the Coach, the Tilt guard, the Squad synergy agent and the Matchup advisor what stands out in
the matches, and the observations that hold up are shown on the Insights tab.

| Agent | What it does | Used by |
|---|---|---|
| Cartographer | Turns a question into one read-only graph query | Ask tab |
| Coordinator | Reads a request, asks the right agents and combines what they found | Insights, `rivals-atlas ask` |
| Coach | Compares heroes with each other, with 50% and with the site's figures, in ranked and quick play | Insights |
| Tilt guard | Checks whether results change by game number in a session | Insights |
| Squad synergy | Compares results with and without a regular teammate on the same side | Insights |
| Matchup advisor | Finds enemy heroes and bans that go with better or worse results | Insights |

| Step | What happens | Code |
|---|---|---|
| Trigger | **Run now** on the Insights tab or `rivals-atlas insights`; after that, again after each fetch that added matches | `web/insights.py` |
| Context | The agents are told the most played heroes per mode and how to pick earlier seasons, which they cannot look up | `agents/__init__.py` |
| Delegate | The Coordinator asks all four; each calls its own tools on the database | `agents/` |
| Observe | Each agent writes short observations: a sentence, a relation (higher, lower, similar, above 50%, above the site figure) and the tool calls it rests on. It writes no numbers | `agents/observations.py` |
| Check | The app runs those calls itself and keeps an observation only if the relation holds: a difference needs 95% ranges that are apart, and "similar" needs narrow ones | `agents/observations.py` |
| Show | Kept observations are saved to the data folder and drawn as cards, the sentence beside the numbers it rests on | `agents/insights.py` |

Small samples rarely show a clear difference, so many observations are dropped and a run may keep only a few. The app checks the numbers and
the relation, not the wording of the sentence, which is why each card shows the bars too. A small local model finds little; Claude finds more.

## Folders

| Folder | Holds |
|---|---|
| `core/` | configuration, table definitions, filters, `queries.py` |
| `ingest/` | fetch, parse, import, hero meta |
| `analysis/` | statistics, patterns, findings, Explore |
| `graph/` | hero pairs, the graph file, team-up facts |
| `agents/` | tools, evidence check, model agents, insights |
| `web/` | `api.py` routes, `payloads.py` page data, `ask.py` job runner |
| `prompts/` | model instructions as text files |
| `frontend/` | the React app, built into `web/ui/` (not stored in git) |

Rates are over decided games (draws left out), carry a 95% interval, and colour appears only when the whole interval is on one side of
50%.
