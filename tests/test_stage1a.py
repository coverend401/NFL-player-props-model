"""Stage 1A regression tests. Run: python -m unittest discover -s tests -v."""

import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from scripts.build_features import STAT_COLS, AUX_STAT_COLS, build_player_features
from scripts.forecast_features import (
    player_features,
    upcoming_player_state,
    completed_history,
    pregame_eligible,
    observation_status,
    schedule_times,
)
from scripts.build_slate import (
    build_slate,
    get_upcoming_week,
    latest_team_defense,
    compute_top_picks,
)
from scripts.train_all_markets import prepare_dataset, coverage_report
from pricing import price_prop


def observations(values=(10.0, 0.0, 30.0, 90.0), weeks=(1, 2, 4, 5), seasons=None):
    rows = []
    for i, (value, week) in enumerate(zip(values, weeks)):
        row = dict(
            player_id="p",
            player_display_name="Player",
            position="QB",
            team="A",
            opponent_team="B",
            season=2025 if seasons is None else seasons[i],
            week=week,
            season_type="REG",
            game_id=f"g{i}",
            offense_pct=1.0,
        )
        for c in STAT_COLS + AUX_STAT_COLS:
            row.setdefault(c, value)
        rows.append(row)
    return pd.DataFrame(rows)


def schedule():
    rows = []
    for i, (week, date) in enumerate(
        [
            (1, "2025-09-07"),
            (2, "2025-09-14"),
            (4, "2025-09-28"),
            (5, "2025-10-05"),
            (6, "2025-10-12"),
        ]
    ):
        rows.append(
            dict(
                game_id=f"g{i}",
                season=2025,
                week=week,
                game_type="REG",
                gameday=date,
                gametime="13:00",
                home_team="A",
                away_team="B",
                home_score=20 if i < 4 else np.nan,
                away_score=10 if i < 4 else np.nan,
                spread_line=3.0,
                total_line=43.0,
                roof="outdoors",
                context_available_at="2024-01-01T00:00:00Z",
            )
        )
    return pd.DataFrame(rows)


class HistoryTests(unittest.TestCase):
    def test_manual_historical_and_inclusive_with_bye_and_zero(self):
        h = observations()
        old = player_features(h, STAT_COLS, AUX_STAT_COLS)
        self.assertAlmostEqual(old.iloc[3].passing_yards_last3_avg, 40 / 3)
        self.assertEqual(old.iloc[3].games_played_prior, 3)
        live = upcoming_player_state(h, STAT_COLS, AUX_STAT_COLS).iloc[0]
        self.assertEqual(live.passing_yards_last3_avg, 40.0)
        self.assertEqual(live.games_played_prior, 4)
        self.assertEqual(len(h), 4)  # bye is not a manufactured zero game

    def test_no_offensive_snaps_do_not_become_zero_history_games(self):
        h = observations()
        h.loc[2, "offense_pct"] = 0.0
        h.loc[2, "passing_yards"] = 0.0
        d = player_features(h, STAT_COLS, AUX_STAT_COLS)
        self.assertEqual(d.iloc[3].passing_yards_last3_avg, 5.0)
        self.assertEqual(d.iloc[3].games_played_prior, 2)
        self.assertEqual(d.iloc[2].passing_yards_last3_avg, 5.0)

    def test_season_boundary_includes_previous_season(self):
        h = observations(weeks=(17, 18, 1, 2), seasons=(2024, 2024, 2025, 2025))
        d = player_features(h, STAT_COLS, AUX_STAT_COLS)
        self.assertEqual(d.iloc[2].passing_yards_season_avg, 5.0)
        self.assertEqual(d.iloc[2].games_played_prior, 2)

    def test_unknown_outcome_not_zero_or_replaced_by_old_game(self):
        h = observations()
        h.loc[2, "passing_yards"] = np.nan
        d = player_features(h, STAT_COLS, AUX_STAT_COLS)
        self.assertTrue(pd.isna(d.iloc[3].passing_yards_last3_avg))
        live = upcoming_player_state(h, STAT_COLS, AUX_STAT_COLS)
        self.assertTrue(pd.isna(live.iloc[0].passing_yards_last3_avg))
        self.assertTrue(pd.isna(h.loc[2, "passing_yards"]))

    def test_current_and_future_outcomes_do_not_change_historical_features(self):
        h = observations()
        a = player_features(h, STAT_COLS, AUX_STAT_COLS)
        h.loc[2:, "passing_yards"] = 99999
        b = player_features(h, STAT_COLS, AUX_STAT_COLS)
        self.assertEqual(
            a.iloc[2].passing_yards_last3_avg, b.iloc[2].passing_yards_last3_avg
        )

    def test_cutoff_blocks_future_and_unfinished_games(self):
        h = observations()
        s = schedule()
        cut = pd.Timestamp("2025-09-29T02:00Z")
        before = completed_history(h, s, cut)
        self.assertEqual(before.week.tolist(), [1, 2, 4])
        h.loc[h.week == 5, "passing_yards"] = 99999
        pd.testing.assert_frame_equal(before, completed_history(h, s, cut))
        s.loc[s.week == 4, "home_score"] = np.nan
        self.assertEqual(completed_history(h, s, cut).week.tolist(), [1, 2])

    def test_strict_completion_cutoff_and_explicit_availability(self):
        s = schedule_times(schedule())
        cut = s.iloc[0].completed_at
        self.assertTrue(completed_history(observations(), s, cut).empty)
        s["stats_available_at"] = s.completed_at + pd.Timedelta(days=1)
        self.assertTrue(
            completed_history(observations(), s, cut + pd.Timedelta(hours=1)).empty
        )
        with self.assertRaises(ValueError):
            completed_history(observations(), s, cut, cut + pd.Timedelta(days=1))

    def test_upcoming_excludes_started_and_completed_games(self):
        s = schedule()
        s.loc[4, "home_score"] = np.nan
        extra = s.iloc[4].copy()
        extra["game_id"] = "earlier"
        extra["gameday"] = "2025-10-09"
        s = pd.concat([s, pd.DataFrame([extra])], ignore_index=True)
        _, games = get_upcoming_week(s, pd.Timestamp("2025-10-11T00:00Z"))
        self.assertEqual(games.game_id.tolist(), ["g4"])

    def test_historical_fixture_selection_ignores_future_known_results(self):
        s = schedule()
        # Week 4 is already scored in today's file but was upcoming at cutoff.
        week, games = get_upcoming_week(s, pd.Timestamp("2025-09-20T00:00Z"))
        self.assertEqual(week, 4)
        self.assertEqual(games.game_id.tolist(), ["g2"])

    def test_defense_includes_latest_game_and_leaves_all_missing_unknown(self):
        h = observations()
        d = latest_team_defense(h)
        self.assertEqual(d.loc["B", "opp_passing_yards_allowed_season_avg"], 32.5)
        h["passing_yards"] = np.nan
        self.assertTrue(
            pd.isna(
                latest_team_defense(h).loc["B", "opp_passing_yards_allowed_season_avg"]
            )
        )

    def test_team_totals_are_not_multiplied_by_player_count(self):
        h = observations()
        for c in STAT_COLS:
            h[f"team_total_{c}"] = 123.0
        other = h.copy()
        other["player_id"] = "other"
        h = pd.concat([h, other], ignore_index=True)
        result = latest_team_defense(h)
        self.assertEqual(result.loc["B", "opp_passing_yards_allowed_season_avg"], 123.0)

    def test_feature_pipeline_adds_participation_without_inventing_outcomes(self):
        h = observations()
        aux = h[
            [
                "player_id",
                "season",
                "week",
                "game_id",
                "season_type",
                "team",
                "opponent_team",
                "position",
                "player_display_name",
            ]
        ].copy()
        for c in AUX_STAT_COLS:
            if c not in h or c not in [
                "target_share",
                "air_yards_share",
                "wopr",
                "passing_epa",
                "rushing_epa",
                "receiving_epa",
            ]:
                aux[c] = 1.0
        missing = aux.iloc[-1].copy()
        missing["player_id"] = "missing"
        aux = pd.concat([aux, pd.DataFrame([missing])], ignore_index=True)
        from scripts.build_slate import build_game_context_for_week

        context = []
        for _, g in schedule().iterrows():
            c = build_game_context_for_week(pd.DataFrame([g])).reset_index()
            c["season"] = g.season
            c["week"] = g.week
            c["opponent_team"] = c.team.map({"A": "B", "B": "A"})
            context.append(c)
        d = build_player_features(
            h, aux=aux, game_context=pd.concat(context), schedule=schedule()
        )
        added = d[d.player_id == "missing"].iloc[0]
        self.assertFalse(added.stats_observed)
        self.assertTrue(pd.isna(added.passing_yards))
        self.assertEqual(added.observation_status, "participated")


class EligibilityTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame(
            dict(
                position=["QB"] * 5,
                games_played_prior=[4] * 5,
                offense_pct_last3_avg=[1.0] * 5,
                offense_pct=[1.0, 1.0, 0.0, np.nan, 1.0],
                attempts=[0.0, 20.0, 0.0, np.nan, np.nan],
                x=[1.0] * 5,
            )
        )

    def test_zero_opportunity_retained_missing_and_no_snap_separate(self):
        d = self.frame()
        config = {"positions": ["QB"], "features": ["x"]}
        got = prepare_dataset(d, "attempts", config)
        self.assertEqual(got.index.tolist(), [0, 1])
        self.assertEqual(
            observation_status(d).tolist(),
            [
                "participated",
                "participated",
                "no_offensive_snaps",
                "unknown_participation",
                "participated",
            ],
        )
        r = coverage_report(d, "attempts", config)[0]
        self.assertEqual(r["retained_zero_outcomes"], 1)
        self.assertEqual(r["excluded_unknown_or_no_offensive_snaps"], 2)
        self.assertEqual(r["excluded_missing_features_or_outcome"], 1)
        self.assertTrue(pregame_eligible(d, ["QB"]).all())

    def test_eligibility_does_not_depend_on_current_opportunities_or_snap_share(self):
        d = self.frame()
        a = pregame_eligible(d, ["QB"])
        d["attempts"] = 999
        d["offense_pct"] = 0
        pd.testing.assert_series_equal(a, pregame_eligible(d, ["QB"]))

    def test_no_history_or_unknown_prior_role_excluded(self):
        d = self.frame()
        d.loc[0, "games_played_prior"] = 2
        d.loc[1, "offense_pct_last3_avg"] = np.nan
        self.assertEqual(
            pregame_eligible(d, ["QB"]).tolist(), [False, False, True, True, True]
        )


class SlateTests(unittest.TestCase):
    def test_model_uses_inclusive_features_and_never_future_outcomes(self):
        h = observations()
        s = schedule()
        with tempfile.TemporaryDirectory() as td:
            model = LinearRegression().fit(
                pd.DataFrame(
                    {
                        "passing_yards_season_avg": [0.0, 0.0, 100.0, 100.0],
                        "passing_yards_last3_avg": [0.0, 100.0, 0.0, 100.0],
                    }
                ),
                [0.0, 100.0, 0.0, 100.0],
            )
            joblib.dump(
                dict(
                    model=model,
                    features=["passing_yards_season_avg", "passing_yards_last3_avg"],
                    resid_std=10.0,
                    positions=["QB"],
                    training_cutoff="2025-10-06T02:00:00Z",
                    feature_timing_version="stage1a",
                ),
                Path(td) / "model_passing_yards.joblib",
            )
            result = build_slate(h, s, pd.Timestamp("2025-10-11T00:00Z"), model_dir=td)
            self.assertEqual(result.iloc[0].projection, 40.0)
            self.assertEqual(result.iloc[0].games_played_prior, 4)
            self.assertEqual(result.iloc[0].game_id, "g4")
            self.assertIn("+00:00", result.iloc[0].prediction_at)
            future = observations(values=(100000.0,), weeks=(6,))
            future["game_id"] = "g4"
            changed = build_slate(
                pd.concat([h, future]),
                s,
                pd.Timestamp("2025-10-11T00:00Z"),
                model_dir=td,
            )
            pd.testing.assert_frame_equal(result, changed)

    def test_future_trained_model_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "model_passing_yards.joblib"
            joblib.dump({"training_cutoff": "2025-10-12T10:00:00Z"}, path)
            with self.assertRaisesRegex(ValueError, "training outcomes"):
                build_slate(
                    observations(),
                    schedule(),
                    pd.Timestamp("2025-10-11T00:00Z"),
                    model_dir=td,
                )
            joblib.dump({}, path)
            with self.assertRaisesRegex(ValueError, "cutoff missing"):
                build_slate(
                    observations(),
                    schedule(),
                    pd.Timestamp("2025-10-11T00:00Z"),
                    model_dir=td,
                )

    def test_replay_rejects_untimestamped_context_or_starters(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "context timestamp"):
                build_slate(
                    observations(),
                    schedule().drop(columns="context_available_at"),
                    pd.Timestamp("2025-10-11T00:00Z"),
                    model_dir=td,
                )
            with self.assertRaisesRegex(ValueError, "QB starters"):
                build_slate(
                    observations(),
                    schedule(),
                    pd.Timestamp("2025-10-11T00:00Z"),
                    current_qb_starters={"A": "p"},
                    model_dir=td,
                )

    def test_opening_week_carries_previous_season_history(self):
        h = observations()
        h["season"] = 2024
        s = schedule()
        s.loc[:3, "season"] = 2024
        s.loc[:3, "gameday"] = s.loc[:3, "gameday"].str.replace("2025", "2024")
        s.loc[4, "week"] = 1
        s.loc[4, "gameday"] = "2025-09-07"
        with tempfile.TemporaryDirectory() as td:
            model = LinearRegression().fit(
                pd.DataFrame(
                    {
                        "passing_yards_season_avg": [0.0, 0.0, 100.0, 100.0],
                        "passing_yards_last3_avg": [0.0, 100.0, 0.0, 100.0],
                    }
                ),
                [0.0, 100.0, 0.0, 100.0],
            )
            joblib.dump(
                dict(
                    model=model,
                    features=["passing_yards_season_avg", "passing_yards_last3_avg"],
                    resid_std=10.0,
                    positions=["QB"],
                    training_cutoff="2024-10-06T02:00Z",
                    feature_timing_version="stage1a",
                ),
                Path(td) / "model_passing_yards.joblib",
            )
            result = build_slate(h, s, pd.Timestamp("2025-09-01T00:00Z"), model_dir=td)
        self.assertEqual(result.iloc[0].projection, 40.0)
        self.assertEqual(result.iloc[0].season, 2025)

    def test_no_completed_history_returns_empty(self):
        s = schedule()
        s[["home_score", "away_score"]] = np.nan
        with tempfile.TemporaryDirectory() as td:
            d = build_slate(
                observations(), s, pd.Timestamp("2025-09-01T00:00Z"), model_dir=td
            )
        self.assertTrue(d.empty)

    def test_empty_outputs_keep_schema(self):
        with tempfile.TemporaryDirectory() as td:
            d = build_slate(
                observations(),
                schedule(),
                pd.Timestamp("2025-10-11T00:00Z"),
                model_dir=td,
            )
        self.assertTrue(d.empty)
        self.assertIn("market", d)
        self.assertTrue(compute_top_picks(d).empty)

    def test_no_historical_fallback_for_missing_upcoming_projection(self):
        r = price_prop(
            market="Passing Yards",
            file_label="passing_yards",
            player="Player",
            side="Over",
            line=20.0,
            odds_raw="1.91",
            slate=None,
            latest_lookup={"Player": observations().iloc[-1]},
        )
        self.assertIn("error", r)


if __name__ == "__main__":
    unittest.main()
