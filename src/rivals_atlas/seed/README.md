# Seed dictionaries

Ids in the match data mean nothing to a person. These files map them to names. Edit or add entries freely;
`names.py` is the only code that reads them.

| File | Maps | Source |
|---|---|---|
| `heroes.json` | hero id to name | copied once from the site's `/characters` page; add new heroes here |
| `maps.json` | map id to "Map · Mode" name | table found in the site's front-end script (an id is a map in one mode). Users can override or add names in `<data dir>/maps.json` |
| `tiers.json` | rank tier level to name | the game's ladder: 3 divisions per tier, then Eternity and One Above All |
| `roles.json` | hero id to role class: 1 vanguard, 2 duelist, 3 strategist (the site's own class numbers) | written from game knowledge, not copied from a source. Checked against 3,288 ranked teams: 61% come out exactly 2-2-2 and no single change improves that by more than 1 point (The Hood, 1066, is the only hint). Please review; fix freely |
| `seasons.json` | the site's season number to the game's season name | the site numbers 1 = Season 0, 2 = Season 1, 3 = Season 1.5 and so on |

Unknown ids show as `Hero 1234` / `Map 1234` so nothing is hidden.
