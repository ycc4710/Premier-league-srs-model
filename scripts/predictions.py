"""Game predictions and Monte Carlo season simulation using SRS ratings.

Prediction model:
  Expected margin = SRS_home - SRS_away
                  + HOME_ADVANTAGE         (~0.4 goals, data-driven)
                  + form_adjustment        (last 5 games, SRS-weighted, opponent quality matters)
                  + rest_adjustment        (non-linear fatigue curve)
                  + injury_adjustment      (FPL-data-driven player importance, not fixed by position)

  Win probability derived from normal CDF with ~1.2 goal std dev.
"""

import math
import logging
import requests
import numpy as np
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)

# ── Model constants ────────────────────────────────────────────────────────
HOME_COURT_ADVANTAGE = 0.4   # goals (overridden by data-driven value)
GAME_STD_DEV = 1.2           # goals
NUM_SIMULATIONS = 10000

# Factor weights
FORM_WEIGHT = 0.10       # max ~±0.5 goals
REST_WEIGHT = 0.06       # max ~±0.4 goals (applied to rest_score diff)
INJURY_WEIGHT = 0.12     # per normalized injury unit (capped)

# FPL API
FPL_API_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"

# FPL team name → our abbreviation
FPL_TEAM_MAP = {
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
    "Man City": "MCI",
    "Man Utd": "MNU",
    "Newcastle": "NEW",
    "Nott'm Forest": "NFO",
    "Sunderland": "SUN",
    "Spurs": "TOT",
    "West Ham": "WHU",
    "Wolves": "WOL",
}

# Only consider players worth £5.0m+ (FPL value in tenths = 50)
# to filter out squad fillers
MIN_PLAYER_VALUE = 50


# ── Core math ──────────────────────────────────────────────────────────────

def predict_margin(home_srs, away_srs, home_advantage=HOME_COURT_ADVANTAGE):
    return home_srs - away_srs + home_advantage


def win_probability(predicted_margin, std_dev=GAME_STD_DEV):
    return 0.5 * (1 + math.erf(predicted_margin / (std_dev * math.sqrt(2))))


# ── Factor 1: Form (SRS-weighted opponent quality) ─────────────────────────

def calculate_form(games, team, srs_ratings, n=5):
    """Calculate form score from last N completed games.

    Returns float roughly in [-1, +1].
    - Win=+1, Draw=0, Loss=-1 as base result
    - Weighted by recency: most recent game has highest weight
    - Weighted by opponent quality: beating a strong team (high SRS) scores more
      than beating a weak team; losing to a weak team penalises more

    Args:
        games: list of completed game dicts
        team: team abbreviation
        srs_ratings: dict of team -> {srs, ...} for opponent quality
        n: number of recent games to consider
    """
    team_games = []
    for g in games:
        if g["home_team"] == team:
            team_games.append(("home", g))
        elif g["away_team"] == team:
            team_games.append(("away", g))

    team_games.sort(key=lambda x: x[1]["date_parsed"], reverse=True)
    recent = team_games[:n]
    if not recent:
        return 0.0

    total, weight_sum = 0.0, 0.0
    for i, (side, g) in enumerate(recent):
        recency_weight = 1.0 / (i + 1)

        hp, ap = g["home_pts"], g["away_pts"]
        if side == "home":
            result = 1.0 if hp > ap else (0.0 if hp == ap else -1.0)
            opponent = g["away_team"]
        else:
            result = 1.0 if ap > hp else (0.0 if ap == hp else -1.0)
            opponent = g["home_team"]

        # Opponent quality weight: scale around 1.0
        # Strong opponent (SRS +2) → weight 1.4; weak opponent (SRS -2) → weight 0.6
        opp_srs = srs_ratings.get(opponent, {}).get("srs", 0.0)
        quality_weight = 1.0 + opp_srs * 0.2
        quality_weight = max(0.4, min(quality_weight, 2.0))  # clamp

        w = recency_weight * quality_weight
        total += result * w
        weight_sum += w

    return total / weight_sum if weight_sum else 0.0


# ── Factor 2: Rest (non-linear fatigue curve) ──────────────────────────────

def rest_score(days):
    """Convert rest days to a readiness score (0.0 = exhausted, 1.0 = fully rested).

    Non-linear: big difference between 3 and 4 days, tiny difference between 6 and 7.
    Based on typical football recovery research:
      - <3 days: severe fatigue
      - 3-5 days: rapid recovery zone
      - 5+ days: diminishing returns
    """
    if days <= 2:
        return 0.25
    elif days <= 3:
        return 0.45
    elif days <= 4:
        return 0.65
    elif days <= 5:
        return 0.80
    elif days <= 6:
        return 0.90
    else:
        return 1.0  # fully recovered, no benefit beyond 7 days


def days_rest(games, team, match_date):
    """Number of days since team's last game before match_date."""
    prior = [
        g for g in games
        if (g["home_team"] == team or g["away_team"] == team)
        and g["date_parsed"] < match_date
    ]
    if not prior:
        return 7  # assume normal rest if no prior game
    last = max(g["date_parsed"] for g in prior)
    delta = datetime.strptime(match_date, "%Y-%m-%d") - datetime.strptime(last, "%Y-%m-%d")
    return delta.days


# ── Factor 3: Injuries (FPL dynamic player importance) ────────────────────

def fetch_injury_data():
    """Fetch player availability from FPL API.

    Player importance is determined dynamically from FPL points-per-game
    relative to their own team's average — not by fixed position weights.
    This means:
      - A goalkeeper who is a team's best player gets high importance
      - A mediocre striker gets low importance even though FWD is usually key
      - Teams heavily reliant on one player are penalised more when he's out

    Returns:
        dict: team_abbr -> injury_impact_score (higher = worse injury situation)
        dict: team_abbr -> injury_detail (list of affected players for display)
    """
    try:
        resp = requests.get(FPL_API_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("Could not fetch FPL injury data: %s", e)
        return {}, {}

    # Build FPL team_id → abbr
    team_id_to_abbr = {}
    for team in data.get("teams", []):
        abbr = FPL_TEAM_MAP.get(team["name"])
        if abbr:
            team_id_to_abbr[team["id"]] = abbr

    # Group players by team, compute team average PPG for normalization
    team_players = defaultdict(list)
    for player in data.get("elements", []):
        team_id = player.get("team")
        abbr = team_id_to_abbr.get(team_id)
        if not abbr:
            continue
        value = player.get("now_cost", 0)
        if value < MIN_PLAYER_VALUE:
            continue
        ppg = float(player.get("points_per_game") or 0)
        team_players[abbr].append({
            "name": player.get("web_name", ""),
            "ppg": ppg,
            "status": player.get("status", "a"),
            "chance": player.get("chance_of_playing_next_round"),
            "value": value,
        })

    injury_scores = {}
    injury_details = {}

    for abbr, players in team_players.items():
        if not players:
            continue

        # Team average PPG (only players with actual minutes)
        active_ppg = [p["ppg"] for p in players if p["ppg"] > 0]
        team_avg_ppg = sum(active_ppg) / len(active_ppg) if active_ppg else 1.0
        team_max_ppg = max(active_ppg) if active_ppg else 1.0

        score = 0.0
        details = []

        for p in players:
            status = p["status"]
            if status == "a":
                continue

            # Player importance: how much above average is this player?
            # Normalized 0-1 where 1 = best player on the team
            importance = p["ppg"] / team_max_ppg if team_max_ppg > 0 else 0.5
            importance = max(0.1, importance)  # floor so even bench players count a little

            # Miss probability
            if status in ("i", "s"):
                miss_prob = 1.0
            elif status == "d":
                miss_prob = 1.0 - (p["chance"] / 100.0) if p["chance"] is not None else 0.5
            else:
                miss_prob = 0.3  # unknown status

            contribution = importance * miss_prob
            score += contribution

            if miss_prob > 0.2:
                details.append({
                    "name": p["name"],
                    "status": status,
                    "miss_prob": round(miss_prob, 2),
                    "importance": round(importance, 2),
                })

        injury_scores[abbr] = score
        injury_details[abbr] = sorted(details, key=lambda x: x["importance"], reverse=True)

    logger.info("FPL injury data: %d teams with absences", sum(1 for s in injury_scores.values() if s > 0))
    return injury_scores, injury_details


# ── Main prediction function ───────────────────────────────────────────────

def predict_games(upcoming_games, srs_ratings, league_home_advantage=HOME_COURT_ADVANTAGE,
                  team_hca=None, completed_games=None, injury_data=None):
    """Generate predictions with SRS + per-team HCA + form + rest + injury adjustments.

    Args:
        upcoming_games: list of dicts with home_team, away_team, date_parsed
        srs_ratings: dict mapping team abbr to {srs, mov, sos}
        league_home_advantage: fallback league-average HCA
        team_hca: dict of team -> Bayesian-shrunk home advantage
        completed_games: completed game dicts (for form + rest calc)
        injury_data: tuple of (scores_dict, details_dict) from fetch_injury_data()
    """
    if completed_games is None:
        completed_games = []
    if team_hca is None:
        team_hca = {}

    # Unpack injury data
    if injury_data and isinstance(injury_data, tuple):
        injury_scores, injury_details = injury_data
    elif isinstance(injury_data, dict):
        injury_scores, injury_details = injury_data, {}
    else:
        injury_scores, injury_details = {}, {}

    predictions = []
    for game in upcoming_games:
        home = game["home_team"]
        away = game["away_team"]
        match_date = game.get("date_parsed", "")

        home_srs = srs_ratings.get(home, {}).get("srs", 0.0)
        away_srs = srs_ratings.get(away, {}).get("srs", 0.0)

        # Per-team HCA: use home team's own shrunk value, fall back to league avg
        hca = team_hca.get(home, league_home_advantage)

        # Base SRS margin with team-specific HCA
        base = predict_margin(home_srs, away_srs, hca)

        # ── Form (SRS-weighted) ──
        home_form = calculate_form(completed_games, home, srs_ratings)
        away_form = calculate_form(completed_games, away, srs_ratings)
        form_adj = (home_form - away_form) * FORM_WEIGHT

        # ── Rest (non-linear) ──
        if match_date:
            hr = days_rest(completed_games, home, match_date)
            ar = days_rest(completed_games, away, match_date)
        else:
            hr = ar = 7
        rest_diff = rest_score(hr) - rest_score(ar)
        rest_adj = rest_diff * REST_WEIGHT

        # ── Injury ──
        home_inj = injury_scores.get(home, 0.0)
        away_inj = injury_scores.get(away, 0.0)
        inj_diff = max(min(away_inj - home_inj, 3.0), -3.0)
        inj_adj = inj_diff * INJURY_WEIGHT

        margin = base + form_adj + rest_adj + inj_adj
        home_win_prob = win_probability(margin)

        predictions.append({
            "date": game.get("date", ""),
            "date_parsed": match_date,
            "home_team": home,
            "away_team": away,
            "home_srs": round(home_srs, 2),
            "away_srs": round(away_srs, 2),
            "predicted_margin": round(margin, 2),
            "home_win_prob": round(home_win_prob, 3),
            "favored": home if margin >= 0 else away,
            "underdog": away if margin >= 0 else home,
            "spread": round(-abs(margin), 2),
            "adjustments": {
                "srs_base": round(base - hca, 2),
                "home_advantage": round(hca, 2),
                "home_advantage_raw": round(league_home_advantage, 2),
                "form": round(form_adj, 3),
                "rest": round(rest_adj, 3),
                "injury": round(inj_adj, 3),
                "home_form": round(home_form, 2),
                "away_form": round(away_form, 2),
                "home_rest_days": hr,
                "away_rest_days": ar,
                "home_rest_score": round(rest_score(hr), 2),
                "away_rest_score": round(rest_score(ar), 2),
                "home_injury_score": round(home_inj, 2),
                "away_injury_score": round(away_inj, 2),
                "home_injuries": injury_details.get(home, []),
                "away_injuries": injury_details.get(away, []),
            },
        })

    predictions.sort(key=lambda p: (p["date_parsed"], -abs(p["predicted_margin"])))
    return predictions


# ── Monte Carlo simulation ─────────────────────────────────────────────────

def monte_carlo_season(remaining_games, current_standings, srs_ratings,
                       num_simulations=NUM_SIMULATIONS):
    """Run Monte Carlo simulation of remaining EPL season."""
    if not remaining_games:
        results = {}
        for team, standing in current_standings.items():
            pts = standing.get("points", standing["wins"] * 3 + standing.get("draws", 0))
            results[team] = {
                "avg_points": float(pts),
                "points_range_low": pts,
                "points_range_high": pts,
                "title_pct": 0.0,
                "top4_pct": 0.0,
                "top6_pct": 0.0,
                "relegation_pct": 0.0,
            }
        return results

    teams = list(current_standings.keys())
    team_idx = {t: i for i, t in enumerate(teams)}
    n_teams = len(teams)

    game_probs = []
    for game in remaining_games:
        home, away = game["home_team"], game["away_team"]
        if home not in team_idx or away not in team_idx:
            continue
        home_srs = srs_ratings.get(home, {}).get("srs", 0.0)
        away_srs = srs_ratings.get(away, {}).get("srs", 0.0)
        margin = predict_margin(home_srs, away_srs)
        prob_home = win_probability(margin)
        draw_prob = 0.25
        game_probs.append((
            team_idx[home], team_idx[away],
            prob_home * (1 - draw_prob),
            (1 - prob_home) * (1 - draw_prob),
            draw_prob
        ))

    base_points = np.array([
        current_standings[t].get("points", current_standings[t]["wins"] * 3 + current_standings[t].get("draws", 0))
        for t in teams
    ], dtype=float)

    total_points = np.zeros((num_simulations, n_teams))
    title_counts = np.zeros(n_teams)
    top4_counts = np.zeros(n_teams)
    top6_counts = np.zeros(n_teams)
    relegation_counts = np.zeros(n_teams)

    rng = np.random.default_rng(seed=42)
    all_randoms = rng.random((num_simulations, len(game_probs)))

    for sim in range(num_simulations):
        sim_points = base_points.copy()
        for g_idx, (hi, ai, ph, pa, pd) in enumerate(game_probs):
            r = all_randoms[sim, g_idx]
            if r < ph:
                sim_points[hi] += 3
            elif r < ph + pd:
                sim_points[hi] += 1
                sim_points[ai] += 1
            else:
                sim_points[ai] += 3
        total_points[sim] = sim_points
        ranked = sorted(range(n_teams), key=lambda i: sim_points[i], reverse=True)
        title_counts[ranked[0]] += 1
        for i in ranked[:4]:
            top4_counts[i] += 1
        for i in ranked[:6]:
            top6_counts[i] += 1
        for i in ranked[-3:]:
            relegation_counts[i] += 1

    results = {}
    for i, team in enumerate(teams):
        pts_dist = total_points[:, i]
        results[team] = {
            "avg_points": round(float(np.mean(pts_dist)), 1),
            "points_range_low": int(np.percentile(pts_dist, 5)),
            "points_range_high": int(np.percentile(pts_dist, 95)),
            "title_pct": round(float(title_counts[i] / num_simulations * 100), 1),
            "top4_pct": round(float(top4_counts[i] / num_simulations * 100), 1),
            "top6_pct": round(float(top6_counts[i] / num_simulations * 100), 1),
            "relegation_pct": round(float(relegation_counts[i] / num_simulations * 100), 1),
        }

    return results