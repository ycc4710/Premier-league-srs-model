"""Tests for data fetching and parsing utilities."""

from scripts.fetch_data import games_to_pairs, _team_abbr


class TestGamesToPairs:
    """Test conversion of game dicts to SRS input pairs."""

    def test_basic_conversion(self):
        games = [
            {"date": "Mon, Oct 28, 2025", "home_team": "BOS", "away_team": "NYK",
             "home_pts": 110, "away_pts": 100},
            {"date": "Mon, Oct 28, 2025", "home_team": "LAL", "away_team": "GSW",
             "home_pts": 95, "away_pts": 105},
        ]
        pairs = games_to_pairs(games)

        assert len(pairs) == 2
        # First game: BOS home win by 10
        assert pairs[0] == ("BOS", "NYK", 10)
        # Second game: LAL home loss by 10
        assert pairs[1] == ("LAL", "GSW", -10)

    def test_empty_games(self):
        assert games_to_pairs([]) == []


class TestTeamAbbr:
    """Test team name to abbreviation mapping."""

    def test_known_teams(self):
        assert _team_abbr("Boston Celtics") == "BOS"
        assert _team_abbr("Los Angeles Lakers") == "LAL"
        assert _team_abbr("Golden State Warriors") == "GSW"
        assert _team_abbr("Philadelphia 76ers") == "PHI"

    def test_whitespace_handling(self):
        assert _team_abbr("  Boston Celtics  ") == "BOS"

    def test_unknown_team(self):
        assert _team_abbr("Unknown Team XYZ") is None
