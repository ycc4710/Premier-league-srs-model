"""
NBA Schedule Fetcher
Fetches NBA schedule for the current week and outputs as JSON.
"""
import requests
import datetime
import json
import re
import time
import pandas as pd
from bs4 import BeautifulSoup

NBA_SCHEDULE_URL = "https://www.basketball-reference.com/leagues/NBA_2026_games.html"

# Placeholder: You may need to scrape or use an API for actual schedule

def get_this_week_schedule():
    today = datetime.date(2024, 10, 29)  # Temporarily set to a date during the season with games
    season_end_year = 2025  # Temporarily set for testing
    base = f"https://www.basketball-reference.com/leagues/NBA_{season_end_year}_games"
    index_url = base + ".html"
    HEADERS = {"User-Agent": "Mozilla/5.0"}
    time.sleep(30)  # Initial delay to avoid rate limiting
    html = requests.get(index_url, headers=HEADERS, timeout=30).text
    soup = BeautifulSoup(html, "html.parser")
    month_hrefs = []
    for a in soup.select('a[href*="NBA_{}_games-"]'.format(season_end_year)):
        href = a.get("href", "")
        if re.search(rf"/leagues/NBA_{season_end_year}_games-[a-z]+\.html$", href):
            month_hrefs.append("https://www.basketball-reference.com" + href)
    month_hrefs = sorted(set(month_hrefs))
    if not month_hrefs:
        month_hrefs = [index_url]
    frames = []
    for url in month_hrefs:
        print(f"Fetching month URL: {url}")
        time.sleep(30.0)  # Increased delay to avoid rate limiting
        mhtml = requests.get(url, headers=HEADERS, timeout=30).text
        try:
            df = pd.read_html(mhtml, attrs={'id': 'schedule'})[0]
            df["season_end_year"] = season_end_year
            df["source_url"] = url
            frames.append(df)
        except Exception as e:
            print(f"Failed to parse table from {url}: {e}")
            continue
    if not frames:
        print("No schedule tables found. Scraping failed.")
        return []
    out = pd.concat(frames, ignore_index=True)
    out = out[out["Date"] != "Date"].copy()
    # Filter for this week
    start = today - datetime.timedelta(days=today.weekday())
    end = start + datetime.timedelta(days=6)
    games = []
    for _, row in out.iterrows():
        try:
            game_date = datetime.datetime.strptime(row["Date"], "%a, %b %d, %Y").date()
        except Exception:
            continue
        if not (start <= game_date <= end):
            continue
        games.append({
            "date": str(game_date),
            "home": row["Home/Neutral"],
            "away": row["Visitor/Neutral"]
        })
    print(f"Found {len(games)} games for this week.")
    if games:
        print("Last 10 games:")
        for g in games[-10:]:
            print(g)
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
