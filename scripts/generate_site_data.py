"""Generate site data JSON by fetching games, calculating SRS, predictions, and simulation."""

import json
import logging
import math
import os
import sys
from datetime import datetime, timezone

from scripts.config import (
    ALL_TEAMS,
    SEASON_DISPLAY,
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
from scripts.predictions import predict_games, fetch_injury_data

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
        draws = {}
        losses = {}
        for g in games:
            home, away = g["home_team"], g["away_team"]
            home_pts, away_pts = g["home_pts"], g["away_pts"]
            if home_pts > away_pts:
                wins[home] = wins.get(home, 0) + 1
                losses[away] = losses.get(away, 0) + 1
            elif home_pts == away_pts:
                draws[home] = draws.get(home, 0) + 1
                draws[away] = draws.get(away, 0) + 1
            else:
                wins[away] = wins.get(away, 0) + 1
                losses[home] = losses.get(home, 0) + 1

        for team in teams_for_srs:
            w = wins.get(team, 0)
            d = draws.get(team, 0)
            l = losses.get(team, 0)
            total = w + d + l
            standings_map[team] = {
                "team": team,
                "conference": "EPL",
                "wins": w,
                "draws": d,
                "losses": l,
                "win_pct": round(w / total, 3) if total > 0 else 0.0,
            }

    return standings_map


def generate():
    """Main pipeline: fetch data, calculate SRS, predict, simulate, write JSON."""
    logger.info("Starting SRS data generation for %s season", SEASON_DISPLAY)

    # ── 1. Fetch completed game data ──
    try:
        games = fetch_games()
    except Exception as e:
        logger.error("Failed to fetch games: %s", e)
        sys.exit(1)

    if not games:
        logger.error("No games found. Exiting without updating data.")
        sys.exit(1)

    # ── 2. Fetch standings ──
    try:
        standings_list = fetch_standings()
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

        teams_output.append({
            "abbreviation": team,
            "name": ABBR_TO_TEAM_NAME.get(team, team),
            "team_id": TEAM_LOGO_IDS.get(team, ""),
            "conference": "EPL",
            "division": TEAM_TO_DIVISION.get(team, ""),
            "wins": standing.get("wins", 0),
            "draws": standing.get("draws", 0),
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

    # Assign standings ranks (EPL: points = wins*3 + draws)
    standings_sorted = sorted(
        teams_output,
        key=lambda t: (t["wins"] * 3 + t["draws"], t["wins"]),
        reverse=True,
    )
    for i, team in enumerate(standings_sorted, 1):
        team["standings_rank"] = i

    teams_output.sort(key=lambda t: t["srs_rank"])

    # ── 5b. Compute model diagnostics ──
    total_goals = 0
    home_margin_sum = 0
    squared_errors = []
    for g in games:
        home_pts, away_pts = g["home_pts"], g["away_pts"]
        total_goals += home_pts + away_pts
        home_margin_sum += home_pts - away_pts
        home_srs = srs_data.get(g["home_team"], {}).get("srs", 0.0)
        away_srs = srs_data.get(g["away_team"], {}).get("srs", 0.0)
        predicted = home_srs - away_srs
        actual = home_pts - away_pts
        squared_errors.append((predicted - actual) ** 2)

    n_games = len(games)
    model_stats = {
        "rmse": round(math.sqrt(sum(squared_errors) / n_games), 2) if n_games else 0,
        "avg_gpg": round(total_goals / (n_games * 2), 2) if n_games else 0,
        "home_advantage": round(home_margin_sum / n_games, 2) if n_games else 0,
    }
    logger.info("Model stats: RMSE=%.2f, Avg GPG=%.2f, Home Adv=%.2f",
                model_stats["rmse"], model_stats["avg_gpg"], model_stats["home_advantage"])

    # ── 5c. Per-team home advantage with Bayesian shrinkage ──
    SHRINKAGE_K = 6  # need ~6 home games before trusting own data 50%
    league_hca = model_stats["home_advantage"]

    team_home_margins = {}
    team_away_margins = {}
    for g in games:
        hm = g["home_pts"] - g["away_pts"]
        team_home_margins.setdefault(g["home_team"], []).append(hm)
        team_away_margins.setdefault(g["away_team"], []).append(-hm)

    team_hca = {}
    for team in teams_for_srs:
        home_margins = team_home_margins.get(team, [])
        away_margins = team_away_margins.get(team, [])
        n_home = len(home_margins)
        n_away = len(away_margins)

        avg_home = sum(home_margins) / n_home if n_home else 0.0
        avg_away = sum(away_margins) / n_away if n_away else 0.0
        raw_hca = avg_home - avg_away

        n_eff = min(n_home, n_away)
        weight = n_eff / (n_eff + SHRINKAGE_K)
        shrunk_hca = weight * raw_hca + (1 - weight) * league_hca
        team_hca[team] = round(shrunk_hca, 3)

        for t in teams_output:
            if t["abbreviation"] == team:
                t["home_advantage"] = team_hca[team]
                t["home_games"] = n_home
                break

    logger.info("Per-team HCA computed (league avg: %.2f, range: %.2f to %.2f)",
                league_hca,
                min(team_hca.values()) if team_hca else 0,
                max(team_hca.values()) if team_hca else 0)

    # ── 6. Fetch injury data from FPL API ──
    injury_data = ({}, {})
    try:
        injury_data = fetch_injury_data()  # returns (scores_dict, details_dict)
        logger.info("Fetched injury data for %d teams", len(injury_data[0]))
    except Exception as e:
        logger.warning("Could not fetch injury data: %s", e)

    # ── 7. Fetch upcoming games and generate predictions ──
    predictions = []
    try:
        upcoming = fetch_upcoming_games(days_ahead=10)
        if upcoming:
            predictions = predict_games(
                upcoming_games=upcoming,
                srs_ratings=srs_data,
                league_home_advantage=model_stats["home_advantage"],
                team_hca=team_hca,
                completed_games=games,
                injury_data=injury_data,
            )
            logger.info("Generated %d game predictions", len(predictions))
    except Exception as e:
        logger.warning("Failed to fetch upcoming games: %s", e)

    # ── 8. Fetch remaining games for client-side Monte Carlo ──
    simulation = {}
    try:
        remaining = fetch_remaining_games()
        if remaining:
            current_standings = {}
            for team in teams_for_srs:
                s = standings_map.get(team, {})
                current_standings[team] = {
                    "wins": s.get("wins", 0),
                    "draws": s.get("draws", 0),
                    "losses": s.get("losses", 0),
                    "points": s.get("wins", 0) * 3 + s.get("draws", 0),
                    "conference": "EPL",
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

    # ── 9. Write output JSON ──
    output = {
        "metadata": {
            "season": SEASON_DISPLAY,
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_games": len(games),
            "model_stats": model_stats,
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