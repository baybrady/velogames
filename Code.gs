// ═══════════════════════════════════════════════════════════
// Code.gs  —  Velogames fantasy league tracker
// ═══════════════════════════════════════════════════════════
// Single-file version. To use for a new race, update CONFIG only.

// ── Critérium du Dauphiné 2026 ──────────────────────────────
const CONFIG = {
  raceName:     'Critérium du Dauphiné 2026',
  leagueUrl:    'https://www.velogames.com/auvergne/2026/leaguescores.php?league=118055015',  // league 118055015 = Seixas fan club
  baseUrl:      'https://www.velogames.com/auvergne/2026/',
  numStages:    9,   // 8 race stages + Final Classifications
  pollStartUtc: 10,  // only scrape between 10:00 and 23:00 UTC
  pollEndUtc:   23,
  notifyEmail:  'mark@baybrady.org',  // comma-separated string to notify multiple people
};

// ── Giro d'Italia 2026 (complete) ───────────────────────────
// const CONFIG = {
//   raceName:     'Giro d\'Italia 2026',
//   leagueUrl:    'https://www.velogames.com/italy/2026/leaguescores.php?league=118055015',
//   baseUrl:      'https://www.velogames.com/italy/2026/',
//   numStages:    22,  // 21 race stages + Final Classifications
//   pollStartUtc: 10,
//   pollEndUtc:   23,
//   notifyEmail:  'mark@baybrady.org',
// };

// ── Tour de France 2026 (swap in when ready) ────────────────
// const CONFIG = {
//   raceName:     'Tour de France 2026',
//   leagueUrl:    'https://www.velogames.com/velogame/2026/leaguescores.php?league=XXXXXXX',
//   baseUrl:      'https://www.velogames.com/velogame/2026/',
//   numStages:    22,  // 21 race stages + Final Classifications
//   pollStartUtc: 10,
//   pollEndUtc:   23,
//   notifyEmail:  'mark@baybrady.org',
// };

const FETCH_OPTS = {
  headers: {
    'User-Agent':      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15',
    'Accept':          'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
  },
  muteHttpExceptions: true,
};

// ═══════════════════════════════════════════════════════════
// Orchestration
// ═══════════════════════════════════════════════════════════

// ─── Polling entry point (called by time-based trigger) ────
function checkAndUpdate() {
  const hour = new Date().getUTCHours();
  if (hour < CONFIG.pollStartUtc || hour >= CONFIG.pollEndUtc) return;

  const html = fetchUrl(CONFIG.leagueUrl);
  if (!html) return;

  const teams = parseLeague(html);
  if (!teams.length) return;

  const fingerprint = teams.map(t => t.score).join(',');
  const props = PropertiesService.getScriptProperties();
  if (props.getProperty('fingerprint') === fingerprint) return;

  Logger.log('New data detected — scores: ' + fingerprint);
  fullScrape(teams);
  props.setProperty('fingerprint', fingerprint);
  notifyLeague(teams);
}

// ─── Full scrape (all rosters + rider profiles) ────────────
function fullScrape(teams) {
  const riderMeta   = {};  // riderId -> { name, cost, proTeam }
  const teamRosters = {};  // tid     -> [riderId, ...]

  for (const team of teams) {
    Utilities.sleep(1000);
    const html = fetchUrl(CONFIG.baseUrl + 'teamroster.php?tid=' + team.tid);
    const riders = parseRoster(html);
    if (riders.length === 0) {
      Logger.log('WARNING: 0 riders for ' + team.name + ' — aborting scrape to protect sheet data');
      return;
    }
    teamRosters[team.tid] = riders.map(r => r.id);
    for (const r of riders) {
      riderMeta[r.id] = { name: r.name, cost: r.cost, proTeam: r.proTeam, finished: r.finished };
    }
  }

  const riderStages = {};  // riderId -> [numStages stage point totals]
  for (const riderId of Object.keys(riderMeta)) {
    Utilities.sleep(500);
    const html = fetchUrl(CONFIG.baseUrl + 'riderprofile.php?rider=' + riderId);
    riderStages[riderId] = parseRiderProfile(html);
  }

  // Determine which stages have been completed (any rider scored > 0)
  const stageCompleted = new Array(CONFIG.numStages).fill(false);
  for (const stages of Object.values(riderStages)) {
    for (let i = 0; i < CONFIG.numStages; i++) {
      if (stages[i] > 0) stageCompleted[i] = true;
    }
  }

  writeAllData(teams, teamRosters, riderMeta, riderStages, stageCompleted);
}

function fetchUrl(url, attempt) {
  attempt = attempt || 1;
  try {
    const resp = UrlFetchApp.fetch(url, FETCH_OPTS);
    if (resp.getResponseCode() !== 200) {
      Logger.log('HTTP ' + resp.getResponseCode() + ' (attempt ' + attempt + ') — ' + url);
      if (attempt < 3) { Utilities.sleep(3000 * attempt); return fetchUrl(url, attempt + 1); }
      return null;
    }
    return resp.getContentText();
  } catch (e) {
    Logger.log('Fetch error (attempt ' + attempt + ') — ' + url + ': ' + e);
    if (attempt < 3) { Utilities.sleep(3000 * attempt); return fetchUrl(url, attempt + 1); }
    return null;
  }
}

function notifyLeague(teams) {
  const sorted = [...teams].sort((a, b) => b.score - a.score);
  const body = sorted.map((t, i) =>
    (i + 1) + '. ' + t.name + ' (' + t.manager + '): ' + t.score + ' pts'
  ).join('\n');
  GmailApp.sendEmail(
    CONFIG.notifyEmail,
    'Velogames ' + CONFIG.raceName + ' — new stage results!',
    'Current standings:\n\n' + body
  );
}

// ─── Manual triggers ────────────────────────────────────────

// Run this once to manually force a full data refresh
function forceUpdate() {
  const html = fetchUrl(CONFIG.leagueUrl);
  if (!html) { Logger.log('Failed to fetch league page'); return; }
  const teams = parseLeague(html);
  Logger.log('Teams found: ' + JSON.stringify(teams));
  fullScrape(teams);
}

// Run this once to install the 30-minute polling trigger
function installTrigger() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('checkAndUpdate')
    .timeBased()
    .everyMinutes(30)
    .create();
  Logger.log('Trigger installed: checkAndUpdate every 30 minutes');
}

// ═══════════════════════════════════════════════════════════
// Parsers
// ═══════════════════════════════════════════════════════════

// Returns: [{ tid, name, manager, score }, ...]
function parseLeague(html) {
  const teams = [];
  const liRe = /<li>([\s\S]*?)<\/li>/g;
  let m;
  while ((m = liRe.exec(html)) !== null) {
    const li = m[1];
    const tidMatch   = li.match(/teamroster\.php\?tid=(\d+)/);
    const nameMatch  = li.match(/teamroster\.php\?tid=\d+">(.*?)<\/a>/);
    const scoreMatch = li.match(/<b>(\d+)<\/b>/);
    if (!tidMatch || !nameMatch || !scoreMatch) continue;
    // Manager is the <p class="born"> that does NOT contain a <b> tag
    const pTags = [...li.matchAll(/<p class="born">([\s\S]*?)<\/p>/g)];
    const manager = pTags
      .map(p => p[1].replace(/<[^>]+>/g, '').trim())
      .find(t => t && !/^\d+$/.test(t)) || '';
    teams.push({
      tid:     tidMatch[1],
      name:    nameMatch[1].trim(),
      score:   parseInt(scoreMatch[1]),
      manager: manager,
    });
  }
  return teams;
}

// Returns: [{ id, name, proTeam, cost, finished }, ...]
function parseRoster(html) {
  if (!html) return [];
  const riders = [];
  const trRe = /<tr>([\s\S]*?)<\/tr>/g;
  let m;
  while ((m = trRe.exec(html)) !== null) {
    const tr = m[1];
    const riderMatch = tr.match(/riderprofile\.php\?rider=(\d+)">(.*?)<\/a>/);
    if (!riderMatch) continue;
    const tds = [...tr.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)]
      .map(t => t[1].replace(/<[^>]+>/g, '').trim());
    // td[0]=name, td[1]=pro team, td[2]=cost, td[3]=fa-check (finished) or fa-times (DNF)
    riders.push({
      id:       riderMatch[1],
      name:     riderMatch[2].trim(),
      proTeam:  tds[1] || '',
      cost:     parseInt(tds[2]) || 0,
      finished: /fa-check/.test(tr),
    });
  }
  return riders;
}

// Returns: Array(numStages) of per-stage total points (index 0 = Stage 1)
function parseRiderProfile(html) {
  if (!html) return new Array(CONFIG.numStages).fill(0);
  const stages = new Array(CONFIG.numStages).fill(0);
  const trRe = /<tr>([\s\S]*?)<\/tr>/g;
  let m;
  while ((m = trRe.exec(html)) !== null) {
    const tr = m[1];
    const finalMatch = tr.match(/Final Classifications/);
    const stageMatch = tr.match(/Stage\s+(\d+)/);
    if (!stageMatch && !finalMatch) continue;
    const n = finalMatch ? CONFIG.numStages : parseInt(stageMatch[1]);
    if (n < 1 || n > CONFIG.numStages) continue;
    const boldMatch = tr.match(/<b>\s*(\d+)\s*<\/b>/);
    stages[n - 1] = boldMatch ? parseInt(boldMatch[1]) : 0;
  }
  return stages;
}

// ═══════════════════════════════════════════════════════════
// Sheet writing
// ═══════════════════════════════════════════════════════════

function writeAllData(teams, teamRosters, riderMeta, riderStages, stageCompleted) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sorted = [...teams].sort((a, b) => b.score - a.score);
  writeRiders(ss, sorted, teamRosters, riderMeta, riderStages, stageCompleted);
  const sheet = ss.getSheetByName('Riders');
  if (sheet) {
    sheet.getRange('A1').setNote(
      (() => {
        const fmt = tz => new Date().toLocaleString('en-US', {
          timeZone: tz, timeZoneName: 'short', month: 'numeric', day: 'numeric',
          hour: 'numeric', minute: '2-digit'
        });
        return 'Last updated: ' + fmt('America/New_York') + ' | ' + fmt('America/Los_Angeles') + ' | ' + fmt('Australia/Adelaide');
      })()
    );
  }
}

// ─── Riders sheet ─────────────────────────────────────────
// Sections (all in one sheet, stage columns aligned throughout):
//   1. Rider rows — one row per unique rider, sorted by first name
//   2. Daily section — per-team points scored each stage
//   3. Cumulative section — per-team running total each stage
//   4. Column chart (daily) + Line chart (cumulative)
function writeRiders(ss, teams, teamRosters, riderMeta, riderStages, stageCompleted) {
  const sheet = getOrCreate(ss, 'Riders');
  sheet.clearContents();
  const chartsExist = sheet.getCharts().length > 0;

  teams = [...teams].sort((a, b) => a.name.localeCompare(b.name));
  const numTeams = teams.length;
  const n        = CONFIG.numStages;
  const stageHdrs = range1(n).map(i => i === n ? 'Bonus' : '' + i);

  // Column positions (1-indexed):
  // [1..numTeams] team membership | [riderCol] Rider | [proTeamCol] Pro Team |
  // [costCol] Cost | [stageStart..stageStart+n-1] stages | [totalCol] Total | [effCol] Efficiency
  const riderCol   = numTeams + 1;
  const proTeamCol = numTeams + 2;
  const costCol    = numTeams + 3;
  const stageStart = numTeams + 4;
  const totalCol   = stageStart + n;
  const effCol     = totalCol + 1;
  const numCols    = effCol;

  // ─── Header row ─────────────────────────────────────────
  sheet.appendRow([...teams.map(t => t.name), 'Rider', 'Pro Team', 'Cost', ...stageHdrs, 'Total', 'Efficiency']);

  // ─── Rider rows ─────────────────────────────────────────
  const riderTeams = {};
  for (const team of teams) {
    for (const rid of (teamRosters[team.tid] || [])) {
      riderTeams[rid] = riderTeams[rid] || [];
      riderTeams[rid].push(team.name);
    }
  }

  const allRiderIds = Object.keys(riderMeta)
    .sort((a, b) => (riderMeta[a].name || '').localeCompare(riderMeta[b].name || ''));

  let currentRow = 2;
  for (const rid of allRiderIds) {
    const meta   = riderMeta[rid] || {};
    const stages = riderStages[rid] || new Array(n).fill(0);
    const total  = stages.reduce((s, v) => s + v, 0);
    const cost   = meta.cost || 0;
    const eff    = cost > 0 ? Math.round(total / cost * 10) / 10 : '';
    const memb   = teams.map(t => (riderTeams[rid] || []).includes(t.name) ? 1 : '');

    // DNF: dash all stages after their last scored stage
    let riderLastStage = n;
    if (!meta.finished) {
      riderLastStage = 0;
      for (let i = 0; i < n - 1; i++) {
        if (stages[i] > 0) riderLastStage = i + 1;
      }
    }

    const stageVals = stages.map((pts, i) => {
      if (!stageCompleted[i]) return '-';
      if (i < n - 1 && (i + 1) > riderLastStage) return '-';
      return pts;
    });

    sheet.appendRow([...memb, meta.name || rid, meta.proTeam || '', cost, ...stageVals, total, eff]);
    currentRow++;
  }

  // ─── Per-team stage sums (numeric, for summary sections) ─
  const teamStageSums = {};
  for (const team of teams) {
    const riderIds = teamRosters[team.tid] || [];
    teamStageSums[team.name] = Array.from({length: n}, (_, i) =>
      riderIds.reduce((sum, rid) => sum + ((riderStages[rid] || [])[i] || 0), 0)
    );
  }

  // ─── Summary section writer ──────────────────────────────
  // Team name is placed in costCol (adjacent to stageStart) so the chart
  // range [costCol .. stageStart+n-1] is contiguous: name | s1 | s2 | ... | sN
  function writeSection(startRow, label, valuesFn) {
    const hdr = new Array(numCols).fill('');
    hdr[costCol - 1] = label;
    stageHdrs.forEach((h, i) => { hdr[stageStart - 1 + i] = h; });
    sheet.getRange(startRow, 1, 1, numCols).setValues([hdr]);

    let r = startRow + 1;
    for (const team of teams) {
      const vals = valuesFn(team.name);
      const row  = new Array(numCols).fill('');
      row[costCol - 1] = team.name;
      vals.forEach((v, i) => { row[stageStart - 1 + i] = v; });
      sheet.getRange(r, 1, 1, numCols).setValues([row]);
      r++;
    }
    return { hdrRow: startRow, dataStart: startRow + 1, dataEnd: r - 1 };
  }

  currentRow += 2;
  const daily = writeSection(currentRow, 'Daily', name => teamStageSums[name]);
  currentRow  = daily.dataEnd + 3;

  const cumul = writeSection(currentRow, 'Cumulative', name => {
    let running = 0;
    return teamStageSums[name].map(v => (running += v));
  });
  currentRow = cumul.dataEnd + 3;

  // ─── Charts ─────────────────────────────────────────────
  // Range: [hdr row + team rows] × [costCol (name) + n stage cols]
  // setTransposeRowsAndColumns(true) → rows (teams) become series, cols (stages) become x-axis
  if (!chartsExist) {
  const dailyNameRange  = sheet.getRange(daily.dataStart, costCol, numTeams, 1);
  const dailyStageRange = sheet.getRange(daily.dataStart, stageStart,  numTeams, n);
  sheet.insertChart(sheet.newChart()
    .setChartType(Charts.ChartType.COLUMN)
    .addRange(dailyNameRange)
    .addRange(dailyStageRange)
    .setTransposeRowsAndColumns(true)
    .setOption('title', 'Daily Stage Points')
    .setOption('hAxis', {title: 'Stage'})
    .setOption('vAxis', {title: 'Points'})
    .setOption('width', 900)
    .setOption('height', 350)
    .setPosition(currentRow, 1, 0, 0)
    .build());

  const cumulNameRange  = sheet.getRange(cumul.dataStart, costCol, numTeams, 1);
  const cumulStageRange = sheet.getRange(cumul.dataStart, stageStart,  numTeams, n);
  sheet.insertChart(sheet.newChart()
    .setChartType(Charts.ChartType.LINE)
    .addRange(cumulNameRange)
    .addRange(cumulStageRange)
    .setTransposeRowsAndColumns(true)
    .setOption('title', 'Cumulative Points')
    .setOption('hAxis', {title: 'Stage'})
    .setOption('vAxis', {title: 'Points'})
    .setOption('width', 900)
    .setOption('height', 350)
    .setPosition(currentRow + 20, 1, 0, 0)
    .build());
  } // end chartsExist check
}

// ─── Helpers ──────────────────────────────────────────────

function getOrCreate(ss, name) {
  return ss.getSheetByName(name) || ss.insertSheet(name);
}

function range1(n) {
  return Array.from({ length: n }, (_, i) => i + 1);
}
