"""
NBA Schedule Fetcher
Fetches NBA schedule for the current week and outputs as JSON.
"""
# Use fetch_games from fetch_data.py to get all 2026 games, then filter for this week and games without a score
import json
import os
from datetime import datetime, timedelta
try:
    from fetch_data import fetch_games
except ImportError:
    from scripts.fetch_data import fetch_games

def get_this_week_schedule():
    today = datetime.now().date()
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    all_games = fetch_games(2026)
    games = []
    for g in all_games:
        # Parse date string to date object
        try:
            game_date = datetime.strptime(g["date"], "%a, %b %d, %Y").date()
        except Exception:
            try:
                game_date = datetime.strptime(g["date"], "%Y-%m-%d").date()
            except Exception:
                continue
        # Only games this week and without a score
        if start <= game_date <= end and (g.get("home_pts") is None or g.get("away_pts") is None):
            games.append({
                "date": str(game_date),
                "home": g["home_team"],
                "away": g["away_team"]
            })
    print(f"Found {len(games)} games for this week without scores.")
    return games
    return games

def main():
    import os
    schedule = get_this_week_schedule()
    out_path = os.path.join(os.path.dirname(__file__), '..', 'site', 'data', 'weekly_schedule.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(schedule, f, indent=2)

if __name__ == "__main__":
    main()
