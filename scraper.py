#!/usr/bin/env python3
"""
Velogames fantasy league scraper.
Outputs data/data.json consumed by index.html (GitHub Pages).
To switch races, update CONFIG only.
"""

import re
import json
import time
import os
from datetime import datetime, timezone

import requests

# ── Tour de France Femmes 2026 ──────────────────────────────
CONFIG = {
    "raceName":   "Tour de France Femmes 2026",
    "leagueUrl":  "https://www.velogames.com/velogame-femmes/2026/leaguescores.php?league=118055015",
    "baseUrl":    "https://www.velogames.com/velogame-femmes/2026/",
    "leagueId":   "118055015",
    "numStages":  10,
    "outputPath": "data/tdf-femmes-2026.json",
    "active":     True,
}
# ── Tour de France 2026 (complete) ──────────────────────────────
#CONFIG = {
#    "raceName":   "Tour de France 2026",
#    "leagueUrl":  "https://www.velogames.com/velogame/2026/leaguescores.php?league=118055015",
#    "baseUrl":    "https://www.velogames.com/velogame/2026/",
#    "leagueId":   "118055015",
#    "numStages":  22,
#    "outputPath": "data/tdf-2026.json",
#    "active":     False,
#}
# ── Tour de Suisse 2026 (complete) ──────────────────────────────
#CONFIG = {
#    "raceName":   "Tour de Suisse 2026",
#    "leagueUrl":  "https://www.velogames.com/suisse/2026/leaguescores.php?league=118055015",
#    "baseUrl":    "https://www.velogames.com/suisse/2026/",
#    "leagueId":   "118055015",
#    "numStages":  6,
#    "outputPath": "data/suisse-2026.json",
#    "active":     False,
#}
# ── Critérium du Dauphiné 2026 (complete) ──────────────────────────────
#CONFIG = {
#    "raceName":   "Critérium du Dauphiné 2026",
#    "leagueUrl":  "https://www.velogames.com/auvergne/2026/leaguescores.php?league=118055015",
#    "baseUrl":    "https://www.velogames.com/auvergne/2026/",
#    "leagueId":   "118055015",
#    "numStages":  9,
#    "outputPath": "data/auvergne-2026.json",
#}

def update_index(config, output_path):
    """Add/update this race in data/index.json (newest first). Sets active flag; deactivates others."""
    index_path = "data/index.json"
    index = []
    if os.path.exists(index_path):
        with open(index_path) as f:
            index = json.load(f)

    active = config.get("active", True)
    if active:
        for r in index:
            if r["file"] != output_path:
                r["active"] = False

    entry = next((r for r in index if r["file"] == output_path), None)
    if entry is None:
        index.insert(0, {"name": config["raceName"], "file": output_path, "active": active})
    else:
        entry["active"] = active

    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)
    print(f"Updated {index_path}")


HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


LAST_FETCH_ERROR = None


def _error_label(e):
    if isinstance(e, requests.exceptions.Timeout):
        return "Timeout"
    if isinstance(e, requests.exceptions.ConnectionError):
        return "Connection error"
    return type(e).__name__


def fetch(url, attempt=1):
    global LAST_FETCH_ERROR
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            print(f"  HTTP {r.status_code} (attempt {attempt}) — {url}")
            if attempt < 3:
                time.sleep(3 * attempt)
                return fetch(url, attempt + 1)
            LAST_FETCH_ERROR = f"HTTP {r.status_code}"
            return None
        LAST_FETCH_ERROR = None
        return r.text
    except Exception as e:
        print(f"  Error (attempt {attempt}) — {url}: {e}")
        if attempt < 3:
            time.sleep(3 * attempt)
            return fetch(url, attempt + 1)
        LAST_FETCH_ERROR = _error_label(e)
        return None


def parse_league(html):
    teams = []
    for li_m in re.finditer(r'<li>([\s\S]*?)</li>', html):
        li = li_m.group(1)
        tid_m   = re.search(r'teamroster\.php\?tid=(\d+)', li)
        name_m  = re.search(r'teamroster\.php\?tid=\d+">(.*?)</a>', li)
        score_m = re.search(r'<b>(\d+)</b>', li)
        if not tid_m or not name_m or not score_m:
            continue
        manager = ''
        for p in re.findall(r'<p class="born">([\s\S]*?)</p>', li):
            text = re.sub(r'<[^>]+>', '', p).strip()
            if text and not re.match(r'^\d+$', text):
                manager = text
                break
        teams.append({
            "tid":     tid_m.group(1),
            "name":    name_m.group(1).strip(),
            "score":   int(score_m.group(1)),
            "manager": manager,
        })
    return teams


def parse_roster(html):
    if not html:
        return []
    riders = []
    for tr_m in re.finditer(r'<tr>([\s\S]*?)</tr>', html):
        tr = tr_m.group(1)
        rider_m = re.search(r'riderprofile\.php\?rider=(\d+)">(.*?)</a>', tr)
        if not rider_m:
            continue
        tds = [re.sub(r'<[^>]+>', '', t.group(1)).strip()
               for t in re.finditer(r'<td[^>]*>([\s\S]*?)</td>', tr)]
        riders.append({
            "id":       rider_m.group(1),
            "name":     rider_m.group(2).strip(),
            "proTeam":  tds[1] if len(tds) > 1 else '',
            "cost":     int(tds[2]) if len(tds) > 2 and tds[2].isdigit() else 0,
            "finished": bool(re.search(r'fa-check', tr)),
        })
    return riders


def parse_riders_page(html):
    """Parses riders.php — the full race startlist (every rider available for
    selection, not just those on a roster in our league).

    Returns {rider_id: {"name", "proTeam", "cost", "score", "category"?}}.
    "score" is the rider's site-wide total points to date, which matches the
    sum of per-stage points we scrape separately via riderprofile.php for
    rostered riders (confirmed against live data) — so it's safe to use
    directly for riders nobody in our league picked, without an extra
    per-rider profile fetch for each of them.

    Velogames sometimes omits the 'Class' column entirely (seen on TdF Femmes 2026
    from around stage 6/7 on — the <th> is HTML-commented out and the <td> is gone
    too), which shifts Cost into the column category used to occupy. Disambiguate
    by cell count rather than assuming a fixed index: 7+ cells means Class is
    present (category at index 3, cost/pct/score follow); 6 cells means it's
    gone (cost/pct/score shift down one, no category data).
    """
    if not html:
        return {}
    result = {}
    for tr_m in re.finditer(r'<tr[^>]*>([\s\S]*?)</tr>', html, re.IGNORECASE):
        tr = tr_m.group(1)
        ids = re.findall(r'riderprofile\.php\?rider=(\d+)', tr)
        if not ids:
            continue
        rid = ids[0]
        tds = [re.sub(r'<[^>]+>', '', t.group(1)).strip()
               for t in re.finditer(r'<td[^>]*>([\s\S]*?)</td>', tr, re.IGNORECASE)]
        # tds: ['' (image), name, pro_team, category, cost, pct, score] when the
        # Class column is present, or ['' (image), name, pro_team, cost, pct, score]
        # when Velogames has dropped it.
        if len(tds) >= 7:
            name, pro_team, category, cost, score = tds[1], tds[2], tds[3], tds[4], tds[6]
        elif len(tds) == 6:
            name, pro_team, category, cost, score = tds[1], tds[2], None, tds[3], tds[5]
        else:
            continue
        rec = {
            "name":    name,
            "proTeam": pro_team,
            "cost":    int(cost) if cost.isdigit() else 0,
            "score":   int(score) if score.isdigit() else 0,
        }
        if category:
            rec["category"] = category
        result[rid] = rec
    return result


def parse_rider_profile(html, num_stages):
    if not html:
        return [0] * num_stages
    stages = [0] * num_stages
    for tr_m in re.finditer(r'<tr>([\s\S]*?)</tr>', html):
        tr = tr_m.group(1)
        final_m = re.search(r'Final Classifications', tr)
        stage_m = re.search(r'Stage\s+(\d+)', tr)
        if not stage_m and not final_m:
            continue
        n = num_stages if final_m else int(stage_m.group(1))
        if n < 1 or n > num_stages:
            continue
        bold_m = re.search(r'<b>\s*(\d+)\s*</b>', tr)
        stages[n - 1] = int(bold_m.group(1)) if bold_m else 0
    return stages


def load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def scores_changed(new_teams, output_path):
    """Return True if any team score differs from the cached output JSON (or no cache exists)."""
    old = load_json(output_path)
    if old is None:
        return True
    cached  = {t["tid"]: t["score"] for t in old.get("teams", [])}
    current = {t["tid"]: t["score"] for t in new_teams}
    return cached != current


def diff_data(old, new):
    """Return list of human-readable change strings between old and new race data."""
    if old is None:
        return [f"Initial scrape — {len(new.get('riders', []))} riders"]

    changes  = []
    old_comp = old.get("stageCompleted", [])
    new_comp = new.get("stageCompleted", [])
    labels   = new.get("stageLabels", [])

    newly_done = [
        labels[i] if i < len(labels) else str(i + 1)
        for i, (o, c) in enumerate(zip(old_comp, new_comp))
        if not o and c
    ]
    if newly_done:
        s = "s" if len(newly_done) > 1 else ""
        changes.append(f"Stage{s} {', '.join(newly_done)} completed")

    old_riders   = {r["id"]: r for r in old.get("riders", [])}
    score_diffs  = []
    dnf_new      = []
    for nr in new.get("riders", []):
        rid = nr["id"]
        or_ = old_riders.get(rid)
        if or_ is None:
            continue
        if not nr["finished"] and or_.get("finished", True):
            dnf_new.append(nr["name"])
        for i, (os, ns) in enumerate(zip(or_.get("stages", []), nr.get("stages", []))):
            if (i < len(old_comp) and old_comp[i]
                    and os is not None and ns is not None and os != ns):
                stage_label = labels[i] if i < len(labels) else str(i + 1)
                score_diffs.append(f"{nr['name']} stage {stage_label}: {os} → {ns}")

    if score_diffs:
        s = "s" if len(score_diffs) != 1 else ""
        changes.append(f"{len(score_diffs)} score{s} updated — " + "; ".join(score_diffs))
    for name in dnf_new:
        changes.append(f"{name} abandoned")

    return changes


def append_log(race_name, changes, ts):
    log_path = "data/log.json"
    entries  = load_json(log_path) or []
    entries.insert(0, {"ts": ts, "race": race_name, "changes": changes})
    entries  = entries[:500]
    with open(log_path, "w") as f:
        json.dump(entries, f, indent=2)
    print(f"Updated {log_path}")


def main():
    if not CONFIG.get("active", True):
        print(f"No active race — set CONFIG['active'] = True in scraper.py to enable scraping.")
        return

    n = CONFIG["numStages"]
    stage_labels = [str(i) for i in range(1, n)] + ["Bonus"]

    print(f"Fetching league: {CONFIG['leagueUrl']}")
    html = fetch(CONFIG["leagueUrl"])
    if not html:
        err = LAST_FETCH_ERROR or "unknown error"
        print(f"Failed to fetch league page ({err})")
        append_log(CONFIG["raceName"], [f"Scrape failed — {err} fetching league page"],
                   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        return

    teams = parse_league(html)
    print(f"Found {len(teams)} teams: {[t['name'] for t in teams]}")
    if not teams:
        append_log(CONFIG["raceName"], ["Scrape failed — 0 teams parsed from league page"],
                   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        return

    if not scores_changed(teams, CONFIG["outputPath"]):
        print("Team scores unchanged — skipping full scrape.")
        return

    old_data = load_json(CONFIG["outputPath"])

    rider_meta   = {}
    team_rosters = {}

    for team in teams:
        time.sleep(2)
        url = CONFIG["baseUrl"] + f"teamroster.php?tid={team['tid']}"
        print(f"  Roster: {team['name']}")
        html = fetch(url)
        riders = parse_roster(html)
        if not riders:
            err = LAST_FETCH_ERROR if html is None else "0 riders parsed (roster may be hidden pre-race)"
            print(f"  WARNING: {err} for {team['name']} — aborting")
            append_log(CONFIG["raceName"], [f"Scrape aborted — {err} fetching roster for {team['name']}"],
                       datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
            return
        team_rosters[team["tid"]] = [r["id"] for r in riders]
        for r in riders:
            rider_meta[r["id"]] = {
                "name":     r["name"],
                "proTeam":  r["proTeam"],
                "cost":     r["cost"],
                "finished": r["finished"],
            }

    time.sleep(2)
    print("Fetching full startlist (riders.php)...")
    riders_html = fetch(CONFIG["baseUrl"] + "riders.php")
    riders_full = parse_riders_page(riders_html)
    n_cat = sum(1 for r in riders_full.values() if "category" in r)
    print(f"  Got {len(riders_full)} riders, categories for {n_cat}")
    for rid in rider_meta:
        if rid in riders_full and "category" in riders_full[rid]:
            rider_meta[rid]["category"] = riders_full[rid]["category"]

    old_stages_by_id = {}
    if old_data:
        for r in old_data.get("riders", []):
            old_stages_by_id[r["id"]] = [(v or 0) for v in r.get("stages", [])]

    failed_profiles = []
    rider_stages = {}
    for rid, meta in rider_meta.items():
        time.sleep(1)
        url = CONFIG["baseUrl"] + f"riderprofile.php?rider={rid}"
        print(f"  Profile: {meta['name']}")
        html = fetch(url)
        if html is None:
            cached = old_stages_by_id.get(rid)
            if cached:
                print(f"  WARNING: profile fetch failed for {meta['name']} — keeping cached stages")
                rider_stages[rid] = cached
            else:
                rider_stages[rid] = [0] * n
            failed_profiles.append(meta["name"])
        else:
            rider_stages[rid] = parse_rider_profile(html, n)

    stage_completed = [False] * n
    for stages in rider_stages.values():
        for i, pts in enumerate(stages):
            if pts > 0:
                stage_completed[i] = True

    rider_to_tids = {}
    for team in teams:
        for rid in team_rosters.get(team["tid"], []):
            rider_to_tids.setdefault(rid, []).append(team["tid"])

    all_rider_ids = sorted(rider_meta.keys(), key=lambda rid: rider_meta[rid]["name"])
    riders_out = []
    for rid in all_rider_ids:
        meta   = rider_meta[rid]
        stages = rider_stages.get(rid, [0] * n)
        total  = sum(stages)
        cost   = meta["cost"]
        eff    = round(total / cost, 1) if cost else 0

        last_stage = n
        if not meta["finished"]:
            last_stage = 0
            for i in range(n - 1):
                if stages[i] > 0:
                    last_stage = i + 1

        stage_vals = []
        for i, pts in enumerate(stages):
            if not stage_completed[i]:
                stage_vals.append(None)
            elif i < n - 1 and (i + 1) > last_stage:
                stage_vals.append(None)
            else:
                stage_vals.append(pts)

        rider_out = {
            "id":         rid,
            "name":       meta["name"],
            "proTeam":    meta["proTeam"],
            "cost":       cost,
            "finished":   meta["finished"],
            "teamIds":    rider_to_tids.get(rid, []),
            "stages":     stage_vals,
            "total":      total,
            "efficiency": eff,
        }
        if "category" in meta:
            rider_out["category"] = meta["category"]
        riders_out.append(rider_out)

    # "Other interesting riders" — top 10 by efficiency among riders on the
    # full startlist (riders.php) that nobody in our league picked. Ranking
    # itself needs no extra requests (riders.php already gives cost + total
    # score for every rider), but once we know which 10 they are, we fetch
    # their riderprofile.php too so the table can show real per-stage
    # heatmap cells instead of a total-only placeholder.
    other_candidates = []
    for rid, rec in riders_full.items():
        if rid in rider_meta:
            continue
        cost = rec.get("cost", 0)
        if cost <= 0:
            continue
        total = rec.get("score", 0)
        entry = {
            "id":         rid,
            "name":       rec["name"],
            "proTeam":    rec["proTeam"],
            "cost":       cost,
            "finished":   True,
            "teamIds":    [],
            "stages":     [None] * n,
            "total":      total,
            "efficiency": round(total / cost, 1),
        }
        if "category" in rec:
            entry["category"] = rec["category"]
        other_candidates.append(entry)
    other_candidates.sort(key=lambda r: -r["efficiency"])
    other_riders_out = other_candidates[:10]

    # Fetch real per-stage scores for just these top 10, so their rows get
    # the same stage-by-stage heatmap as picked riders instead of the
    # placeholder [None] * n set above. There's no roster page for an
    # unpicked rider (that's the whole point — nobody rostered them), so
    # unlike picked riders there's no fa-check icon to read DNF status
    # from; "finished" stays True (unknown) and stages simply score 0
    # rather than trimming to null after a would-be abandonment.
    for entry in other_riders_out:
        time.sleep(1)
        url = CONFIG["baseUrl"] + f"riderprofile.php?rider={entry['id']}"
        print(f"  Profile (other): {entry['name']}")
        html = fetch(url)
        if html is None:
            print(f"  WARNING: profile fetch failed for {entry['name']} — keeping total only")
            failed_profiles.append(entry["name"])
            continue
        stages = parse_rider_profile(html, n)
        entry["stages"] = [
            stages[i] if stage_completed[i] else None
            for i in range(n)
        ]

    teams_sorted = sorted(teams, key=lambda t: -t["score"])
    for team in teams_sorted:
        rids = team_rosters.get(team["tid"], [])
        sums = [
            sum((rider_stages.get(rid, [0] * n)[i] or 0) for rid in rids)
            for i in range(n)
        ]
        cumul, running = [], 0
        for s in sums:
            running += s
            cumul.append(running)
        team["stageSums"]  = sums
        team["stageCumul"] = cumul

    output = {
        "raceName":       CONFIG["raceName"],
        "leagueId":       CONFIG["leagueId"],
        "leagueUrl":      CONFIG["leagueUrl"],
        "baseUrl":        CONFIG["baseUrl"],
        "numStages":      n,
        "stageLabels":    stage_labels,
        "stageCompleted": stage_completed,
        "teams":          teams_sorted,
        "riders":         riders_out,
        "otherRiders":    other_riders_out,
    }

    changes = diff_data(old_data, output)
    if failed_profiles:
        changes.append(
            f"{len(failed_profiles)} rider profile(s) failed to fetch (kept cached stages, "
            "or total-only for unrostered riders) — " + ", ".join(failed_profiles)
        )
    if old_data is not None and not changes:
        print("Full scrape matched cached data — no write needed.")
        return

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    output["lastUpdated"] = ts

    os.makedirs(os.path.dirname(CONFIG["outputPath"]) or ".", exist_ok=True)
    with open(CONFIG["outputPath"], "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote {CONFIG['outputPath']}")
    append_log(CONFIG["raceName"], changes, ts)
    update_index(CONFIG, CONFIG["outputPath"])


if __name__ == "__main__":
    main()
