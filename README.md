# Rivals Atlas

A personal hobby project for analysing your own Marvel Rivals matches. It fetches your match history from rivalsmeta.com, shows it in a
dashboard, lets you explore with statistics, hero graphs, and lets you analyse complex insights with a knowledge-graph agent about it.

<p align="center"><img src="docs/demo.gif" width="720" alt="A 25 second tour of the app"></p>

<table>
  <tr>
    <td><img src="docs/screenshots/explore.webp" alt="Explore graph"></td>
    <td><img src="docs/screenshots/ask.webp" alt="Ask"></td>
  </tr>
</table>

| Page | Content |
|---|---|
| **Overview** | Rank journey by season, win rate, recent form, role split and highlights |
| **Heroes** | Win rate per hero next to the site's meta numbers, and your averages next to everyone else's on the same hero |
| **Maps** | Win rate by map, and a hero by map grid |
| **Patterns** | Results by weekday, hour and session, with an activity calendar |
| **Squad** | Your regular teammates and how each party combination did |
| **Explore** | Filter by map, role, bans, time of day or party, and see the result as a hero graph or a breakdown |
| **Agents** | **Ask**: a chat with the knowledge-graph agent, where every number comes from a query you can open and check. **Insights**: what the Coach, the Tilt guard, the Squad synergy agent and the Matchup advisor found in the matches, each sentence next to the numbers it rests on |
| **Data** | What is stored, and fetching match history |

## How it fits together

![Architecture](docs/architecture.svg)

More detail: [docs/how-it-works.md](docs/how-it-works.md).

## Install

### Without a terminal (Windows and macOS)

Download the zip for your computer from the [latest release](https://github.com/touhi99/rivals-atlas/releases/latest),
unzip it, and start the launcher inside:

- **Windows:** `RivalsAtlas-windows.zip` — double-click `Start Rivals Atlas.bat`.
- **macOS:** `RivalsAtlas-macos.zip` — right-click `Start Rivals Atlas.command` and choose **Open** the first time
  (macOS blocks downloaded scripts that are double-clicked).

The first launch installs what is missing (a minute or two) and opens the dashboard in your browser; later launches
open it straight away. The Terminal window (macOS) or console window (Windows) is the app — closing it stops it.
On macOS the bundle carries the OpenSSL 3 libraries the graph engine needs, so Homebrew is not required.

The Agents page needs a language model; every other page works without one.

### From a terminal

Needs [uv](https://docs.astral.sh/uv/). Node.js 20 or newer is needed only to build the front end from source.

```
git clone <this repository>
cd rivals-atlas
./scripts/setup.sh                 # installs the Python side and the front end, and builds the web app
uv run rivals-atlas serve          # http://127.0.0.1:8000
```

`uv run rivals-atlas serve --open` opens the browser once the dashboard is ready. If port 8000 is taken, the next
free port is used and printed.

On the first start there is no data. Open **Data**, paste the address of a player's page on rivalsmeta.com (it ends with a
number), read the notice, tick the box and press **Fetch**. Later fetches download only new matches, and a stopped fetch resumes.

From a terminal: `uv run rivals-atlas fetch --profile <id>` (then `--yes` after reading the notice), and `uv run rivals-atlas import`
to rebuild the database from the stored files. Never run `import` while a fetch is running.

## Be gentle with the data source

All match data comes from [rivalsmeta.com](https://rivalsmeta.com), through the endpoints its own pages use. It is a free site run
by someone else, so please treat it kindly:

- **Ranked is the default.** Fetch quick play only if you want it (**Mode** on the Data page, or `--mode 1`).
- **The default pace is one request every 3 seconds.** A long history takes hours, so leave it running.
- The tool never retries and stops at the first refusal.
- Fetch your own history, once, and then only what is new. Do not use this to collect other people's data in bulk.
- The site may change or block this at any time. Following its terms of use is the responsibility of whoever runs the tool.

If this tool or its data is used in another project, article or video, please credit rivalsmeta.com for the data and link to this repository, https://github.com/touhi99/rivals-atlas, for the tool.

## The Agents page needs a model

The Agents page (Ask and Insights) needs an Anthropic API key, or Ollama or LM Studio running locally. The rest of the app works without a model.

```
cp .env.example .env     # then set RIVALS_ATLAS_LLM and, for Anthropic, ANTHROPIC_API_KEY
```

| `RIVALS_ATLAS_LLM` | Model |
|---|---|
| `anthropic:claude-haiku-5-5` | Claude through the Anthropic API |
| `ollama:<model>` | Any model from the [Ollama library](https://ollama.com/library) |
| `lmstudio:<model>` | Any model loaded in [LM Studio](https://lmstudio.ai) |

The model only writes one read-only query. The rows shown come straight from the data, and the model's own sentence is marked unchecked.

Insights run the model too: when you press **Run now** on the Insights tab, and after that again after each fetch that finds new matches. That
uses tokens, and with Anthropic the query results are sent to the API.

## Data

Everything is stored in `./data` (change the place with `RIVALS_ATLAS_DATA`): the downloaded match files in `data/raw/`, the database
`rivals.db` and the graph file `graph.lbdb`. Delete the folder to start over, or run `rivals-atlas import` to rebuild the database and
graph from the raw files.

## Development

```
uv run ruff check src
uv run mypy src
```

## Future work

- More default stats
- Streaming answer
- Hero profile / general stats from patch note or official stat note
- A small test suite for the win-rate maths, the importer and the read-only guards

## License

MIT, see [LICENSE](LICENSE).

Not affiliated with Marvel, NetEase or rivalsmeta.com.
