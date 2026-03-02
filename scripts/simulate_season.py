"""
EPL Monte Carlo Season Simulator
Simulates the rest of the EPL season using SRS ratings.
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

# Fetch remaining (unplayed) games
try:
    from fetch_data import fetch_remaining_games
except ImportError:
    from scripts.fetch_data import fetch_remaining_games

remaining = fetch_remaining_games()
schedule = [{"home": g["home_team"], "away": g["away_team"]} for g in remaining]


def calculate_srs_rmse():
    """Calculate RMSE of SRS prediction errors from played games."""
    try:
        try:
            from fetch_data import fetch_games
        except ImportError:
            from scripts.fetch_data import fetch_games
        played_games = fetch_games()
    except Exception:
        return 1.2  # fallback

    abbr_to_team = {team["abbreviation"]: team for team in teams}
    errors = []
    for g in played_games:
        home, away = g["home_team"], g["away_team"]
        if home not in abbr_to_team or away not in abbr_to_team:
            continue
        predicted = abbr_to_team[home]["srs"] - abbr_to_team[away]["srs"]
        actual = g["home_pts"] - g["away_pts"]
        errors.append(predicted - actual)
    return float(np.sqrt(np.mean(np.square(errors)))) if errors else 1.2


def simulate_game(home_srs, away_srs, std):
    """Return (prob_home_win, prob_draw, prob_away_win).

    EPL draw rate ~25%; we scale win probs accordingly.
    """
    prob_home = 1 - norm.cdf(0, loc=home_srs - away_srs, scale=std)
    draw_prob = 0.25
    prob_home_adj = prob_home * (1 - draw_prob)
    prob_away_adj = (1 - prob_home) * (1 - draw_prob)
    return prob_home_adj, draw_prob, prob_away_adj


def run_simulation(num_sim=DEFAULT_NUM_SIM):
    abbr_to_team = {team["abbreviation"]: team for team in teams}
    std = calculate_srs_rmse()

    # Current points from srs_data
    current_points = {
        team["abbreviation"]: team["wins"] * 3 + team.get("draws", 0)
        for team in teams
    }

    if not schedule:
        print("Warning: Schedule is empty. No games to simulate.")

    results = {abbr: {
        "points": [],
        "title_sim": [],
        "top4_sim": [],
        "top6_sim": [],
        "relegation_sim": [],
    } for abbr in abbr_to_team}

    for _ in range(num_sim):
        sim_points = dict(current_points)

        for game in schedule:
            home, away = game["home"], game["away"]
            if home not in abbr_to_team or away not in abbr_to_team:
                continue
            home_srs = abbr_to_team[home]["srs"]
            away_srs = abbr_to_team[away]["srs"]
            prob_home, prob_draw, prob_away = simulate_game(home_srs, away_srs, std)

            r = random.random()
            if r < prob_home:
                sim_points[home] += 3
            elif r < prob_home + prob_draw:
                sim_points[home] += 1
                sim_points[away] += 1
            else:
                sim_points[away] += 3

        # Final standings
        ranked = sorted(abbr_to_team.keys(), key=lambda a: sim_points[a], reverse=True)

        for abbr in abbr_to_team:
            results[abbr]["points"].append(sim_points[abbr])
            rank = ranked.index(abbr) + 1
            results[abbr]["title_sim"].append(int(rank == 1))
            results[abbr]["top4_sim"].append(int(rank <= 4))    # Champions League
            results[abbr]["top6_sim"].append(int(rank <= 6))    # Europa League
            results[abbr]["relegation_sim"].append(int(rank >= len(ranked) - 2))  # Bottom 3

    # Aggregate
    output = {}
    for abbr, res in results.items():
        pts_arr = np.array(res["points"])
        def pct(arr):
            a = np.array(arr)
            p = a.mean()
            se = float(np.sqrt(p * (1 - p) / len(a))) if len(a) > 1 else 0
            return round(float(p * 100), 1), round(se * 100, 2)

        title_pct, title_se = pct(res["title_sim"])
        top4_pct, top4_se = pct(res["top4_sim"])
        top6_pct, top6_se = pct(res["top6_sim"])
        rel_pct, rel_se = pct(res["relegation_sim"])

        output[abbr] = {
            "expected_points": round(float(np.mean(pts_arr)), 1),
            "std_points": round(float(np.std(pts_arr, ddof=1)), 1) if len(pts_arr) > 1 else 0,
            "title_pct": title_pct,
            "title_pct_stderr": title_se,
            "top4_pct": top4_pct,           # Champions League qualification
            "top4_pct_stderr": top4_se,
            "top6_pct": top6_pct,           # Europa League qualification
            "top6_pct_stderr": top6_se,
            "relegation_pct": rel_pct,      # Relegated (bottom 3)
            "relegation_pct_stderr": rel_se,
        }

    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--num_sim", type=int, default=DEFAULT_NUM_SIM)
    parser.add_argument("--std_error", type=float, default=None,
                        help="Override goal std dev (default: auto from RMSE)")
    args = parser.parse_args()
    results = run_simulation(args.num_sim)
    out_path = os.path.join(base_dir, '..', 'site', 'data', 'simulation_results.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Simulation complete. Results written to {out_path}")


if __name__ == "__main__":
    main()