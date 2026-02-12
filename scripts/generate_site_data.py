"""Generate site data JSON by fetching games, calculating SRS, and merging standings."""

import json
import logging
import os
import sys
from datetime import datetime, timezone

try:
    from config import (
        ALL_TEAMS,
        EASTERN_CONFERENCE,
        WESTERN_CONFERENCE,
        SEASON_DISPLAY,
        SEASON_END_YEAR,
        OUTPUT_PATH,
        ABBR_TO_TEAM_NAME,
        TEAM_LOGO_IDS,
    )
except ImportError:
    from scripts.config import (
        ALL_TEAMS,
        EASTERN_CONFERENCE,
        WESTERN_CONFERENCE,
        SEASON_DISPLAY,
        SEASON_END_YEAR,
        OUTPUT_PATH,
        ABBR_TO_TEAM_NAME,
        TEAM_LOGO_IDS,
    )
try:
    from fetch_data import fetch_games, fetch_standings, games_to_pairs
    from calculate_srs import calculate_srs
except ImportError:
    from scripts.fetch_data import fetch_games, fetch_standings, games_to_pairs
    from scripts.calculate_srs import calculate_srs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def generate():
    """Main pipeline: fetch data, calculate SRS, write JSON."""
    logger.info("Starting SRS data generation for %s season", SEASON_DISPLAY)

    # Fetch game data
    try:
        games = fetch_games(SEASON_END_YEAR)
    except Exception as e:
        logger.error("Failed to fetch games: %s", e)
        sys.exit(1)

    if not games:
        logger.error("No games found. Exiting without updating data.")
        sys.exit(1)

    # Fetch standings
    try:
        standings_list = fetch_standings(SEASON_END_YEAR)
    except Exception as e:
        logger.warning("Failed to fetch standings: %s. Will compute from game data.", e)
        standings_list = []

    # Convert to game pairs for SRS calculation
    game_pairs = games_to_pairs(games)

    # Determine which teams have played
    active_teams = set()
    for team_a, team_b, _ in game_pairs:
        active_teams.add(team_a)
        active_teams.add(team_b)
    teams_for_srs = sorted(active_teams)

    # Calculate SRS
    logger.info("Calculating SRS for %d teams from %d games", len(teams_for_srs), len(game_pairs))
    srs_data = calculate_srs(game_pairs, teams_for_srs)

    # Build standings lookup
    standings_map = {}
    for s in standings_list:
        standings_map[s["team"]] = s

    # If we didn't get standings from B-Ref, compute W-L from game data
    if not standings_map:
        logger.info("Computing standings from game data")
        wins = {}
        losses = {}
        for g in games:
            home, away = g["home_team"], g["away_team"]
            if g["home_pts"] > g["away_pts"]:
                wins[home] = wins.get(home, 0) + 1
                losses[away] = losses.get(away, 0) + 1
            else:
                wins[away] = wins.get(away, 0) + 1
                losses[home] = losses.get(home, 0) + 1

        for team in teams_for_srs:
            w = wins.get(team, 0)
            l = losses.get(team, 0)
            total = w + l
            conf = "East" if team in EASTERN_CONFERENCE else "West"
            standings_map[team] = {
                "team": team,
                "conference": conf,
                "wins": w,
                "losses": l,
                "win_pct": round(w / total, 3) if total > 0 else 0.0,
            }

    # Merge SRS with standings and build output
    teams_output = []
    for team in teams_for_srs:
        srs_info = srs_data.get(team, {"srs": 0, "mov": 0, "sos": 0, "games_played": 0})
        standing = standings_map.get(team, {})

        conf = standing.get("conference")
        if not conf:
            conf = "East" if team in EASTERN_CONFERENCE else "West"

        teams_output.append({
            "abbreviation": team,
            "name": ABBR_TO_TEAM_NAME.get(team, team),
            "team_id": TEAM_LOGO_IDS.get(team, 0),
            "conference": conf,
            "wins": standing.get("wins", 0),
            "losses": standing.get("losses", 0),
            "win_pct": standing.get("win_pct", 0.0),
            "srs": srs_info["srs"],
            "mov": srs_info["mov"],
            "sos": srs_info["sos"],
            "games_played": srs_info["games_played"],
        })

    # Sort by SRS descending and assign ranks
    teams_output.sort(key=lambda t: t["srs"], reverse=True)
    for i, team in enumerate(teams_output, 1):
        team["srs_rank"] = i

    # Assign standings rank (by win_pct descending)
    standings_sorted = sorted(teams_output, key=lambda t: t["win_pct"], reverse=True)
    for i, team in enumerate(standings_sorted, 1):
        team["standings_rank"] = i

    # Re-sort by SRS rank for output
    teams_output.sort(key=lambda t: t["srs_rank"])

    output = {
        "metadata": {
            "season": SEASON_DISPLAY,
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_games": len(games),
        },
        "teams": teams_output,
    }

    # Ensure output directory exists
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    logger.info("Wrote SRS data to %s (%d teams, %d games)", OUTPUT_PATH, len(teams_output), len(games))


if __name__ == "__main__":
    generate()
