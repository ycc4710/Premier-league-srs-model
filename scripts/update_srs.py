"""
EPL SRS Updater
Fetches all played games, recalculates SRS, and saves to srs_data.json.
"""
import json
import os
from datetime import datetime

try:
    from calculate_srs import calculate_srs
    from fetch_data import fetch_games
except ImportError:
    from scripts.calculate_srs import calculate_srs
    from scripts.fetch_data import fetch_games

from scripts.config import (
    ABBR_TO_TEAM_NAME,
    TEAM_LOGO_IDS,
    TEAM_TO_DIVISION,
)

base_dir = os.path.dirname(__file__)
srs_out_path = os.path.join(base_dir, '..', 'site', 'data', 'srs_data.json')

# ── 1. Fetch all played games ──
games = fetch_games()

# ── 2. Build game_results tuples ──
game_results = []
teams = set()
wins = {}
draws = {}
losses = {}

for game in games:
    home = game.get("home_team") or game.get("home")
    away = game.get("away_team") or game.get("away")
    home_pts = game.get("home_pts")
    away_pts = game.get("away_pts")

    if not home or not away or home_pts is None or away_pts is None:
        continue

    margin = home_pts - away_pts
    game_results.append((home, away, margin))
    teams.update([home, away])

    # Track W/D/L
    if home_pts > away_pts:
        wins[home] = wins.get(home, 0) + 1
        losses[away] = losses.get(away, 0) + 1
    elif home_pts == away_pts:
        draws[home] = draws.get(home, 0) + 1
        draws[away] = draws.get(away, 0) + 1
    else:
        wins[away] = wins.get(away, 0) + 1
        losses[home] = losses.get(home, 0) + 1

teams = sorted(teams)

# ── 3. Calculate SRS ──
srs_dict = calculate_srs(game_results, teams)

# ── 4. Build output ──
out_teams = []
for abbr, stats in srs_dict.items():
    w = wins.get(abbr, 0)
    d = draws.get(abbr, 0)
    l = losses.get(abbr, 0)
    total = w + d + l
    points = w * 3 + d

    team_entry = {
        "abbreviation": abbr,
        "name": ABBR_TO_TEAM_NAME.get(abbr, abbr),
        "team_id": TEAM_LOGO_IDS.get(abbr, ""),
        "conference": "EPL",
        "division": TEAM_TO_DIVISION.get(abbr, ""),
        "wins": w,
        "draws": d,
        "losses": l,
        "points": points,
        "win_pct": round(w / total, 3) if total > 0 else 0.0,
        "games_played": total,
        "srs": stats.get("srs", 0),
        "mov": stats.get("mov", 0),
        "sos": stats.get("sos", 0),
    }
    out_teams.append(team_entry)

# Standings rank by points (then wins as tiebreaker)
out_teams.sort(key=lambda t: (t["points"], t["wins"]), reverse=True)
for idx, team in enumerate(out_teams, 1):
    team["standings_rank"] = idx

# SRS rank
out_teams_srs = sorted(out_teams, key=lambda t: t["srs"], reverse=True)
for idx, team in enumerate(out_teams_srs, 1):
    team["srs_rank"] = idx

out = {
    "metadata": {
        "season": "2024-25",
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "total_games": len(game_results),
    },
    "teams": out_teams,
}

os.makedirs(os.path.dirname(srs_out_path), exist_ok=True)
with open(srs_out_path, "w") as f:
    json.dump(out, f, indent=2)

print(f"Updated SRS for {len(out_teams)} EPL teams from {len(game_results)} matches.")