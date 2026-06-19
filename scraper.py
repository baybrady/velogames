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

# ── Critérium du Dauphiné 2026 ──────────────────────────────
CONFIG = {
    "raceName":   "Critérium du Dauphiné 2026",
    "leagueUrl":  "https://www.velogames.com/auvergne/2026/leaguescores.php?league=118055015",
    "baseUrl":    "https://www.velogames.com/auvergne/2026/",
    "leagueId":   "118055015",
    "numStages":  9,
    "outputPath": "data/auvergne-2026.json",
}

def update_index(config, output_path):
    """Add this race to data/index.json (newest first) if not already present."""
    index_path = "data/index.json"
    index = []
    if os.path.exists(index_path):
        with open(index_path) as f:
            index = json.load(f)
    if not any(r["file"] == output_path for r in index):
        index.insert(0, {"name": config["raceName"], "file": output_path})
        with open(index_path, "w") as f:
            json.dump(index, f, indent=2)
        print(f"Updated {index_path}")


# ── Tour de France 2026 (swap in when ready) ────────────────
# CONFIG = {
#     "raceName":   "Tour de France 2026",
#     "leagueUrl":  "https://www.velogames.com/velogame/2026/leaguescores.php?league=118055015",
#     "baseUrl":    "https://www.velogames.com/velogame/2026/",
#     "leagueId":   "118055015",
#     "numStages":  22,
#     "outputPath": "data/data.json",
# }

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch(url, attempt=1):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            print(f"  HTTP {r.status_code} (attempt {attempt}) — {url}")
            if attempt < 3:
                time.sleep(3 * attempt)
                return fetch(url, attempt + 1)
            return None
        return r.text
    except Exception as e:
        print(f"  Error (attempt {attempt}) — {url}: {e}")
        if attempt < 3:
            time.sleep(3 * attempt)
            return fetch(url, attempt + 1)
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


def main():
    n = CONFIG["numStages"]
    stage_labels = [str(i) for i in range(1, n)] + ["Bonus"]

    print(f"Fetching league: {CONFIG['leagueUrl']}")
    html = fetch(CONFIG["leagueUrl"])
    if not html:
        print("Failed to fetch league page")
        return

    teams = parse_league(html)
    print(f"Found {len(teams)} teams: {[t['name'] for t in teams]}")
    if not teams:
        return

    rider_meta   = {}
    team_rosters = {}

    for team in teams:
        time.sleep(1)
        url = CONFIG["baseUrl"] + f"teamroster.php?tid={team['tid']}"
        print(f"  Roster: {team['name']}")
        html = fetch(url)
        riders = parse_roster(html)
        if not riders:
            print(f"  WARNING: 0 riders for {team['name']} — aborting")
            return
        team_rosters[team["tid"]] = [r["id"] for r in riders]
        for r in riders:
            rider_meta[r["id"]] = {
                "name":     r["name"],
                "proTeam":  r["proTeam"],
                "cost":     r["cost"],
                "finished": r["finished"],
            }

    rider_stages = {}
    for rid, meta in rider_meta.items():
        time.sleep(0.5)
        url = CONFIG["baseUrl"] + f"riderprofile.php?rider={rid}"
        print(f"  Profile: {meta['name']}")
        html = fetch(url)
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

        riders_out.append({
            "id":         rid,
            "name":       meta["name"],
            "proTeam":    meta["proTeam"],
            "cost":       cost,
            "finished":   meta["finished"],
            "teamIds":    rider_to_tids.get(rid, []),
            "stages":     stage_vals,
            "total":      total,
            "efficiency": eff,
        })

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
        "lastUpdated":    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "teams":          teams_sorted,
        "riders":         riders_out,
    }

    os.makedirs(os.path.dirname(CONFIG["outputPath"]) or ".", exist_ok=True)
    with open(CONFIG["outputPath"], "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote {CONFIG['outputPath']}")
    update_index(CONFIG, CONFIG["outputPath"])


if __name__ == "__main__":
    main()
