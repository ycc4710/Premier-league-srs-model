"""
NBA Monte Carlo Season Simulator
Simulates the rest of the NBA season using SRS ratings.
"""
import json
import random
import argparse
import os

DEFAULT_STD_ERROR = 7.0
DEFAULT_NUM_SIM = 1000

# Load SRS data
base_dir = os.path.dirname(__file__)
srs_path = os.path.join(base_dir, '..', 'site', 'data', 'srs_data.json')
schedule_path = os.path.join(base_dir, '..', 'site', 'data', 'weekly_schedule.json')
with open(srs_path) as f:
    srs_data = json.load(f)
teams = srs_data["teams"]
# Load schedule
try:
    with open(schedule_path) as f:
        schedule = json.load(f)
except FileNotFoundError:
    schedule = []

# Placeholder: Simulate games

def simulate_game(home_srs, away_srs, std_error):
    margin = home_srs - away_srs + random.gauss(0, std_error)
    home_win_prob = 1 / (1 + 10 ** (-(margin) / 10))
    return home_win_prob

def run_simulation(std_error=DEFAULT_STD_ERROR, num_sim=DEFAULT_NUM_SIM):
    results = {team["abbreviation"]: {"division_wins": 0, "playoff_berths": 0, "wins": 0} for team in teams}
    abbr_to_team = {team["abbreviation"]: team for team in teams}
    # Fallback: if division info missing, use conference
    divisions = {team["abbreviation"]: team.get("division", team.get("conference", "")) for team in teams}
    if not schedule:
        print("Warning: Schedule is empty. No games to simulate.")
    for _ in range(num_sim):
        sim_wins = {abbr: 0 for abbr in abbr_to_team}
        # Simulate each game
        for game in schedule:
            home = game["home"]
            away = game["away"]
            if home not in abbr_to_team or away not in abbr_to_team:
                continue
            home_srs = abbr_to_team[home]["srs"]
            away_srs = abbr_to_team[away]["srs"]
            margin = home_srs - away_srs + random.gauss(0, std_error)
            home_win = margin > 0
            if home_win:
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
        # Track wins
        for abbr in sim_wins:
            results[abbr]["wins"] += sim_wins[abbr]
    # Average results
    for abbr in results:
        results[abbr]["division_prob"] = results[abbr]["division_wins"] / num_sim if num_sim else 0
        results[abbr]["playoff_prob"] = results[abbr]["playoff_berths"] / num_sim if num_sim else 0
        results[abbr]["avg_wins"] = results[abbr]["wins"] / num_sim if num_sim else 0
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--std_error", type=float, default=DEFAULT_STD_ERROR)
    parser.add_argument("--num_sim", type=int, default=DEFAULT_NUM_SIM)
    args = parser.parse_args()
    results = run_simulation(args.std_error, args.num_sim)
    out_path = os.path.join(os.path.dirname(__file__), '..', 'site', 'data', 'simulation_results.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
