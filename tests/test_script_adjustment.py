"""Numerical script regression: no network, sealed outcomes, training or selection."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from script_adjustment.data import ACTIONS, aggregate, team_panel
from script_adjustment.models import FEATURES
from script_adjustment.players import Correction, Z, allocate
from weekly_learning.store import ROOT, Store


class ScriptMathTests(unittest.TestCase):
    def test_kneels_spikes_scrambles_and_sacks_have_correct_official_support(self):
        rows = []
        for i, (kind, passed, rush, sack, scramble, kneel) in enumerate(
            [
                ("pass", 1, 0, 0, 0, 0),
                ("pass", 1, 0, 1, 0, 0),
                ("run", 0, 1, 0, 1, 0),
                ("run", 0, 1, 0, 0, 0),
                ("qb_kneel", 0, 1, 0, 0, 1),
                ("qb_spike", 1, 0, 0, 0, 0),
            ]
        ):
            rows.append(
                {
                    "game_id": "2025_01_NE_DET",
                    "play_id": i,
                    "season": 2025,
                    "week": 1,
                    "season_type": "REG",
                    "posteam": "NE",
                    "defteam": "DET",
                    "play_type": kind,
                    "pass_attempt": passed,
                    "rush_attempt": rush,
                    "sack": sack,
                    "qb_scramble": scramble,
                    "qb_kneel": kneel,
                    "two_point_attempt": 0,
                    "score_differential": 10,
                    "game_seconds_remaining": 60,
                    "qtr": 4,
                }
            )
        actual = (
            aggregate(pd.DataFrame(rows))
            .groupby("action")
            .n.sum()
            .reindex(ACTIONS, fill_value=0)
        )
        self.assertEqual(
            actual.to_dict(),
            {"attempt": 2, "designed_carry": 1, "scramble": 1, "kneel": 1, "other": 1},
        )
        extra = pd.DataFrame(rows[:1])
        extra["two_point_attempt"] = 1
        self.assertEqual(
            aggregate(
                pd.concat([pd.DataFrame(rows), extra.assign(play_id=999)])
            ).n.sum(),
            6,
        )
        bad = pd.DataFrame(rows)
        bad["week"] = 11
        bad["season"] = 2026
        with self.assertRaisesRegex(ValueError, "Sealed"):
            aggregate(bad)

    def test_missing_state_and_duplicate_play_are_not_invented(self):
        row = {
            "game_id": "g",
            "play_id": 1,
            "season": 2025,
            "week": 1,
            "posteam": "NE",
            "defteam": "DET",
            "play_type": "pass",
            "pass_attempt": 1,
            "rush_attempt": 0,
            "sack": 0,
            "qb_scramble": 0,
            "qb_kneel": 0,
            "two_point_attempt": 0,
            "score_differential": np.nan,
            "game_seconds_remaining": 100,
            "qtr": 4,
        }
        with self.assertRaisesRegex(ValueError, "Missing"):
            aggregate(pd.DataFrame([row]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            aggregate(pd.DataFrame([row, row]))

    def test_same_game_outcomes_cannot_change_pregame_features(self):
        rows = []
        cells = []
        for week in range(1, 6):
            kickoff = pd.Timestamp("2025-09-01T18:00Z") + pd.Timedelta(weeks=week)
            for team, opponent, home in [("NE", "DET", 1), ("DET", "NE", 0)]:
                rows.append(
                    {
                        "game_id": str(week),
                        "team": team,
                        "opponent": opponent,
                        "season": 2025,
                        "week": week,
                        "kickoff_at": kickoff,
                        "completed_at": kickoff + pd.Timedelta(hours=8),
                        "is_home": home,
                        "plays": 60,
                        "dropbacks": 35,
                        "rushes": 25,
                        "margin": 7 if home else -7,
                        "points_for": 21 if home else 14,
                        "points_against": 14 if home else 21,
                        "pace_sum": 500,
                        "pace_n": 20,
                    }
                )
                for cell in range(15):
                    for action, n in [("attempt", 2), ("designed_carry", 2)]:
                        cells.append(
                            {
                                "game_id": str(week),
                                "team": team,
                                "season": 2025,
                                "week": week,
                                "cell": cell,
                                "action": action,
                                "n": n,
                            }
                        )
        games = pd.DataFrame(rows)
        counts = pd.DataFrame(cells)
        original = team_panel(games, counts)
        games.loc[games.game_id.eq("4"), ["margin", "points_for", "points_against"]] = (
            999
        )
        counts.loc[counts.game_id.eq("4"), "n"] = 500
        changed = team_panel(games, counts)
        pd.testing.assert_frame_equal(
            original[original.game_id.eq("4")][FEATURES],
            changed[changed.game_id.eq("4")][FEATURES],
        )
        self.assertTrue(
            (
                original.history_available_at.dropna()
                < original.loc[original.history_available_at.notna(), "prediction_at"]
            ).all()
        )

    def test_future_participation_cannot_change_teammate_pool_or_allocations(self):
        from script_adjustment.players import SHARE_COLS, player_histories

        rows = []
        for week in range(1, 5):
            for identity in ["A", "B"]:
                row = {
                    "player_id": identity,
                    "game_id": str(week),
                    "team": "NE",
                    "position": "QB",
                    "season": 2025,
                    "week": week,
                    "kickoff_at": pd.Timestamp("2025-09-01T18:00Z")
                    + pd.Timedelta(weeks=week),
                    "completed_at": pd.Timestamp("2025-09-02T02:00Z")
                    + pd.Timedelta(weeks=week),
                    "offense_pct": 0.5,
                    "stats_observed": True,
                    "team_total_attempts": 35,
                    "team_total_carries": 30,
                }
                for col in [
                    "attempts",
                    "carries",
                    "targets",
                    "passing_yards",
                    "completions",
                    "rushing_yards",
                    "receiving_yards",
                    "receptions",
                ]:
                    row[col] = 5
                rows.append(row)
        source = pd.DataFrame(rows)
        fixtures = source[source.week.eq(4)][
            ["game_id", "team", "season", "week", "kickoff_at"]
        ].drop_duplicates()
        absent = source[~(source.week.eq(4) & source.player_id.eq("B"))]
        a = player_histories(absent, fixtures=fixtures)
        b = player_histories(source, fixtures=fixtures)
        cols = ["player_id", "game_id", "category"] + SHARE_COLS
        pd.testing.assert_frame_equal(a[cols], b[cols])
        self.assertIn("B", set(a.player_id))
        self.assertTrue(a[a.player_id.eq("B")].actual_opportunities.isna().all())
        self.assertFalse(a[a.player_id.eq("B")].stats_observed.any())

    def test_coherent_capacity_preserves_unassigned_and_never_invents_teammates(self):
        teams = pd.DataFrame(
            [
                {
                    "game_id": "g",
                    "team": "NE",
                    "season": 2025,
                    "week": 1,
                    "kickoff_at": pd.Timestamp("2025-09-01T18:00Z"),
                    "expected_carries": 30.0,
                    "expected_attempts": 35.0,
                    "expected_scramble": 3.0,
                    "own_plays": 60.0,
                    "own_scramble_rate": 0.05,
                    "own_carries": 30.0,
                    "own_attempts": 35.0,
                }
            ]
        )
        candidates = pd.DataFrame(
            [
                {
                    "player_id": str(i),
                    "game_id": "g",
                    "team": "NE",
                    "season": 2025,
                    "week": 1,
                    "kickoff_at": pd.Timestamp("2025-09-01T18:00Z"),
                    "category": "carries",
                    "position": "RB",
                    "share_recent": v,
                    "prior_snaps": 0.5,
                }
                for i, v in enumerate([0.2, 0.3])
            ]
        )
        _, c = allocate(candidates, teams)
        self.assertAlmostEqual(c.unassigned.iloc[0], 15.0)
        candidates["share_recent"] = 0.8
        out, c = allocate(candidates, teams)
        self.assertAlmostEqual(c.allocated.iloc[0], 30.0)
        self.assertGreaterEqual(c.unassigned.iloc[0], -1e-10)
        self.assertEqual(set(out.player_id), {"0", "1"})

    def test_context_explained_by_champion_is_not_counted_twice(self):
        x = np.linspace(1, 100, 300)
        frame = pd.DataFrame({"baseline": x, "y": x + 50})
        for i, name in enumerate(Z):
            frame[name] = (i + 1) * x + 10
        model = Correction().fit(frame, ["baseline"])
        pred, _ = model.predict(frame)
        np.testing.assert_array_equal(pred, np.zeros(len(frame)))
        self.assertFalse(model.active.any())

    def test_numerical_correction_learns_new_information_not_bias_intercept(self):
        rng = np.random.default_rng(47)
        x = rng.normal(size=1000)
        z = rng.normal(size=1000)
        frame = pd.DataFrame({"baseline": x, "y": x + 0.3 * z})
        for i, name in enumerate(Z):
            frame[name] = z if i == 0 else 2 * x
        model = Correction().fit(frame, ["baseline"])
        pred, components = model.predict(frame)
        self.assertGreater(np.std(pred), 0.1)
        self.assertAlmostEqual(float(pred.mean()), 0, places=10)
        np.testing.assert_allclose(components.sum(axis=1), pred)

    def test_operational_refresh_cannot_access_network_before_cutoff(self):
        from script_adjustment.weekly import current_inputs

        with (
            patch(
                "script_adjustment.weekly.validate_receipt",
                side_effect=ValueError("closed"),
            ),
            patch("script_adjustment.weekly.requests.get") as get,
            self.assertRaisesRegex(ValueError, "closed"),
        ):
            current_inputs(
                Store(ROOT / "weekly_learning_state"),
                Path("/tmp/nonexistent-receipt"),
                Path("/tmp/nonexistent-experiment"),
            )
        get.assert_not_called()

    def test_no_reconstruction_of_experimental_forecasts_after_results(self):
        import tempfile

        from script_adjustment.weekly import evaluate_captured

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("script_adjustment.weekly.requests.get") as get,
        ):
            self.assertIsNone(
                evaluate_captured(Store(tmp), "test", "missing-capture", pd.DataFrame())
            )
        get.assert_not_called()


@unittest.skipUnless(
    sys.version_info[:2] == (3, 14), "Frozen live parent requires Python3.14"
)
class FrozenExperimentTests(unittest.TestCase):
    def test_committed_numerical_replay_and_unchanged_champion(self):
        from script_adjustment.runner import DEFAULT
        from script_adjustment.validate import validate

        self.assertTrue(validate(DEFAULT, replay=True)["exact_replay"])

    def test_real_research_entrypoint_renders_numerical_and_weekly_views_without_http(
        self,
    ):
        import os
        import tempfile

        from streamlit.testing.v1 import AppTest

        from tests.archived_week11 import archived_week11

        with (
            archived_week11(),
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(
                os.environ,
                {
                    "RESEARCH_PREVIEW_PASSWORD": "synthetic-numerical-only",
                    "SPORTSGAMEODDS_API_KEY": "",
                    "SGO_GITHUB_QUOTA_TOKEN": "",
                    "SGO_QUOTA_REPOSITORY": "",
                    "SGO_RESEARCH_STORE": str(Path(tmp) / "cache.sqlite"),
                },
            ),
            patch("requests.get") as get,
            patch("requests.request") as request,
        ):
            app = AppTest.from_file(
                str(ROOT / "odds_value_research.py"), default_timeout=90
            ).run()
            app.text_input(key="research_password").input("synthetic-numerical-only")
            app.button[0].click().run()
            app.selectbox[0].select("Game Intelligence").run()
            self.assertFalse(app.exception, app.exception)
            tables = [d.value for d in app.dataframe]
            self.assertTrue(
                any(
                    {"Original", "Experimental", "Change"} <= set(t.columns)
                    for t in tables
                )
            )
            app.selectbox[0].select("Weekly Learning").run()
            self.assertFalse(app.exception, app.exception)
            get.assert_not_called()
            request.assert_not_called()

    def test_report_retains_failed_challenger_and_sealed_week12_candidate(self):
        from script_adjustment.runner import DEFAULT

        r = json.loads((DEFAULT / "report.json").read_text())
        s = json.loads((DEFAULT / "week12_status.json").read_text())
        self.assertFalse(r["promotion_passed"])
        self.assertTrue(r["champion_retained"])
        self.assertFalse(s["player_candidate_certified"])
        d = pd.read_parquet(DEFAULT / "player_replay.parquet")
        self.assertEqual(d.market.nunique(), 9)
        self.assertTrue(d.delta.ne(0).any())
        self.assertGreater(d.y.eq(0).sum(), 0)
        self.assertFalse((d.season.eq(2026) & d.week.ge(11)).any())
        overlay = pd.read_parquet(DEFAULT / "reference_week11_adjustments.parquet")
        self.assertEqual(len(overlay), 568)
        self.assertTrue(overlay.projection_status.eq("complete").all())
        self.assertTrue(overlay.market.nunique() == 9)
        self.assertFalse((overlay.game_id == "2026_11_TEN_DAL").any())


class ProspectiveAdapterTests(unittest.TestCase):
    def test_admitted_synthetic_pbp_matches_official_counts_and_reuses_cache(self):
        import tempfile
        from unittest.mock import Mock

        from script_adjustment.data import COLUMNS
        from script_adjustment.weekly import current_inputs

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "state")
            base = root / "inputs"
            base.mkdir()
            experiment = root / "experiment"
            experiment.mkdir()
            columns = [
                "game_id",
                "team",
                "opponent",
                "season",
                "week",
                "plays",
                "dropbacks",
                "rushes",
                "no_huddle",
                "pace_sum",
                "pace_n",
                "kickoff_at",
                "completed_at",
                "is_home",
                "points_for",
                "points_against",
                "margin",
            ]
            pd.DataFrame(columns=columns).to_parquet(
                base / "games.parquet", index=False
            )
            pd.DataFrame(
                columns=["game_id", "team", "season", "week", "cell", "action", "n"]
            ).to_parquet(base / "cells.parquet", index=False)
            (experiment / "manifest.json").write_text(
                json.dumps({"input_bundle": "inputs"})
            )
            source = root / "source"
            source.mkdir()
            pd.DataFrame(
                [
                    {
                        "game_id": "2026_11_NE_DET",
                        "season": 2026,
                        "week": 11,
                        "game_type": "REG",
                        "gameday": "2026-11-01",
                        "gametime": "13:00",
                        "home_team": "DET",
                        "away_team": "NE",
                        "home_score": 21,
                        "away_score": 14,
                    }
                ]
            ).to_parquet(source / "schedule.parquet", index=False)
            pd.DataFrame(
                [
                    {
                        "game_id": "2026_11_NE_DET",
                        "team": t,
                        "season": 2026,
                        "week": 11,
                        "attempts": 1,
                        "carries": 1,
                    }
                    for t in ["NE", "DET"]
                ]
            ).to_parquet(source / "team_stats.parquet", index=False)
            rows = []
            for team, opponent in [("NE", "DET"), ("DET", "NE")]:
                for kind in ["pass", "qb_kneel"]:
                    row = {c: 0 for c in COLUMNS}
                    row.update(
                        game_id="2026_11_NE_DET",
                        play_id=len(rows),
                        season=2026,
                        week=11,
                        season_type="REG",
                        posteam=team,
                        defteam=opponent,
                        play_type=kind,
                        pass_attempt=int(kind == "pass"),
                        rush_attempt=int(kind == "qb_kneel"),
                        qb_kneel=int(kind == "qb_kneel"),
                        game_seconds_remaining=100,
                        qtr=4,
                        drive=1,
                        no_huddle=0,
                    )
                    rows.append(row)
            blob = root / "mock.parquet"
            pd.DataFrame(rows).to_parquet(blob, index=False)
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.iter_content.return_value = [blob.read_bytes()]
            receipt = root / "receipt.json"
            receipt.write_text("{}")
            spec = {
                "source_path": "source",
                "through_week": 11,
                "allowed_games": [{"game_id": "2026_11_NE_DET"}],
            }
            with (
                patch("script_adjustment.weekly.ROOT", root),
                patch("script_adjustment.weekly.validate_receipt", return_value=spec),
                patch("weekly_learning.admission.validate_receipt", return_value=spec),
                patch(
                    "script_adjustment.weekly.requests.get", return_value=response
                ) as get,
            ):
                games, cells = current_inputs(store, receipt, experiment)
                self.assertEqual(len(games), 2)
                self.assertEqual(cells.n.sum(), 4)
                self.assertEqual(cells[cells.action.eq("kneel")].n.sum(), 2)
                current_inputs(store, receipt, experiment)
                self.assertEqual(get.call_count, 1)


if __name__ == "__main__":
    unittest.main()
