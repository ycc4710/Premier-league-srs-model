"""
Predict margin of victory and home win probability for upcoming NBA games using SRS ratings.
Outputs predictions to weekly_schedule.json for frontend UI.
"""
import json
import os
import numpy as np

DEFAULT_STD_ERROR = 7.0  # Typical NBA RMSE for margin prediction

base_dir = os.path.dirname(__file__)
srs_path = os.path.join(base_dir, '..', 'site', 'data', 'srs_data.json')
schedule_path = os.path.join(base_dir, '..', 'site', 'data', 'weekly_schedule.json')
output_path = schedule_path  # Overwrite with predictions

# Load SRS data
with open(srs_path) as f:
    srs_data = json.load(f)
teams = {team["abbreviation"]: team for team in srs_data["teams"]}

# Load schedule
try:
    with open(schedule_path) as f:
        schedule = json.load(f)
except FileNotFoundError:
    schedule = []

predictions = []
for game in schedule:
    home = game["home"]
    away = game["away"]
    home_srs = teams.get(home, {}).get("srs", 0)
    away_srs = teams.get(away, {}).get("srs", 0)
    mov_pred = home_srs - away_srs  # Predicted margin of victory
    # Probability home wins: normal CDF
    prob_home_win = float(1.0 / (1.0 + np.exp(-mov_pred / DEFAULT_STD_ERROR)))
    predictions.append({
        "home": home,
        "away": away,
        "home_name": teams.get(home, {}).get("name", home),
        "away_name": teams.get(away, {}).get("name", away),
        "predicted_margin": round(mov_pred, 2),
        "prob_home_win": round(prob_home_win, 3),
        "date": game.get("date", ""),
    })

with open(output_path, "w") as f:
    json.dump(predictions, f, indent=2)

print(f"Wrote predictions for {len(predictions)} games to {output_path}")
