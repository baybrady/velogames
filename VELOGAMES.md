# Velogames Fantasy League Tracker — Google Apps Script

Automatically polls the Velogames website for new stage results and writes a full breakdown to a Google Sheet shared with league members. Everything lives in a **single file: `Code.gs`**. To reuse for a new race, update `CONFIG` only.

`Parser.gs` and `Sheets.gs` are superseded by the merged `Code.gs` and can be ignored.

---

## TODO

- **Sheet/cell formatting** — currently applied manually in the spreadsheet. Would be nicer to own it in `Code.gs` (header row colors, column widths, heatmap on stage scores, etc.) so the sheet is fully reproducible from the script alone.
- **Chart data ranges** — the ranges passed to the column and line charts aren't quite right and need investigation/correction.
- the sheet should contain links to (a) each team, and (b) the leage.
---

## File overview

### `Code.gs` — everything

Defines `CONFIG` (race name, league URL, stage count, poll hours, notification email) and `FETCH_OPTS` (browser User-Agent needed to get past Cloudflare). Contains three logical sections separated by banner comments: **Orchestration**, **Parsers**, and **Sheet writing**.

| Function | Purpose |
|---|---|
| `checkAndUpdate()` | Time-trigger entry point. Skips outside 10:00–23:00 UTC. Fetches league scores, computes a score fingerprint, and only fires `fullScrape()` when the fingerprint changes (stored in `PropertiesService`). |
| `fullScrape(teams)` | Walks every team roster, then every unique rider profile, building three data maps: `riderMeta`, `teamRosters`, `riderStages`. Aborts if any roster comes back empty (protects sheet from a bad scrape). Calls `writeAllData()`. |
| `fetchUrl(url)` | Retries up to 3× with exponential back-off. |
| `notifyLeague(teams)` | Sends a plain-text Gmail with current standings to `CONFIG.notifyEmail`. |
| `forceUpdate()` | Manual one-shot full refresh — run this from the Apps Script editor to populate the sheet immediately. |
| `installTrigger()` | Run once to install a 30-minute time-based trigger on `checkAndUpdate`. Deletes any existing triggers first. |

**Pages scraped:**
- `leaguescores.php?league=118055015` — team list + total scores (fingerprint source)
- `teamroster.php?tid=XXXX` — rider IDs, costs, pro teams, DNF status per team
- `riderprofile.php?rider=XXXX` — per-stage point breakdown for every unique rider (~25–36 riders)

---

### Parsers (in `Code.gs`)

Pure regex-based parsers (no DOM, no Cheerio — Apps Script has neither).

| Function | Input | Output |
|---|---|---|
| `parseLeague(html)` | League scores page | `[{ tid, name, manager, score }, ...]` |
| `parseRoster(html)` | Team roster page | `[{ id, name, proTeam, cost, finished }, ...]` |
| `parseRiderProfile(html)` | Rider profile page | `Array(numStages)` of per-stage points (index 0 = Stage 1, last index = Final Classifications) |

`parseRoster` sets `finished: true/false` based on a `fa-check` / `fa-times` icon in the HTML — used downstream for DNF detection.

`parseRiderProfile` maps both `Stage N` rows and the `Final Classifications` row (which maps to `stages[numStages - 1]`).

---

### Sheet writing (in `Code.gs`)

Writes everything to a single sheet named **Riders**. The sheet is cleared and rewritten on every scrape; charts are created only once (`if (!chartsExist)`).

#### Column layout (1-indexed, example with 4 teams)

| Cols | Content |
|---|---|
| 1 – numTeams | Team membership flags (1 = rider is on that team, blank = not) |
| numTeams+1 | Rider name |
| numTeams+2 | Pro team |
| numTeams+3 | Cost — also used as the row-header column in the summary sections |
| numTeams+4 … +4+n-1 | Stage points (Stage 1 → Stage 21 → "Bonus" / Final Classifications) |
| totalCol | Total points |
| effCol | Efficiency (total ÷ cost, 1 d.p.) |

#### Sheet sections (top to bottom)

1. **Header row** — team names, Rider, Pro Team, Cost, stage numbers, Total, Efficiency
2. **Rider rows** — one per unique rider, sorted alphabetically by first name. Stages not yet completed show `-`; stages after a DNF rider's last scored stage also show `-`.
3. **Daily section** — per-team points scored in each stage (two blank rows gap from rider section)
4. **Cumulative section** — running total per team per stage (two blank rows gap from daily section)
5. **Column chart** — Daily stage points (stages on x-axis, teams as series)
6. **Line chart** — Cumulative points (same orientation)

Both summary sections write their row-header (team name) and section label into the **Cost column** (`costCol = numTeams + 3`) so that the chart range `[costCol … stageStart+n-1]` is contiguous: `name | s1 | s2 | … | sN`.

A note on cell A1 records the last-updated time in ET, PT, and Adelaide time.

`styleHeaderRow` and `greenHeatmap` are defined in `Sheets.gs` but not called — they are stubs left over from an earlier version that applied formatting programmatically. Formatting is now set manually in the sheet; the script intentionally leaves it alone.

---

## Setting up in Google Sheets

### 1. Create the spreadsheet

Open (or create) the Google Sheet you want to use. No manual setup of sheets or columns is needed — the script creates and populates everything.

### 2. Open Apps Script

**Extensions → Apps Script**

This opens the bound Apps Script project for the spreadsheet.

### 3. Paste the script

The editor starts with a single `Code.gs` file — that's all you need. Paste the entire contents of `Code.gs` into it.

The `appsscript.json` manifest is also saved in this folder. In the Apps Script editor you can view it via **Project Settings → Show "appsscript.json" manifest file in editor**. It sets the V8 runtime, STACKDRIVER exception logging, and the four required OAuth scopes.

### 4. Update CONFIG

In `Code.gs`, verify or update:

```js
const CONFIG = {
  raceName:     'Tour de France 2026',
  leagueUrl:    'https://www.velogames.com/velogame/2026/leaguescores.php?league=XXXXXXX',
  baseUrl:      'https://www.velogames.com/velogame/2026/',
  numStages:    22,       // 21 race stages + Final Classifications
  pollStartUtc: 10,       // only scrape between 10:00 and 23:00 UTC
  pollEndUtc:   23,
  notifyEmail:  'you@example.com',
};
```

### 5. Authorize the script

Select `forceUpdate` from the function dropdown and click **Run**. Google will prompt for permissions — grant access to:
- **Google Sheets** (SpreadsheetApp)
- **Gmail** (GmailApp — for score-change notifications)
- **External URLs** (UrlFetchApp — to scrape Velogames)
- **Script Properties** (PropertiesService — fingerprint storage)
- **Script Triggers** (ScriptApp — for `installTrigger`)

### 6. Populate the sheet for the first time

With `forceUpdate` still selected, click **Run**. This performs a full scrape immediately and writes the Riders sheet. It will take ~1–2 minutes (one HTTP request per rider with 500 ms sleeps).

### 7. Install the polling trigger

Select `installTrigger` and click **Run** once. This installs a 30-minute time-based trigger on `checkAndUpdate`. The trigger fires every 30 minutes but only does a full scrape when scores have changed since the last run.

You can verify the trigger was created under **Triggers** (clock icon in the left sidebar).

---

## How change detection works

`checkAndUpdate` concatenates all team scores into a comma-separated string (e.g. `"12340,11820,10950,9870"`) and compares it to the value stored in `PropertiesService` under the key `fingerprint`. If they match, it exits immediately without scraping any rider pages. If they differ, it runs `fullScrape`, updates the fingerprint, and sends the notification email.

This avoids hammering ~30 rider profile pages every 30 minutes throughout the day when no new stage has finished.

---

## DNF handling

If a rider's `finished` flag is false (they did not complete the race), the sheet displays `-` for all stages after their last stage with a non-zero score. The rider's Total still reflects points actually accumulated.
