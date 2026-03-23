"""Fetch EPL game data, standings, and xG from football-data.org + Understat."""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta

import aiohttp
import requests
import understat
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY", "")
if not API_KEY:
    raise RuntimeError(
        "Missing API key. Please create a .env file in the project root with:\n"
        "FOOTBALL_DATA_API_KEY=your_token_here"
    )

BASE_URL = "https://api.football-data.org/v4"
COMPETITION = "PL"
SEASON_YEAR = 2025          # 2025 = 2025-26 season
UNDERSTAT_SEASON = "2025"   # Understat uses string year
REQUEST_DELAY = 1

logger = logging.getLogger(__name__)

HEADERS = {"X-Auth-Token": API_KEY}

# football-data.org team name → abbreviation
TEAM_NAME_TO_ABBR = {
    "Arsenal FC": "ARS",
    "Aston Villa FC": "AVL",
    "AFC Bournemouth": "BOU",
    "Brentford FC": "BRE",
    "Brighton & Hove Albion FC": "BHA",
    "Burnley FC": "BUR",
    "Chelsea FC": "CHE",
    "Crystal Palace FC": "CRY",
    "Everton FC": "EVE",
    "Fulham FC": "FUL",
    "Leeds United FC": "LEE",
    "Liverpool FC": "LIV",
    "Manchester City FC": "MCI",
    "Manchester United FC": "MNU",
    "Newcastle United FC": "NEW",
    "Nottingham Forest FC": "NFO",
    "Sunderland AFC": "SUN",
    "Tottenham Hotspur FC": "TOT",
    "West Ham United FC": "WHU",
    "Wolverhampton Wanderers FC": "WOL",
}

# Understat uses shorter names
UNDERSTAT_NAME_TO_ABBR = {
    "Arsenal": "ARS",
    "Aston Villa": "AVL",
    "Bournemouth": "BOU",
    "Brentford": "BRE",
    "Brighton": "BHA",
    "Burnley": "BUR",
    "Chelsea": "CHE",
    "Crystal Palace": "CRY",
    "Everton": "EVE",
    "Fulham": "FUL",
    "Leeds": "LEE",
    "Liverpool": "LIV",
    "Manchester City": "MCI",
    "Manchester United": "MNU",
    "Newcastle United": "NEW",
    "Nottingham Forest": "NFO",
    "Sunderland": "SUN",
    "Tottenham": "TOT",
    "West Ham": "WHU",
    "Wolves": "WOL",
}

ABBR_TO_TEAM_NAME = {v: k for k, v in TEAM_NAME_TO_ABBR.items()}


# ── football-data.org helpers ─────────────────────────────────────────────

def _team_abbr(name):
    name = name.strip()
    if name in TEAM_NAME_TO_ABBR:
        return TEAM_NAME_TO_ABBR[name]
    for full_name, abbr in TEAM_NAME_TO_ABBR.items():
        if name in full_name or full_name in name:
            return abbr
    logger.warning("Unknown team name: %s", name)
    return None


def _get(endpoint, params=None):
    url = f"{BASE_URL}{endpoint}"
    response = requests.get(url, headers=HEADERS, params=params, timeout=30)
    response.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return response.json()


# ── football-data.org fetch functions ────────────────────────────────────

def fetch_games():
    """Fetch all completed EPL matches this season."""
    logger.info("Fetching EPL results from football-data.org")
    data = _get(f"/competitions/{COMPETITION}/matches", params={
        "season": SEASON_YEAR,
        "status": "FINISHED",
    })
    games = []
    for match in data.get("matches", []):
        home_abbr = _team_abbr(match["homeTeam"]["name"])
        away_abbr = _team_abbr(match["awayTeam"]["name"])
        if not home_abbr or not away_abbr:
            continue
        score = match.get("score", {})
        full_time = score.get("fullTime", {})
        home_pts = full_time.get("home")
        away_pts = full_time.get("away")
        if home_pts is None or away_pts is None:
            continue
        date_str = match["utcDate"][:10]
        games.append({
            "date": date_str,
            "date_parsed": date_str,
            "home_team": home_abbr,
            "away_team": away_abbr,
            "home_pts": home_pts,
            "away_pts": away_pts,
            "played": True,
        })
    logger.info("Fetched %d completed matches", len(games))
    return games


def fetch_upcoming_games(days_ahead=7):
    """Fetch upcoming EPL matches in the next N days."""
    now = datetime.now()
    cutoff = now + timedelta(days=days_ahead)
    logger.info("Fetching upcoming EPL fixtures from football-data.org")
    data = _get(f"/competitions/{COMPETITION}/matches", params={
        "season": SEASON_YEAR,
        "status": "SCHEDULED",
        "dateFrom": now.strftime("%Y-%m-%d"),
        "dateTo": cutoff.strftime("%Y-%m-%d"),
    })
    upcoming = []
    for match in data.get("matches", []):
        home_abbr = _team_abbr(match["homeTeam"]["name"])
        away_abbr = _team_abbr(match["awayTeam"]["name"])
        if not home_abbr or not away_abbr:
            continue
        upcoming.append({
            "date": match["utcDate"][:10],
            "date_parsed": match["utcDate"][:10],
            "home_team": home_abbr,
            "away_team": away_abbr,
        })
    logger.info("Found %d upcoming matches in next %d days", len(upcoming), days_ahead)
    return upcoming


def fetch_remaining_games():
    """Fetch all remaining EPL matches this season for Monte Carlo."""
    logger.info("Fetching remaining EPL fixtures from football-data.org")
    data = _get(f"/competitions/{COMPETITION}/matches", params={
        "season": SEASON_YEAR,
        "status": "SCHEDULED",
    })
    remaining = []
    for match in data.get("matches", []):
        home_abbr = _team_abbr(match["homeTeam"]["name"])
        away_abbr = _team_abbr(match["awayTeam"]["name"])
        if not home_abbr or not away_abbr:
            continue
        remaining.append({
            "date": match["utcDate"][:10],
            "date_parsed": match["utcDate"][:10],
            "home_team": home_abbr,
            "away_team": away_abbr,
        })
    logger.info("Found %d remaining matches this season", len(remaining))
    return remaining


def fetch_standings():
    """Fetch current EPL standings from football-data.org."""
    logger.info("Fetching EPL standings from football-data.org")
    data = _get(f"/competitions/{COMPETITION}/standings", params={
        "season": SEASON_YEAR,
    })
    standings = []
    for table in data.get("standings", []):
        if table.get("type") != "TOTAL":
            continue
        for row in table.get("table", []):
            team_abbr = _team_abbr(row["team"]["name"])
            if not team_abbr:
                continue
            won = row.get("won", 0)
            draw = row.get("draw", 0)
            lost = row.get("lost", 0)
            played = row.get("playedGames", won + draw + lost)
            standings.append({
                "team": team_abbr,
                "conference": "EPL",
                "wins": won,
                "draws": draw,
                "losses": lost,
                "win_pct": round(won / played, 3) if played else 0.0,
            })
    logger.info("Fetched standings for %d teams", len(standings))
    return standings


def games_to_pairs(games):
    """Convert game dicts to (team_a, team_b, margin_a) tuples for SRS."""
    return [(g["home_team"], g["away_team"], g["home_pts"] - g["away_pts"]) for g in games]


# ── Understat xG fetch ────────────────────────────────────────────────────

async def _fetch_xg_async():
    async with aiohttp.ClientSession() as session:
        client = understat.Understat(session)
        return await client.get_league_results("epl", UNDERSTAT_SEASON)


def fetch_xg_data():
    """Fetch completed EPL match xG data from Understat.

    Returns:
        dict mapping (home_abbr, away_abbr, date_str) -> {home_xg, away_xg}
        Returns empty dict on failure — caller handles gracefully.
    """
    logger.info("Fetching xG data from Understat (season %s)", UNDERSTAT_SEASON)
    try:
        matches = asyncio.run(_fetch_xg_async())
    except Exception as e:
        logger.warning("Failed to fetch xG data from Understat: %s", e)
        return {}

    xg_map = {}
    skipped = 0
    for m in matches:
        home_name = m.get("h", {}).get("title", "")
        away_name = m.get("a", {}).get("title", "")
        home_abbr = UNDERSTAT_NAME_TO_ABBR.get(home_name)
        away_abbr = UNDERSTAT_NAME_TO_ABBR.get(away_name)

        if not home_abbr or not away_abbr:
            skipped += 1
            continue

        try:
            home_xg = float(m.get("xG", {}).get("h", 0) or 0)
            away_xg = float(m.get("xG", {}).get("a", 0) or 0)
        except (TypeError, ValueError):
            skipped += 1
            continue

        date_str = str(m.get("datetime", ""))[:10]
        xg_map[(home_abbr, away_abbr, date_str)] = {
            "home_xg": home_xg,
            "away_xg": away_xg,
        }

    logger.info("Understat xG: %d matches loaded, %d skipped", len(xg_map), skipped)
    return xg_map
