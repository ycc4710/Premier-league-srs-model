"""Game predictions and Monte Carlo season simulation using SRS ratings.

Prediction model:
  Expected margin = SRS_home - SRS_away + HOME_COURT_ADVANTAGE
  Win probability derived from margin using a logistic function calibrated
  to NBA historical data (~12 point std dev in game outcomes).
"""

import math
import numpy as np
from collections import defaultdict


# Home court advantage in points (NBA average ~3.0 points)
HOME_COURT_ADVANTAGE = 3.0

# Standard deviation of NBA game outcomes (~12 points)
# Used to convert predicted margin to win probability
GAME_STD_DEV = 12.0

# Number of Monte Carlo simulation trials
NUM_SIMULATIONS = 10000


def predict_margin(home_srs, away_srs):
    """Predict the point margin for a game (from home team's perspective)."""
    return home_srs - away_srs + HOME_COURT_ADVANTAGE


def win_probability(predicted_margin):
    """Convert a predicted margin to a win probability for the favored side.

    Uses a logistic/normal CDF approximation calibrated to NBA game variance.
    A predicted margin of 0 gives 50% win probability.
    """
    # Use normal CDF: P(home wins) = Phi(margin / std_dev)
    return 0.5 * (1 + math.erf(predicted_margin / (GAME_STD_DEV * math.sqrt(2))))


def predict_games(upcoming_games, srs_ratings):
    """Generate predictions for a list of upcoming games.

    Args:
        upcoming_games: list of dicts with home_team, away_team, date, date_parsed
        srs_ratings: dict mapping team abbreviation to {srs, mov, sos, ...}

    Returns:
        list of prediction dicts sorted by date then by abs(spread) descending
    """
    predictions = []
    for game in upcoming_games:
        home = game["home_team"]
        away = game["away_team"]

        home_srs = srs_ratings.get(home, {}).get("srs", 0.0)
        away_srs = srs_ratings.get(away, {}).get("srs", 0.0)

        margin = predict_margin(home_srs, away_srs)
        home_win_prob = win_probability(margin)

        if margin >= 0:
            favored = home
            underdog = away
            spread = -margin  # Spread is expressed as the favored team's line (negative)
        else:
            favored = away
            underdog = home
            spread = margin

        predictions.append({
            "date": game.get("date", ""),
            "date_parsed": game.get("date_parsed", ""),
            "home_team": home,
            "away_team": away,
            "home_srs": round(home_srs, 2),
            "away_srs": round(away_srs, 2),
            "predicted_margin": round(margin, 1),
            "home_win_prob": round(home_win_prob, 3),
            "favored": favored,
            "underdog": underdog,
            "spread": round(spread, 1),
        })

    # Sort by date, then by how close the game is (biggest mismatches first)
    predictions.sort(key=lambda p: (p["date_parsed"], -abs(p["predicted_margin"])))
    return predictions


def monte_carlo_season(remaining_games, current_standings, srs_ratings,
                       num_simulations=NUM_SIMULATIONS):
    """Run Monte Carlo simulation of remaining season games.

    Args:
        remaining_games: list of dicts with home_team, away_team
        current_standings: dict mapping team to {wins, losses, conference}
        srs_ratings: dict mapping team to {srs, ...}
        num_simulations: number of trials to run

    Returns:
        dict mapping team to simulation results:
        {
            avg_wins, avg_losses, win_range_low, win_range_high,
            playoff_pct, top_seed_pct, conference
        }
    """
    if not remaining_games:
        # No remaining games - return current standings as final
        results = {}
        for team, standing in current_standings.items():
            results[team] = {
                "avg_wins": float(standing["wins"]),
                "avg_losses": float(standing["losses"]),
                "win_range_low": standing["wins"],
                "win_range_high": standing["wins"],
                "playoff_pct": 0.0,
                "top_seed_pct": 0.0,
                "play_in_pct": 0.0,
                "lottery_pct": 0.0,
                "conference": standing.get("conference", ""),
            }
        return results

    teams = list(current_standings.keys())
    team_idx = {t: i for i, t in enumerate(teams)}
    n_teams = len(teams)

    # Pre-compute win probabilities for all remaining games
    game_probs = []
    for game in remaining_games:
        home = game["home_team"]
        away = game["away_team"]
        if home not in team_idx or away not in team_idx:
            continue
        home_srs = srs_ratings.get(home, {}).get("srs", 0.0)
        away_srs = srs_ratings.get(away, {}).get("srs", 0.0)
        margin = predict_margin(home_srs, away_srs)
        prob = win_probability(margin)
        game_probs.append((team_idx[home], team_idx[away], prob))

    # Base wins/losses from current standings
    base_wins = np.array([current_standings[t]["wins"] for t in teams], dtype=float)
    base_losses = np.array([current_standings[t]["losses"] for t in teams], dtype=float)

    # Track results across simulations
    total_wins = np.zeros((num_simulations, n_teams))
    playoff_counts = np.zeros(n_teams)
    top_seed_counts = np.zeros(n_teams)
    play_in_counts = np.zeros(n_teams)

    # Conference mapping
    conf_map = {t: current_standings[t].get("conference", "") for t in teams}

    # Pre-generate random numbers for all simulations at once
    rng = np.random.default_rng(seed=42)
    all_randoms = rng.random((num_simulations, len(game_probs)))

    for sim in range(num_simulations):
        sim_wins = base_wins.copy()
        sim_losses = base_losses.copy()

        # Simulate each remaining game
        for g_idx, (home_idx, away_idx, prob) in enumerate(game_probs):
            if all_randoms[sim, g_idx] < prob:
                sim_wins[home_idx] += 1
                sim_losses[away_idx] += 1
            else:
                sim_wins[away_idx] += 1
                sim_losses[home_idx] += 1

        total_wins[sim] = sim_wins

        # Determine playoff standings by conference
        for conf in ["East", "West"]:
            conf_teams = [i for i in range(n_teams) if conf_map[teams[i]] == conf]
            if not conf_teams:
                continue
            # Sort by wins descending (tiebreaker: random since we don't have h2h)
            conf_teams.sort(key=lambda i: sim_wins[i], reverse=True)

            # Top 6 seeds: direct playoff qualification
            for rank, i in enumerate(conf_teams[:6]):
                playoff_counts[i] += 1
            # #1 seed
            if conf_teams:
                top_seed_counts[conf_teams[0]] += 1
            # 7-10 seeds: play-in tournament
            for i in conf_teams[6:10]:
                play_in_counts[i] += 1

    # Aggregate results
    results = {}
    for i, team in enumerate(teams):
        wins_dist = total_wins[:, i]
        results[team] = {
            "avg_wins": round(float(np.mean(wins_dist)), 1),
            "avg_losses": round(float(82 - np.mean(wins_dist)), 1),
            "win_range_low": int(np.percentile(wins_dist, 5)),
            "win_range_high": int(np.percentile(wins_dist, 95)),
            "playoff_pct": round(float(playoff_counts[i] / num_simulations * 100), 1),
            "top_seed_pct": round(float(top_seed_counts[i] / num_simulations * 100), 1),
            "play_in_pct": round(float(play_in_counts[i] / num_simulations * 100), 1),
            "lottery_pct": round(float(
                (num_simulations - playoff_counts[i] - play_in_counts[i])
                / num_simulations * 100
            ), 1),
            "conference": conf_map.get(team, ""),
        }

    return results
