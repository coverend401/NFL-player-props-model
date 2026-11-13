"""Regression cases discovered during the focused pre-merge review."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from test_stage1a import observations, schedule
from scripts.build_features import build_player_features
from scripts.forecast_features import schedule_times, completed_history
from scripts.build_slate import (
    build_slate,
    compute_top_picks,
    build_game_context_for_week,
    get_upcoming_qb_starters,
)
from scripts.train_all_markets import prepare_dataset, train_market
from pricing import price_prop


class FinalReviewTests(unittest.TestCase):
    def model(self, directory, cutoff="2025-10-06T02:00:00Z", version="stage1a"):
        x = pd.DataFrame(
            [(a, b, c) for a in [0.0, 100.0] for b in [0.0, 100.0] for c in [0.0, 1.0]],
            columns=["passing_yards_season_avg", "passing_yards_last3_avg", "indoor"],
        )
        model = LinearRegression().fit(x, x.passing_yards_last3_avg + 20 * x.indoor)
        bundle = dict(
            model=model,
            features=x.columns.tolist(),
            resid_std=10.0,
            positions=["QB"],
            training_cutoff=cutoff,
            feature_timing_version=version,
        )
        joblib.dump(bundle, Path(directory) / "model_passing_yards.joblib")

    def test_unknown_roof_preserves_explicit_scenarios_but_not_betting_output(self):
        s = schedule()
        s.loc[s.week == 6, "roof"] = np.nan
        with tempfile.TemporaryDirectory() as d:
            self.model(d)
            slate = build_slate(
                observations(), s, pd.Timestamp("2025-10-11T00:00Z"), model_dir=d
            )
        row = slate.iloc[0]
        self.assertEqual(row.projection_status, "roof_scenarios_only")
        self.assertEqual(
            (row.projection, row.roof_scenario_low, row.roof_scenario_high),
            (50.0, 40.0, 60.0),
        )
        self.assertTrue(pd.isna(s.loc[s.week == 6, "roof"].iloc[0]))
        self.assertTrue(compute_top_picks(slate).empty)
        result = price_prop(
            market="Passing Yards",
            file_label="passing_yards",
            player="Player",
            side="Over",
            line=40.0,
            odds_raw="1.91",
            slate=slate,
        )
        self.assertIn("roof unresolved", result["error"])

    def test_known_roof_forecasts_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            self.model(d)
            row = build_slate(
                observations(),
                schedule(),
                pd.Timestamp("2025-10-11T00:00Z"),
                model_dir=d,
            ).iloc[0]
        self.assertEqual(row.projection_status, "complete")
        self.assertEqual(row.projection, 40.0)

    def test_missing_model_feature_version_requires_coordinated_refresh(self):
        with tempfile.TemporaryDirectory() as d:
            self.model(d, version="old")
            with self.assertRaisesRegex(ValueError, "coordinated model refresh"):
                build_slate(
                    observations(),
                    schedule(),
                    pd.Timestamp("2025-10-11T00:00Z"),
                    model_dir=d,
                )

    def test_returning_traded_qb_uses_confirmed_asof_team_after_opening_week(self):
        h = observations()
        h["season"] = 2024
        s = schedule()
        s.loc[:3, "season"] = 2024
        s.loc[:3, "gameday"] = s.loc[:3, "gameday"].str.replace("2025", "2024")
        at = pd.Timestamp("2025-10-11T00:00Z")
        with tempfile.TemporaryDirectory() as d:
            self.model(d, cutoff="2024-10-06T02:00Z")
            unconfirmed = build_slate(h, s, at, model_dir=d)
            confirmed = build_slate(
                h,
                s,
                at,
                model_dir=d,
                current_qb_starters={"B": "p"},
                qb_starters_as_of=at,
            )
        self.assertTrue(unconfirmed.empty)
        self.assertEqual(len(confirmed), 1)
        self.assertEqual(confirmed.iloc[0].team, "B")
        self.assertEqual(confirmed.iloc[0].opponent, "A")

    def test_january_depth_chart_request_uses_nfl_fixture_season(self):
        s = schedule().iloc[[-1]].copy()
        s["gameday"] = "2027-01-03"
        s["season"] = 2026
        s["week"] = 18
        at = pd.Timestamp("2027-01-01T00:00Z")
        with patch(
            "scripts.build_slate.get_current_qb_starters", return_value={}
        ) as load:
            get_upcoming_qb_starters(s, at)
        load.assert_called_once_with(2026, at)

    def test_training_strict_asof_filters_future_proxy_and_equality(self):
        at = pd.Timestamp("2026-11-10T09:00Z")
        frame = pd.DataFrame(
            dict(
                position=["QB"] * 4,
                games_played_prior=[4] * 4,
                offense_pct=[1.0] * 4,
                offense_pct_last3_avg=[1.0] * 4,
                attempts=[1.0, 2.0, 999.0, 999.0],
                x=[1.0] * 4,
                completed_at=[
                    at - pd.Timedelta(hours=1),
                    at,
                    at + pd.Timedelta(minutes=15),
                    pd.NaT,
                ],
            )
        )
        got = prepare_dataset(
            frame, "attempts", {"positions": ["QB"], "features": ["x"]}, as_of=at
        )
        self.assertEqual(got.attempts.tolist(), [1.0])

    def test_real_training_records_only_available_outcomes_in_metadata(self):
        at = pd.Timestamp("2026-11-10T09:00Z")
        n = 240
        frame = pd.DataFrame(
            dict(
                position=["QB"] * n,
                games_played_prior=[4] * n,
                offense_pct=[1.0] * n,
                offense_pct_last3_avg=[1.0] * n,
                x=np.arange(n) % 120,
                season=[2024] * 120 + [2025] * 120,
                week=(np.arange(n) % 18) + 1,
            )
        )
        frame["attempts"] = frame.x * 2.0
        frame["completed_at"] = pd.to_datetime(
            frame.season.astype(str) + "-12-30", utc=True
        )
        future = frame.iloc[[-1]].copy()
        future["season"] = 2026
        future["attempts"] = 1e9
        future["completed_at"] = at + pd.Timedelta(minutes=15)
        frame = pd.concat([frame, future], ignore_index=True)
        with (
            patch("scripts.train_all_markets.joblib.dump") as dump,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            train_market(
                frame,
                "attempts",
                {"positions": ["QB"], "features": ["x"]},
                training_as_of=at,
            )
        bundle = dump.call_args.args[0]
        self.assertLess(pd.Timestamp(bundle["training_cutoff"]), at)
        self.assertEqual(pd.Timestamp(bundle["training_as_of"]), at)
        self.assertEqual(bundle["feature_timing_version"], "stage1a")

    def test_feature_build_excludes_scored_but_not_yet_available_games(self):
        h = observations()
        s = schedule()
        s.loc[3, "gameday"] = "2026-11-09"
        s.loc[3, "gametime"] = "20:15"
        at = pd.Timestamp("2026-11-10T09:00Z")
        contexts = []
        for _, g in s.iterrows():
            c = build_game_context_for_week(pd.DataFrame([g])).reset_index()
            c["season"] = g.season
            c["week"] = g.week
            c["opponent_team"] = c.team.map({"A": "B", "B": "A"})
            contexts.append(c)
        with contextlib.redirect_stdout(io.StringIO()):
            built = build_player_features(
                h,
                aux=h[["player_id", "season", "week", "offense_pct"]],
                game_context=pd.concat(contexts),
                schedule=s,
                data_cutoff=at,
            )
        self.assertEqual(built.game_id.tolist(), ["g0", "g1", "g2"])
        self.assertEqual(
            schedule_times(s).iloc[3].completed_at, pd.Timestamp("2026-11-10T09:15Z")
        )

    def test_explicit_status_blocks_suspended_game_even_with_scores(self):
        s = schedule()
        s["game_status"] = "final"
        s.loc[0, "game_status"] = "suspended"
        h = completed_history(observations(), s, pd.Timestamp("2025-10-11T00:00Z"))
        self.assertNotIn("g0", h.game_id.tolist())

    def test_stats_available_timestamp_does_not_replace_missing_completion(self):
        s = schedule_times(schedule())
        s["stats_available_at"] = s.completed_at + pd.Timedelta(hours=1)
        s.loc[0, "completed_at"] = pd.NaT
        self.assertTrue(pd.isna(schedule_times(s).iloc[0].completed_at))

    def test_completion_before_kickoff_rejected(self):
        s = schedule_times(schedule())
        s.loc[0, "completed_at"] = s.iloc[0].kickoff_at - pd.Timedelta(minutes=1)
        with self.assertRaisesRegex(ValueError, "precede kickoff"):
            schedule_times(s)
