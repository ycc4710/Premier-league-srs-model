"""Fetch NBA game data and standings from Basketball-Reference.com."""

import logging
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup, Comment

from scripts.config import (
    SCHEDULE_URL,
    STANDINGS_URL,
    SCHEDULE_MONTHS,
    SEASON_END_YEAR,
    REQUEST_DELAY,
    USER_AGENT,
    TEAM_NAME_TO_ABBR,
)

logger = logging.getLogger(__name__)


def _get_page(url):
    """Fetch a page with proper headers and rate limiting."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.basketball-reference.com/",
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return response.text


def _team_abbr(name):
    """Convert a full team name to its abbreviation."""
    name = name.strip()
    if name in TEAM_NAME_TO_ABBR:
        return TEAM_NAME_TO_ABBR[name]
    # Try partial matching for edge cases
    for full_name, abbr in TEAM_NAME_TO_ABBR.items():
        if name in full_name or full_name in name:
            return abbr
    logger.warning("Unknown team name: %s", name)
    return None


def _get_schedule_months(season_end_year):
    """Determine which months to scrape based on current date."""
    now = datetime.now()
    months = []
    for month in SCHEDULE_MONTHS:
        # Months oct-dec are in the year before season_end_year
        if month in ("october", "november", "december"):
            month_year = season_end_year - 1
        else:
            month_year = season_end_year

        month_num = {
            "october": 10, "november": 11, "december": 12,
            "january": 1, "february": 2, "march": 3, "april": 4,
        }[month]

        # Only include months up to the current month
        month_date = datetime(month_year, month_num, 1)
        if month_date <= now:
            months.append(month)

    return months


def fetch_games(season_end_year=SEASON_END_YEAR):
    """Scrape game results from Basketball-Reference schedule pages.

    Returns:
        list of dicts with keys: date, home_team, away_team, home_pts, away_pts
        Teams are identified by their abbreviation (e.g., "BOS", "LAL").
    """
    months = _get_schedule_months(season_end_year)
    all_games = []

    for month in months:
        url = SCHEDULE_URL.format(year=season_end_year, month=month)
        logger.info("Fetching schedule: %s", url)

        try:
            html = _get_page(url)
        except requests.RequestException as e:
            logger.warning("Failed to fetch %s: %s", month, e)
            continue

        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", id="schedule")
        if not table:
            logger.warning("No schedule table found for %s", month)
            continue

        tbody = table.find("tbody")
        if not tbody:
            continue

        for row in tbody.find_all("tr"):
            # Skip header rows that appear mid-table
            if row.find("th", {"scope": "col"}):
                continue

            cells = row.find_all(["th", "td"])
            if len(cells) < 6:
                continue

            # Basketball-Reference schedule table columns:
            # [0] Date (th), [1] Start time, [2] Visitor team, [3] Visitor PTS,
            # [4] Home team, [5] Home PTS, ...
            date_cell = cells[0]
            visitor_cell = cells[2]
            visitor_pts_cell = cells[3]
            home_cell = cells[4]
            home_pts_cell = cells[5]

            # Skip games that haven't been played yet (no score)
            visitor_pts_text = visitor_pts_cell.get_text(strip=True)
            home_pts_text = home_pts_cell.get_text(strip=True)
            if not visitor_pts_text or not home_pts_text:
                continue

            try:
                visitor_pts = int(visitor_pts_text)
                home_pts = int(home_pts_text)
            except ValueError:
                continue

            # Extract team names from links
            visitor_link = visitor_cell.find("a")
            home_link = home_cell.find("a")
            visitor_name = visitor_link.get_text(strip=True) if visitor_link else visitor_cell.get_text(strip=True)
            home_name = home_link.get_text(strip=True) if home_link else home_cell.get_text(strip=True)

            visitor_abbr = _team_abbr(visitor_name)
            home_abbr = _team_abbr(home_name)
            if not visitor_abbr or not home_abbr:
                continue

            game_date = date_cell.get_text(strip=True)

            all_games.append({
                "date": game_date,
                "home_team": home_abbr,
                "away_team": visitor_abbr,
                "home_pts": home_pts,
                "away_pts": visitor_pts,
            })

    logger.info("Fetched %d games total", len(all_games))
    return all_games


def fetch_standings(season_end_year=SEASON_END_YEAR):
    """Scrape current standings from Basketball-Reference.

    Returns:
        list of dicts with keys: team, conference, wins, losses, win_pct
    """
    url = STANDINGS_URL.format(year=season_end_year)
    logger.info("Fetching standings: %s", url)

    html = _get_page(url)
    soup = BeautifulSoup(html, "lxml")

    standings = []

    # B-Ref has conference standings tables.
    # They may be in comments (rendered via JS on the site).
    # Look for tables directly first, then inside HTML comments.
    for conf_id, conf_name in [
        ("confs_standings_E", "East"),
        ("confs_standings_W", "West"),
    ]:
        table = soup.find("table", id=conf_id)

        # If not found directly, search inside HTML comments
        if not table:
            for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
                if conf_id in str(comment):
                    comment_soup = BeautifulSoup(str(comment), "lxml")
                    table = comment_soup.find("table", id=conf_id)
                    if table:
                        break

        # Also try the expanded standings table IDs
        if not table:
            alt_id = f"divs_standings_{conf_name[0]}"
            table = soup.find("table", id=alt_id)
            if not table:
                for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
                    if alt_id in str(comment):
                        comment_soup = BeautifulSoup(str(comment), "lxml")
                        table = comment_soup.find("table", id=alt_id)
                        if table:
                            break

        if not table:
            logger.warning("Could not find standings table for %s", conf_name)
            continue

        rows = table.find_all("tr")
        for row in rows:
            # Skip division header rows and column header rows
            if row.find("th", {"scope": "col"}) or row.get("class") == ["thead"]:
                continue

            cells = row.find_all(["th", "td"])
            if len(cells) < 3:
                continue

            # First cell is team name (th with data-stat="team_name")
            team_cell = cells[0]
            team_link = team_cell.find("a")
            if not team_link:
                continue
            team_name = team_link.get_text(strip=True)
            team_abbr = _team_abbr(team_name)
            if not team_abbr:
                continue

            # Find W, L, W/L% columns by data-stat attribute
            wins = 0
            losses = 0
            win_pct = 0.0

            for cell in cells:
                stat = cell.get("data-stat", "")
                text = cell.get_text(strip=True)
                if stat == "wins" and text:
                    wins = int(text)
                elif stat == "losses" and text:
                    losses = int(text)
                elif stat == "win_loss_pct" and text:
                    win_pct = float(text)

            # If data-stat approach didn't work, fall back to positional
            if wins == 0 and losses == 0 and len(cells) >= 4:
                try:
                    wins = int(cells[1].get_text(strip=True))
                    losses = int(cells[2].get_text(strip=True))
                    win_pct_text = cells[3].get_text(strip=True)
                    win_pct = float(win_pct_text) if win_pct_text else 0.0
                except (ValueError, IndexError):
                    pass

            standings.append({
                "team": team_abbr,
                "conference": conf_name,
                "wins": wins,
                "losses": losses,
                "win_pct": round(win_pct, 3),
            })

    logger.info("Fetched standings for %d teams", len(standings))
    return standings


def games_to_pairs(games):
    """Convert game dicts to (team_a, team_b, margin_a) tuples for SRS.

    Each game produces one tuple where team_a is the home team and
    margin_a is the home team's point differential.
    """
    pairs = []
    for g in games:
        margin = g["home_pts"] - g["away_pts"]
        pairs.append((g["home_team"], g["away_team"], margin))
    return pairs
