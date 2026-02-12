"""SRS (Simple Rating System) calculation for NBA teams.

SRS = Margin of Victory (MOV) + Strength of Schedule (SOS)

The system is solved via linear algebra: A * R = MOV, where A encodes
the schedule relationships between teams. An average team has SRS of 0.
"""

import numpy as np


def calculate_srs(game_results, teams):
    """Calculate SRS ratings using linear algebra (primary method).

    Args:
        game_results: list of (team_a, team_b, margin_a) tuples.
            margin_a is positive if team_a won by that many points.
        teams: list of team abbreviations to include in the calculation.

    Returns:
        dict mapping team abbreviation to {srs, mov, sos, games_played}.
    """
    n = len(teams)
    if n == 0:
        return {}

    team_idx = {team: i for i, team in enumerate(teams)}

    total_margin = np.zeros(n)
    games_played = np.zeros(n)
    matchup_counts = np.zeros((n, n))

    for team_a, team_b, margin in game_results:
        if team_a not in team_idx or team_b not in team_idx:
            continue
        i, j = team_idx[team_a], team_idx[team_b]
        total_margin[i] += margin
        total_margin[j] -= margin
        games_played[i] += 1
        games_played[j] += 1
        matchup_counts[i][j] += 1
        matchup_counts[j][i] += 1

    # Filter to only teams that have played at least 1 game
    active_mask = games_played > 0
    if not np.any(active_mask):
        return {team: {"srs": 0.0, "mov": 0.0, "sos": 0.0, "games_played": 0}
                for team in teams}

    # Compute MOV
    mov = np.zeros(n)
    mov[active_mask] = total_margin[active_mask] / games_played[active_mask]

    # Build coefficient matrix: A[i][i] = 1, A[i][j] = -matchups_ij / games_i
    A = np.eye(n)
    for i in range(n):
        if games_played[i] > 0:
            for j in range(n):
                if i != j:
                    A[i][j] = -matchup_counts[i][j] / games_played[i]

    try:
        srs_ratings = np.linalg.solve(A, mov)
    except np.linalg.LinAlgError:
        # Fall back to iterative method if matrix is singular
        return _calculate_srs_iterative(
            game_results, teams, total_margin, games_played, matchup_counts
        )

    # Normalize: force mean SRS = 0
    srs_ratings -= np.mean(srs_ratings)

    # SOS = SRS - MOV
    sos = srs_ratings - mov

    return {
        teams[i]: {
            "srs": round(float(srs_ratings[i]), 2),
            "mov": round(float(mov[i]), 2),
            "sos": round(float(sos[i]), 2),
            "games_played": int(games_played[i]),
        }
        for i in range(n)
    }


def _calculate_srs_iterative(game_results, teams, total_margin, games_played,
                              matchup_counts, max_iter=10000, tolerance=0.001):
    """Iterative SRS calculation as fallback.

    Used when the linear algebra approach fails (e.g., singular matrix
    early in the season when not all teams have played each other).
    """
    n = len(teams)
    team_idx = {team: i for i, team in enumerate(teams)}

    # Build opponent lists for each team
    opponents = {i: [] for i in range(n)}
    for team_a, team_b, _ in game_results:
        if team_a not in team_idx or team_b not in team_idx:
            continue
        i, j = team_idx[team_a], team_idx[team_b]
        opponents[i].append(j)
        opponents[j].append(i)

    mov = np.zeros(n)
    active = games_played > 0
    mov[active] = total_margin[active] / games_played[active]

    srs = mov.copy()

    for _ in range(max_iter):
        new_srs = np.zeros(n)
        for i in range(n):
            if opponents[i]:
                avg_opp_srs = np.mean([srs[j] for j in opponents[i]])
                new_srs[i] = mov[i] + avg_opp_srs
        new_srs -= np.mean(new_srs)

        if np.max(np.abs(new_srs - srs)) < tolerance:
            srs = new_srs
            break
        srs = new_srs

    sos = srs - mov

    return {
        teams[i]: {
            "srs": round(float(srs[i]), 2),
            "mov": round(float(mov[i]), 2),
            "sos": round(float(sos[i]), 2),
            "games_played": int(games_played[i]),
        }
        for i in range(n)
    }
