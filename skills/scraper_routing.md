# IPL Oracle — Scraper Routing Table

Source of truth for which tool to use for each data source.

| Data needed | Tool | Notes |
|-------------|------|-------|
| Player career stats (T20/IPL) | Playwright → ESPNcricinfo | JS-rendered, 800ms delay |
| Player stats at specific venue | Playwright → ESPNcricinfo ground filter | 1.5s delay, max 3 concurrent |
| Live playing XI + Impact Pool | Playwright → IPLT20 (primary), Cricbuzz stealth (fallback) | Cricbuzz needs playwright-stealth |
| IPL 2026 fixture schedule | Playwright → IPLT20 | JS-rendered |
| Live scorecard (ongoing match) | Playwright → Cricbuzz stealth | playwright-stealth mandatory |
| Injury / team / selection news | Google News RSS → SerpAPI | Free RSS: news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en |
| Weather at venue | httpx → OpenWeatherMap | REST API, no JS needed |
| Historical career records | httpx + bs4 → Howstat | Static HTML |
| Report agent ad-hoc research | MCP web_search + web_fetch | Only when Claude Code is runtime |

## Politeness Rules (ALWAYS apply)

- 800ms delay between Playwright page loads
- 1.5s delay between ESPNcricinfo venue-stat queries (slower endpoint)
- Max 5 concurrent Playwright instances for stats; max 3 for venue queries
- Realistic User-Agent on every request
- `playwright-stealth` on any Cricbuzz page

## ESPNcricinfo Ground Filter URL Pattern

```
https://stats.espncricinfo.com/ci/engine/player/{player_id}.html?class=6;ground={ground_id};template=results;type=batting
```

- `class=6` = T20 cricket
- `ground` = ground ID from `espncricinfo_ground_ids.json`
- `type=batting` or `type=bowling`

## IPLT20 Schedule URL Pattern

```
https://www.iplt20.com/matches/fixtures
```

## Cricbuzz Live Score URL Pattern

```
https://www.cricbuzz.com/live-cricket-scorecard/{match_id}
```
