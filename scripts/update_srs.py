"""
NBA SRS Updater
Parses all games from weekly_schedule.json, recalculates SRS, and saves to srs_data.json.
"""
import json
import os
from datetime import datetime
from calculate_srs import calculate_srs


# Load all games for the season
base_dir = os.path.dirname(__file__)
season_path = os.path.join(base_dir, '..', 'site', 'data', 'srs_data.json')
games_path = os.path.join(base_dir, '..', 'site', 'data', 'simulation_results.json')

# Prefer simulation_results.json if it exists, else fallback to srs_data.json (for games)
if os.path.exists(games_path):
    with open(games_path) as f:
        games_data = json.load(f)
    games = games_data if isinstance(games_data, list) else games_data.get('games', [])
else:
    # fallback: try to load from srs_data.json if it contains games
    with open(season_path) as f:
        srs_data = json.load(f)
    games = srs_data.get('games', []) if isinstance(srs_data, dict) else []
    if not games:
        # fallback: try weekly_schedule.json (legacy)
        schedule_path = os.path.join(base_dir, '..', 'site', 'data', 'weekly_schedule.json')
        with open(schedule_path) as f:
            games = json.load(f)


# Build game_results: (home_abbr, away_abbr, margin) for all games played (with scores)
game_results = []
teams = set()
for game in games:
    # Accept both old and new keys
    home_abbr = game.get("home_abbr") or game.get("home_team") or game.get("home")
    away_abbr = game.get("away_abbr") or game.get("away_team") or game.get("away")
    home_pts = game.get("home_pts") if "home_pts" in game else game.get("home_score")
    away_pts = game.get("away_pts") if "away_pts" in game else game.get("away_score")
    if home_abbr and away_abbr and home_pts is not None and away_pts is not None:
        margin = home_pts - away_pts
        game_results.append((home_abbr, away_abbr, margin))
        teams.add(home_abbr)
        teams.add(away_abbr)

teams = sorted(list(teams))

# Calculate SRS
srs_dict = calculate_srs(game_results, teams)

# Save to srs_data.json
metadata = {
    "season": "2025-26",
    "last_updated": datetime.utcnow().isoformat() + "Z",
    "total_games": len(game_results)
}
out = {
    "metadata": metadata,
    "teams": []
}
for abbr, stats in srs_dict.items():
    team_entry = {"abbreviation": abbr}
    team_entry.update(stats)
    # Add conference info
    east = ["Boston Celtics", "Brooklyn Nets", "Charlotte Hornets", "Chicago Bulls", "Cleveland Cavaliers", "Detroit Pistons", "Indiana Pacers", "Miami Heat", "Milwaukee Bucks", "New York Knicks", "Orlando Magic", "Philadelphia 76ers", "Toronto Raptors", "Washington Wizards", "Atlanta Hawks"]
    west = ["Dallas Mavericks", "Denver Nuggets", "Golden State Warriors", "Houston Rockets", "Los Angeles Clippers", "Los Angeles Lakers", "Memphis Grizzlies", "Minnesota Timberwolves", "New Orleans Pelicans", "Oklahoma City Thunder", "Phoenix Suns", "Portland Trail Blazers", "Sacramento Kings", "San Antonio Spurs", "Utah Jazz"]
    divisions = {
        "Atlantic": ["Boston Celtics", "Brooklyn Nets", "New York Knicks", "Philadelphia 76ers", "Toronto Raptors"],
        "Central": ["Chicago Bulls", "Cleveland Cavaliers", "Detroit Pistons", "Indiana Pacers", "Milwaukee Bucks"],
        "Southeast": ["Atlanta Hawks", "Charlotte Hornets", "Miami Heat", "Orlando Magic", "Washington Wizards"],
        "Northwest": ["Denver Nuggets", "Minnesota Timberwolves", "Oklahoma City Thunder", "Portland Trail Blazers", "Utah Jazz"],
        "Pacific": ["Golden State Warriors", "Los Angeles Clippers", "Los Angeles Lakers", "Phoenix Suns", "Sacramento Kings"],
        "Southwest": ["Dallas Mavericks", "Houston Rockets", "Memphis Grizzlies", "New Orleans Pelicans", "San Antonio Spurs"]
    }
    # Add conference
    if abbr in east:
        team_entry["conference"] = "East"
    elif abbr in west:
        team_entry["conference"] = "West"
    # Add division
    for div, teams_in_div in divisions.items():
        if abbr in teams_in_div:
            team_entry["division"] = div
            break
    # Add team_id (NBA.com numeric ID)
    nba_ids = {
        "Atlanta Hawks": "1610612737", "Boston Celtics": "1610612738", "Brooklyn Nets": "1610612751", "Charlotte Hornets": "1610612766", "Chicago Bulls": "1610612741", "Cleveland Cavaliers": "1610612739", "Dallas Mavericks": "1610612742", "Denver Nuggets": "1610612743", "Detroit Pistons": "1610612765", "Golden State Warriors": "1610612744", "Houston Rockets": "1610612745", "Indiana Pacers": "1610612754", "Los Angeles Clippers": "1610612746", "Los Angeles Lakers": "1610612747", "Memphis Grizzlies": "1610612763", "Miami Heat": "1610612748", "Milwaukee Bucks": "1610612749", "Minnesota Timberwolves": "1610612750", "New Orleans Pelicans": "1610612740", "New York Knicks": "1610612752", "Oklahoma City Thunder": "1610612760", "Orlando Magic": "1610612753", "Philadelphia 76ers": "1610612755", "Phoenix Suns": "1610612756", "Portland Trail Blazers": "1610612757", "Sacramento Kings": "1610612758", "San Antonio Spurs": "1610612759", "Toronto Raptors": "1610612761", "Utah Jazz": "1610612762", "Washington Wizards": "1610612764"
    }
    team_entry["team_id"] = nba_ids.get(abbr, "")
    # Calculate wins, losses, win_pct
    team_entry["wins"] = stats.get("wins", 0)
    team_entry["losses"] = stats.get("losses", 0)
    total_games = team_entry["wins"] + team_entry["losses"]
    team_entry["win_pct"] = (team_entry["wins"] / total_games) if total_games > 0 else 0
    team_entry["games_played"] = total_games
    out["teams"].append(team_entry)

# Add standings_rank (by win_pct)
teams_sorted = sorted(out["teams"], key=lambda t: t["win_pct"], reverse=True)
for idx, team in enumerate(teams_sorted, 1):
    team["standings_rank"] = idx

with open(srs_out_path, "w") as f:
    json.dump(out, f, indent=2)
