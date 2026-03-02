"""Configuration for EPL SRS ratings scraper and calculator."""

import os

# Current EPL season
SEASON = "2025-2026"
SEASON_DISPLAY = "2025-26"

# Output path for generated data
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(BASE_DIR, "site", "data", "srs_data.json")

# Request delay between scraping pages (seconds) to respect rate limits
REQUEST_DELAY = 4.0

# User-Agent for HTTP requests
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# FBref URL templates
SCORES_URL = (
    f"https://fbref.com/en/comps/9/{SEASON}/schedule/"
    f"{SEASON}-Premier-League-Scores-and-Fixtures"
)
STANDINGS_URL = (
    f"https://fbref.com/en/comps/9/{SEASON}/{SEASON}-Premier-League-Stats"
)

# FBref full team name -> abbreviation
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

ABBR_TO_TEAM_NAME = {v: k for k, v in TEAM_NAME_TO_ABBR.items()}

ALL_TEAMS = sorted(TEAM_NAME_TO_ABBR.values())

# EPL has no conferences — all teams in one group
EASTERN_CONFERENCE = set()   # kept for compatibility, unused
WESTERN_CONFERENCE = set()   # kept for compatibility, unused

# Premier League clubs don't have official divisions,
# but we group them geographically for display purposes
DIVISIONS = {
    "London": ["ARS", "BRE", "CHE", "CRY", "FUL", "TOT", "WHU"],
    "Midlands": ["AVL", "LEI", "NFO", "WOL"],
    "North West": ["LIV", "MCI", "MNU", "EVE"],
    "Other": ["BHA", "BOU", "IPS", "NEW", "SOU"],
}

TEAM_TO_DIVISION = {}
for _div, _teams in DIVISIONS.items():
    for _team in _teams:
        TEAM_TO_DIVISION[_team] = _div

# Logo URLs — using Wikipedia Commons Wikimedia SVGs (freely available)
# Format: https://upload.wikimedia.org/wikipedia/en/thumb/{path}
# We store a simple slug used in the frontend to build URLs.
# You can replace these with whichever CDN/source your frontend uses.
TEAM_LOGO_IDS = {
    "ARS": "arsenal",
    "AVL": "aston_villa",
    "BOU": "bournemouth",
    "BRE": "brentford",
    "BHA": "brighton",
    "CHE": "chelsea",
    "CRY": "crystal_palace",
    "EVE": "everton",
    "FUL": "fulham",
    "IPS": "ipswich",
    "LEI": "leicester",
    "LIV": "liverpool",
    "MCI": "man_city",
    "MNU": "man_utd",
    "NEW": "newcastle",
    "NFO": "nott_forest",
    "SOU": "southampton",
    "TOT": "tottenham",
    "WHU": "west_ham",
    "WOL": "wolves",
}