"""Generate site data JSON by fetching games, calculating SRS, predictions, and simulation."""

import json
import logging
import os
import sys
from datetime import datetime, timezone

from scripts.config import (
    ALL_TEAMS,
    EASTERN_CONFERENCE,
    WESTERN_CONFERENCE,
    SEASON_DISPLAY,
    SEASON_END_YEAR,
    OUTPUT_PATH,
    ABBR_TO_TEAM_NAME,
    TEAM_LOGO_IDS,
    DIVISIONS,
    TEAM_TO_DIVISION,
)
from scripts.fetch_data import (
    fetch_games, fetch_standings, fetch_upcoming_games,
    fetch_remaining_games, games_to_pairs,
)
from scripts.calculate_srs import calculate_srs
from scripts.predictions import predict_games

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _build_standings_map(games, standings_list, teams_for_srs):
    """Build a standings lookup dict, falling back to game data if needed."""
    standings_map = {}
    for s in standings_list:
        standings_map[s["team"]] = s

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

    return standings_map


def generate():
    """Main pipeline: fetch data, calculate SRS, predict, simulate, write JSON."""
    logger.info("Starting SRS data generation for %s season", SEASON_DISPLAY)

    # ── 1. Fetch completed game data ──
    try:
        games = fetch_games(SEASON_END_YEAR)
    except Exception as e:
        logger.error("Failed to fetch games: %s", e)
        sys.exit(1)

    if not games:
        logger.error("No games found. Exiting without updating data.")
        sys.exit(1)

    # ── 2. Fetch standings ──
    try:
        standings_list = fetch_standings(SEASON_END_YEAR)
    except Exception as e:
        logger.warning("Failed to fetch standings: %s. Will compute from game data.", e)
        standings_list = []

    # ── 3. Calculate SRS ──
    game_pairs = games_to_pairs(games)
    active_teams = set()
    for team_a, team_b, _ in game_pairs:
        active_teams.add(team_a)
        active_teams.add(team_b)
    teams_for_srs = sorted(active_teams)

    logger.info("Calculating SRS for %d teams from %d games", len(teams_for_srs), len(game_pairs))
    srs_data = calculate_srs(game_pairs, teams_for_srs)

    # ── 4. Build standings ──
    standings_map = _build_standings_map(games, standings_list, teams_for_srs)

    # ── 5. Build team output ──
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

    # Assign SRS ranks
    teams_output.sort(key=lambda t: t["srs"], reverse=True)
    for i, team in enumerate(teams_output, 1):
        team["srs_rank"] = i

    # Assign standings ranks
    standings_sorted = sorted(teams_output, key=lambda t: t["win_pct"], reverse=True)
    for i, team in enumerate(standings_sorted, 1):
        team["standings_rank"] = i

    teams_output.sort(key=lambda t: t["srs_rank"])

    # ── 6. Fetch upcoming games and generate predictions ──
    predictions = []
    try:
        upcoming = fetch_upcoming_games(SEASON_END_YEAR, days_ahead=10)
        if upcoming:
            predictions = predict_games(upcoming, srs_data)
            logger.info("Generated %d game predictions", len(predictions))
    except Exception as e:
        logger.warning("Failed to fetch upcoming games: %s", e)

    # ── 7. Fetch remaining games for client-side Monte Carlo ──
    simulation = {}
    try:
        remaining = fetch_remaining_games(SEASON_END_YEAR)
        if remaining:
            current_standings = {}
            for team in teams_for_srs:
                s = standings_map.get(team, {})
                conf = s.get("conference")
                if not conf:
                    conf = "East" if team in EASTERN_CONFERENCE else "West"
                current_standings[team] = {
                    "wins": s.get("wins", 0),
                    "losses": s.get("losses", 0),
                    "conference": conf,
                    "division": TEAM_TO_DIVISION.get(team, ""),
                }

            simulation = {
                "remaining_games": [
                    {"home_team": g["home_team"], "away_team": g["away_team"]}
                    for g in remaining
                ],
                "current_standings": current_standings,
                "divisions": DIVISIONS,
            }
            logger.info("Included %d remaining games for client-side simulation", len(remaining))
    except Exception as e:
        logger.warning("Failed to fetch remaining games: %s", e)

    # ── 8. Write output JSON ──
    output = {
        "metadata": {
            "season": SEASON_DISPLAY,
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_games": len(games),
        },
        "teams": teams_output,
        "predictions": predictions,
        "simulation": simulation,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    logger.info("Wrote SRS data to %s (%d teams, %d games, %d predictions)",
                OUTPUT_PATH, len(teams_output), len(games), len(predictions))


if __name__ == "__main__":
    generate()
