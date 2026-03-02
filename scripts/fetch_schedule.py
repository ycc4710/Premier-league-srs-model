"""
EPL Schedule Fetcher
Fetches EPL schedule for the current week and outputs as JSON.
"""
import json
import os
from datetime import datetime, timedelta

try:
    from fetch_data import fetch_upcoming_games
except ImportError:
    from scripts.fetch_data import fetch_upcoming_games


def get_this_week_schedule():
    today = datetime.now().date()
    start = today - timedelta(days=today.weekday())  # Monday
    end = start + timedelta(days=6)                  # Sunday

    # fetch_upcoming_games already filters by date range, but we pass 7 days to be safe
    all_games = fetch_upcoming_games(days_ahead=7)

    games = []
    for g in all_games:
        try:
            game_date = datetime.strptime(g["date_parsed"], "%Y-%m-%d").date()
        except Exception:
            continue

        if start <= game_date <= end:
            games.append({
                "date": str(game_date),
                "home": g["home_team"],
                "away": g["away_team"],
            })

    print(f"Found {len(games)} EPL games this week.")
    return games


def main():
    schedule = get_this_week_schedule()
    out_path = os.path.join(
        os.path.dirname(__file__), "..", "site", "data", "weekly_schedule.json"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(schedule, f, indent=2)
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()