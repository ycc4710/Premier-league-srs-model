"""Fetch NBA game data and standings from Basketball-Reference.com."""

import logging
import time
from datetime import datetime, timedelta

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


def _parse_bref_date(date_str):
    """Parse Basketball-Reference date strings like 'Mon, Oct 28, 2025'."""
    date_str = date_str.strip()
    for fmt in ["%a, %b %d, %Y", "%B %d, %Y", "%b %d, %Y"]:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def _get_schedule_months(season_end_year):
    """Determine which months to scrape based on current date."""
    now = datetime.now()
    months = []
    for month in SCHEDULE_MONTHS:
        if month in ("october", "november", "december"):
            month_year = season_end_year - 1
        else:
            month_year = season_end_year

        month_num = {
            "october": 10, "november": 11, "december": 12,
            "january": 1, "february": 2, "march": 3, "april": 4,
        }[month]

        month_date = datetime(month_year, month_num, 1)
        if month_date <= now:
            months.append(month)

    return months


def _get_all_schedule_months():
    """Return all months of the regular season (for upcoming games too)."""
    return list(SCHEDULE_MONTHS)


def _parse_schedule_page(html, played_only=True):
    """Parse a Basketball-Reference schedule page.

    Args:
        html: Raw HTML of the page.
        played_only: If True, only return games with scores. If False,
                     return all games (including upcoming with no score).

    Returns:
        list of dicts with keys: date, home_team, away_team, home_pts, away_pts, played
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="schedule")
    if not table:
        return []

    tbody = table.find("tbody")
    if not tbody:
        return []

    games = []
    for row in tbody.find_all("tr"):
        if row.find("th", {"scope": "col"}):
            continue

        cells = row.find_all(["th", "td"])
        if len(cells) < 6:
            continue

        date_cell = cells[0]
        visitor_cell = cells[2]
        visitor_pts_cell = cells[3]
        home_cell = cells[4]
        home_pts_cell = cells[5]

        # Extract team names
        visitor_link = visitor_cell.find("a")
        home_link = home_cell.find("a")
        visitor_name = visitor_link.get_text(strip=True) if visitor_link else visitor_cell.get_text(strip=True)
        home_name = home_link.get_text(strip=True) if home_link else home_cell.get_text(strip=True)

        visitor_abbr = _team_abbr(visitor_name)
        home_abbr = _team_abbr(home_name)
        if not visitor_abbr or not home_abbr:
            continue

        game_date_str = date_cell.get_text(strip=True)
        game_date = _parse_bref_date(game_date_str)

        visitor_pts_text = visitor_pts_cell.get_text(strip=True)
        home_pts_text = home_pts_cell.get_text(strip=True)

        played = bool(visitor_pts_text and home_pts_text)

        if played_only and not played:
            continue

        try:
            visitor_pts = int(visitor_pts_text) if played else 0
            home_pts = int(home_pts_text) if played else 0
        except ValueError:
            continue

        games.append({
            "date": game_date_str,
            "date_parsed": game_date.strftime("%Y-%m-%d") if game_date else "",
            "home_team": home_abbr,
            "away_team": visitor_abbr,
            "home_pts": home_pts,
            "away_pts": visitor_pts,
            "played": played,
        })

    return games


def fetch_games(season_end_year=SEASON_END_YEAR):
    """Scrape completed game results from Basketball-Reference.

    Returns:
        list of dicts with keys: date, home_team, away_team, home_pts, away_pts
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

        games = _parse_schedule_page(html, played_only=True)
        all_games.extend(games)

    logger.info("Fetched %d completed games total", len(all_games))
    return all_games


def fetch_upcoming_games(season_end_year=SEASON_END_YEAR, days_ahead=7):
    """Scrape upcoming (unplayed) games for the next N days.

    Returns:
        list of dicts with keys: date, date_parsed, home_team, away_team
    """
    now = datetime.now()
    cutoff = now + timedelta(days=days_ahead)
    months = _get_all_schedule_months()
    upcoming = []

    for month in months:
        if month in ("october", "november", "december"):
            month_year = season_end_year - 1
        else:
            month_year = season_end_year

        month_num = {
            "october": 10, "november": 11, "december": 12,
            "january": 1, "february": 2, "march": 3, "april": 4,
        }[month]

        # Only fetch months that could contain upcoming games
        month_start = datetime(month_year, month_num, 1)
        if month_num == 12:
            month_end = datetime(month_year + 1, 1, 1)
        else:
            month_end = datetime(month_year, month_num + 1, 1)

        if month_end < now or month_start > cutoff:
            continue

        url = SCHEDULE_URL.format(year=season_end_year, month=month)
        logger.info("Fetching upcoming schedule: %s", url)

        try:
            html = _get_page(url)
        except requests.RequestException as e:
            logger.warning("Failed to fetch %s: %s", month, e)
            continue

        games = _parse_schedule_page(html, played_only=False)
        for g in games:
            if not g["played"] and g["date_parsed"]:
                game_dt = datetime.strptime(g["date_parsed"], "%Y-%m-%d")
                if now.date() <= game_dt.date() <= cutoff.date():
                    upcoming.append({
                        "date": g["date"],
                        "date_parsed": g["date_parsed"],
                        "home_team": g["home_team"],
                        "away_team": g["away_team"],
                    })

    logger.info("Found %d upcoming games in next %d days", len(upcoming), days_ahead)
    return upcoming


def fetch_remaining_games(season_end_year=SEASON_END_YEAR):
    """Scrape all remaining (unplayed) games in the season for Monte Carlo.

    Returns:
        list of dicts with keys: date, date_parsed, home_team, away_team
    """
    now = datetime.now()
    months = _get_all_schedule_months()
    remaining = []

    for month in months:
        if month in ("october", "november", "december"):
            month_year = season_end_year - 1
        else:
            month_year = season_end_year

        month_num = {
            "october": 10, "november": 11, "december": 12,
            "january": 1, "february": 2, "march": 3, "april": 4,
        }[month]

        # Skip months entirely in the past
        if month_num == 12:
            month_end = datetime(month_year + 1, 1, 1)
        else:
            month_end = datetime(month_year, month_num + 1, 1)

        if month_end < now:
            continue

        url = SCHEDULE_URL.format(year=season_end_year, month=month)
        logger.info("Fetching full schedule for remaining: %s", url)

        try:
            html = _get_page(url)
        except requests.RequestException as e:
            logger.warning("Failed to fetch %s: %s", month, e)
            continue

        games = _parse_schedule_page(html, played_only=False)
        for g in games:
            if not g["played"]:
                remaining.append({
                    "date": g["date"],
                    "date_parsed": g["date_parsed"],
                    "home_team": g["home_team"],
                    "away_team": g["away_team"],
                })

    logger.info("Found %d remaining games in season", len(remaining))
    return remaining


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

    for conf_id, conf_name in [
        ("confs_standings_E", "East"),
        ("confs_standings_W", "West"),
    ]:
        table = soup.find("table", id=conf_id)

        if not table:
            for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
                if conf_id in str(comment):
                    comment_soup = BeautifulSoup(str(comment), "lxml")
                    table = comment_soup.find("table", id=conf_id)
                    if table:
                        break

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
            if row.find("th", {"scope": "col"}) or row.get("class") == ["thead"]:
                continue

            cells = row.find_all(["th", "td"])
            if len(cells) < 3:
                continue

            team_cell = cells[0]
            team_link = team_cell.find("a")
            if not team_link:
                continue
            team_name = team_link.get_text(strip=True)
            team_abbr = _team_abbr(team_name)
            if not team_abbr:
                continue

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
    """Convert game dicts to (team_a, team_b, margin_a) tuples for SRS."""
    pairs = []
    for g in games:
        margin = g["home_pts"] - g["away_pts"]
        pairs.append((g["home_team"], g["away_team"], margin))
    return pairs
