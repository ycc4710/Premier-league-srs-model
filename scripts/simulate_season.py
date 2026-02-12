"""
NBA Monte Carlo Season Simulator
Simulates the rest of the NBA season using SRS ratings.
"""

import json
import random
import argparse
import os
import numpy as np
from scipy.stats import norm

DEFAULT_NUM_SIM = 1000


# Load SRS data
base_dir = os.path.dirname(__file__)
srs_path = os.path.join(base_dir, '..', 'site', 'data', 'srs_data.json')
with open(srs_path) as f:
    srs_data = json.load(f)
teams = srs_data["teams"]

# Use fetch_games to get all 2026 games, then filter for games without a score
try:
    from fetch_data import fetch_games
except ImportError:
    from scripts.fetch_data import fetch_games

all_games = fetch_games(2026)
schedule = []
for g in all_games:
    # Only simulate games without a score
    if g.get("home_pts") is None or g.get("away_pts") is None:
        schedule.append({
            "home": g["home_team"],
            "away": g["away_team"]
        })

# Placeholder: Simulate games


# Calculate RMSE of SRS prediction errors from played games
def calculate_srs_rmse():
    # Use all played games from fetch_games
    played_games = [g for g in all_games if g.get("home_pts") is not None and g.get("away_pts") is not None]
    abbr_to_team = {team["abbreviation"]: team for team in teams}
    errors = []
    for g in played_games:
        home = g["home_team"]
        away = g["away_team"]
        if home not in abbr_to_team or away not in abbr_to_team:
            continue
        predicted_margin = abbr_to_team[home]["srs"] - abbr_to_team[away]["srs"]
        actual_margin = g["home_pts"] - g["away_pts"]
        errors.append(predicted_margin - actual_margin)
    if errors:
        return float(np.sqrt(np.mean(np.square(errors))))
    else:
        return 7.0  # fallback default

def simulate_game(home_srs, away_srs, std):
    # Median margin is home_srs - away_srs
    # Probability home wins = P(margin > 0) = 1 - CDF(0)
    home_win_prob = 1 - norm.cdf(0, loc=home_srs - away_srs, scale=std)
    return home_win_prob


def run_simulation(num_sim=DEFAULT_NUM_SIM):
    results = {team["abbreviation"]: {
        "division_wins": 0,
        "playoff_berths": 0,
        "wins": [],  # store all win counts for stddev
    } for team in teams}
    abbr_to_team = {team["abbreviation"]: team for team in teams}
    divisions = {team["abbreviation"]: team.get("division", team.get("conference", "")) for team in teams}
    std = calculate_srs_rmse()
    if not schedule:
        print("Warning: Schedule is empty. No games to simulate.")
    for _ in range(num_sim):
        sim_wins = {abbr: 0 for abbr in abbr_to_team}
        for game in schedule:
            home = game["home"]
            away = game["away"]
            if home not in abbr_to_team or away not in abbr_to_team:
                continue
            home_srs = abbr_to_team[home]["srs"]
            away_srs = abbr_to_team[away]["srs"]
            home_win_prob = simulate_game(home_srs, away_srs, std)
            if random.random() < home_win_prob:
                sim_wins[home] += 1
            else:
                sim_wins[away] += 1
        # Division winners
        division_winners = {}
        for abbr, div in divisions.items():
            div_teams = [a for a, d in divisions.items() if d == div]
            div_winner = max(div_teams, key=lambda a: sim_wins[a])
            division_winners[div] = div_winner
        for winner in division_winners.values():
            results[winner]["division_wins"] += 1
        # Playoff berths (top 8 in each conference)
        confs = {team["abbreviation"]: team["conference"] for team in teams}
        for conf in ["East", "West"]:
            conf_teams = [a for a, c in confs.items() if c == conf]
            sorted_conf = sorted(conf_teams, key=lambda a: sim_wins[a], reverse=True)
            for abbr in sorted_conf[:8]:
                results[abbr]["playoff_berths"] += 1
        for abbr in sim_wins:
            results[abbr]["wins"].append(sim_wins[abbr])
    # Aggregate results
    output = {}
    for abbr, res in results.items():
        win_arr = np.array(res["wins"])
        output[abbr] = {
            "playoff_prob": res["playoff_berths"] / num_sim if num_sim else 0,
            "division_prob": res["division_wins"] / num_sim if num_sim else 0,
            "expected_wins": float(np.mean(win_arr)) if len(win_arr) else 0,
            "std_wins": float(np.std(win_arr, ddof=1)) if len(win_arr) > 1 else 0,
        }
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--num_sim", type=int, default=DEFAULT_NUM_SIM)
    args = parser.parse_args()
    results = run_simulation(args.num_sim)
    out_path = os.path.join(os.path.dirname(__file__), '..', 'site', 'data', 'simulation_results.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
