"""Tests for the SRS calculation algorithm."""

import pytest
from scripts.calculate_srs import calculate_srs, _calculate_srs_iterative
import numpy as np


class TestCalculateSRS:
    """Test SRS calculation with known scenarios."""

    def test_two_teams_simple(self):
        """Two teams, one beats the other every time by 10."""
        teams = ["A", "B"]
        # A beats B by 10, three times
        games = [("A", "B", 10), ("A", "B", 10), ("A", "B", 10)]
        result = calculate_srs(games, teams)

        assert result["A"]["srs"] > 0
        assert result["B"]["srs"] < 0
        # MOV should be +10 and -10
        assert result["A"]["mov"] == 10.0
        assert result["B"]["mov"] == -10.0
        # SRS should sum to 0 (normalized)
        total_srs = result["A"]["srs"] + result["B"]["srs"]
        assert abs(total_srs) < 0.01

    def test_four_teams_round_robin(self):
        """Four teams in a round robin with known margins."""
        teams = ["A", "B", "C", "D"]
        # A beats everyone by 10 -> MOV = +10
        # B beats C and D by 5 each, loses to A by 10 -> MOV = (5+5-10)/3 = 0
        # C beats D by 5, loses to A by 10, loses to B by 5 -> MOV = (5-10-5)/3 = -10/3
        # D loses to everyone -> MOV depends on margins
        games = [
            ("A", "B", 10),  # A beats B by 10
            ("A", "C", 10),  # A beats C by 10
            ("A", "D", 10),  # A beats D by 10
            ("B", "C", 5),   # B beats C by 5
            ("B", "D", 5),   # B beats D by 5
            ("C", "D", 5),   # C beats D by 5
        ]
        result = calculate_srs(games, teams)

        # A should be ranked highest, D lowest
        assert result["A"]["srs"] > result["B"]["srs"]
        assert result["B"]["srs"] > result["C"]["srs"]
        assert result["C"]["srs"] > result["D"]["srs"]

        # Mean SRS should be 0
        mean_srs = sum(result[t]["srs"] for t in teams) / len(teams)
        assert abs(mean_srs) < 0.01

        # Games played should be 3 for each team
        for t in teams:
            assert result[t]["games_played"] == 3

    def test_srs_equals_mov_plus_sos(self):
        """Verify SRS = MOV + SOS for every team."""
        teams = ["A", "B", "C", "D"]
        games = [
            ("A", "B", 15),
            ("A", "C", 5),
            ("B", "D", 10),
            ("C", "D", -5),  # D beats C by 5
            ("A", "D", 20),
            ("B", "C", 3),
        ]
        result = calculate_srs(games, teams)

        for t in teams:
            computed_srs = result[t]["mov"] + result[t]["sos"]
            assert abs(result[t]["srs"] - computed_srs) < 0.02, \
                f"SRS != MOV + SOS for team {t}: {result[t]}"

    def test_equal_teams(self):
        """All games are ties effectively (alternating wins by same margin)."""
        teams = ["A", "B", "C"]
        games = [
            ("A", "B", 5),
            ("B", "A", 5),   # B beats A by 5
            ("A", "C", 5),
            ("C", "A", 5),
            ("B", "C", 5),
            ("C", "B", 5),
        ]
        result = calculate_srs(games, teams)

        # All teams should have SRS near 0 (everyone is equal)
        for t in teams:
            assert abs(result[t]["srs"]) < 0.1
            assert abs(result[t]["mov"]) < 0.1

    def test_empty_games(self):
        """No games produces zero ratings."""
        teams = ["A", "B", "C"]
        result = calculate_srs([], teams)
        for t in teams:
            assert result[t]["srs"] == 0
            assert result[t]["games_played"] == 0

    def test_empty_teams(self):
        """Empty teams list returns empty dict."""
        result = calculate_srs([("A", "B", 10)], [])
        assert result == {}

    def test_unknown_team_in_games_ignored(self):
        """Games with teams not in the teams list are skipped."""
        teams = ["A", "B"]
        games = [
            ("A", "B", 10),
            ("A", "X", 5),  # X not in teams list, should be ignored
        ]
        result = calculate_srs(games, teams)
        assert result["A"]["games_played"] == 1
        assert result["B"]["games_played"] == 1

    def test_strength_of_schedule(self):
        """Team that plays strong opponents should have higher SOS."""
        teams = ["STRONG", "WEAK", "TEST_A", "TEST_B"]
        # STRONG beats everyone by 20
        # WEAK loses to everyone by 20
        # TEST_A only plays STRONG (has hard schedule)
        # TEST_B only plays WEAK (has easy schedule)
        games = [
            ("STRONG", "WEAK", 20),
            ("STRONG", "WEAK", 20),
            ("STRONG", "TEST_A", 10),   # STRONG beats TEST_A by 10
            ("TEST_B", "WEAK", 10),     # TEST_B beats WEAK by 10
        ]
        result = calculate_srs(games, teams)

        # TEST_A plays STRONG -> should have higher SOS
        # TEST_B plays WEAK -> should have lower SOS
        assert result["TEST_A"]["sos"] > result["TEST_B"]["sos"]

    def test_large_number_of_games(self):
        """SRS should handle a realistic number of teams and games."""
        np.random.seed(42)
        teams = [f"T{i:02d}" for i in range(30)]
        games = []
        # Each team plays ~80 games (like NBA season)
        for _ in range(1200):
            i, j = np.random.choice(30, 2, replace=False)
            # Better teams (lower index) tend to win
            expected_margin = (j - i) * 0.5  # simple skill model
            actual_margin = expected_margin + np.random.normal(0, 10)
            games.append((teams[i], teams[j], round(actual_margin, 1)))

        result = calculate_srs(games, teams)

        # All 30 teams should have results
        assert len(result) == 30

        # Mean SRS should be ~0
        mean_srs = sum(result[t]["srs"] for t in teams) / 30
        assert abs(mean_srs) < 0.1

        # Best team (T00) should generally have highest SRS
        srs_sorted = sorted(teams, key=lambda t: result[t]["srs"], reverse=True)
        # T00 should be in top 5
        assert "T00" in srs_sorted[:5]


class TestIterativeMethod:
    """Test the iterative fallback method."""

    def test_matches_linalg(self):
        """Iterative method should produce similar results to linear algebra."""
        teams = ["A", "B", "C", "D"]
        games = [
            ("A", "B", 10),
            ("A", "C", 5),
            ("B", "D", 10),
            ("C", "D", -5),
            ("A", "D", 20),
            ("B", "C", 3),
        ]
        result_linalg = calculate_srs(games, teams)

        # Use iterative directly
        total_margin = np.zeros(4)
        games_played = np.zeros(4)
        matchup_counts = np.zeros((4, 4))
        team_idx = {t: i for i, t in enumerate(teams)}

        for ta, tb, m in games:
            i, j = team_idx[ta], team_idx[tb]
            total_margin[i] += m
            total_margin[j] -= m
            games_played[i] += 1
            games_played[j] += 1
            matchup_counts[i][j] += 1
            matchup_counts[j][i] += 1

        result_iter = _calculate_srs_iterative(
            games, teams, total_margin, games_played, matchup_counts
        )

        for t in teams:
            assert abs(result_linalg[t]["srs"] - result_iter[t]["srs"]) < 0.1, \
                f"SRS mismatch for {t}: linalg={result_linalg[t]['srs']}, iter={result_iter[t]['srs']}"
