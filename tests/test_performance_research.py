"""Performance comparisons use synthetic outcomes and never contact providers."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from performance_research.study import (
    candidates,
    paired_weeks,
    permitted,
    point_study,
    walk_calibrate,
)
from performance_research.weekly import capture, prospective_frame
from stage1b.data import MARKETS
from weekly_learning.store import Store


def point_rows():
    frame = pd.DataFrame(
        [
            {
                "market": "receptions",
                "game_id": str(i),
                "player_id": str(i),
                "position": "WR",
                "season": year,
                "week": i + 1,
                "baseline": 5.0,
                "y": 6.0,
                "recent_shrunk": 5.0,
                "player_ridge": 5.0,
                "role_ridge": 5.0,
                "opponent_ridge": 5.0,
                "context_tree": 6.0,
                "efficiency3": 0.5,
                "efficiency_career": 0.5,
            }
            for year in [2025, 2026]
            for i in range(10)
        ]
    )
    for target, _, opp, _ in MARKETS.values():
        for field in [target, opp]:
            for lag in ["last3", "last5", "career"]:
                frame[field + "_" + lag] = 5.0
    return frame


class ComparisonTests(unittest.TestCase):
    def test_future_outcomes_cannot_change_point_inputs_or_selected_method(self):
        f = point_rows()
        original, methods = candidates(f)
        changed = f.copy()
        changed.loc[changed.season.eq(2026), "y"] = 999.0
        alternate, _ = candidates(changed)
        pd.testing.assert_frame_equal(original[methods], alternate[methods])
        self.assertEqual(point_study(f)[1], point_study(changed)[1])

    def test_missing_workload_is_not_zero_and_populations_are_identical(self):
        f = point_rows()
        f.loc[0, "targets_last3"] = np.nan
        c, _ = candidates(f)
        self.assertEqual(len(c), len(f))
        self.assertEqual(c.loc[0, "workload_efficiency_0.5"], c.loc[0, "baseline"])
        self.assertTrue(c.loc[0, "workload_efficiency_0.5_missing_input_fallback"])
        with self.assertRaises(ValueError):
            permitted(f.assign(season=2026, week=11))

    def test_paired_uncertainty_uses_weeks_not_player_row_pseudoreplication(self):
        f = point_rows()
        f = f[f.season.eq(2025)]
        result = paired_weeks(f, pd.Series(np.ones(len(f)), index=f.index))
        duplicated = pd.concat([f] * 20, ignore_index=True)
        other = paired_weeks(duplicated, pd.Series(np.ones(len(duplicated))))
        self.assertEqual(result, other)
        self.assertEqual(result["p"], 1 / 32)

    def test_calibrator_is_prefix_only_and_monotone(self):
        rows = []
        for week in range(1, 9):
            kickoff = pd.Timestamp("2025-09-01T18:00Z") + pd.Timedelta(weeks=week)
            for i in range(24):
                rows.append(
                    {
                        "game_id": f"{week}-{i}",
                        "player_id": str(i),
                        "market": "receptions",
                        "method": "research_empirical",
                        "season": 2025,
                        "week": week,
                        "offset": i % 3,
                        "p_over": [0.3, 0.6, 0.9][i % 3],
                        "observed_over": int(i % 3 > 0),
                        "prediction_at": kickoff - pd.Timedelta(hours=1),
                        "available_at": kickoff + pd.Timedelta(hours=8),
                    }
                )
        f = pd.DataFrame(rows)
        first = walk_calibrate(f)
        changed = f.copy()
        changed.loc[changed.week.eq(8), "observed_over"] = (
            1 - changed.loc[changed.week.eq(8), "observed_over"]
        )
        second = walk_calibrate(changed)
        np.testing.assert_allclose(first.calibrated, second.calibrated)
        self.assertTrue(
            first.loc[first.week.eq(8), "calibration_training_rows"].gt(0).all()
        )
        last = first[first.week.eq(8)].sort_values("p_over")
        self.assertTrue(last.calibrated.diff().dropna().ge(0).all())


class ProspectiveTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame(
            [
                {
                    "projection_status": "complete",
                    "market": "Receptions",
                    "game_id": "2026_12_A_B",
                    "player_id": "p",
                    "projection": 5.0,
                    "career_avg": 4.0,
                    "recent_form": 8.0,
                    "prediction_at": "2026-11-25T12:00Z",
                    "season": 2026,
                    "week": 12,
                }
            ]
        )

    def test_genuine_capture_formula_and_timing(self):
        f = self.frame()
        times = {"2026_12_A_B": "2026-11-29T18:00Z"}
        c = prospective_frame(f, times, "2026-11-25T13:00Z")
        self.assertEqual(c.loc[0, "captured_season_recent_0.5"], 6.0)
        self.assertEqual(c.loc[0, "market"], "receptions")
        with self.assertRaises(ValueError):
            prospective_frame(f, times, "2026-11-29T17:00Z")
        with self.assertRaises(ValueError):
            prospective_frame(f, times, "2026-11-25T11:00Z")

    def test_capture_is_immutable_and_does_not_modify_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            self.frame().to_parquet(source / "slate.parquet", index=False)
            (source / "manifest.json").write_text("{}")
            store = Store(root / "state")
            meta = {
                "release_id": "synthetic",
                "game_kickoffs": {"2026_12_A_B": "2026-11-29T18:00Z"},
                "models": {"synthetic": "only"},
            }
            original = (source / "slate.parquet").read_bytes()
            p = capture(store, source, meta, now="2026-11-25T13:00Z")
            self.assertEqual(capture(store, source, meta, now="2026-11-25T14:00Z"), p)
            self.assertEqual((source / "slate.parquet").read_bytes(), original)
            self.assertEqual(
                json.loads((p / "capture.json").read_text())["capture_tier"],
                "genuine_predecision_capture",
            )

    def test_weekly_challengers_are_scored_only_after_admission_and_never_promoted(
        self,
    ):
        from performance_research.weekly import evaluate

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "weekly_learning").mkdir()
            policy = {
                "operational_settlement_approved": True,
                "operational_scope": {
                    "season": 2026,
                    "first_week": 11,
                    "last_week": 18,
                    "not_before": "2026-11-24T12:00Z",
                },
            }
            (root / "weekly_learning/policy.json").write_text(json.dumps(policy))
            source = root / "source"
            source.mkdir()
            self.frame().to_parquet(source / "slate.parquet", index=False)
            (source / "manifest.json").write_text("{}")
            receipt = root / "receipt.json"
            receipt.write_text("{}")
            store = Store(root / "state")
            meta = {
                "release_id": "synthetic",
                "game_kickoffs": {"2026_12_A_B": "2026-11-29T18:00Z"},
                "models": {"synthetic": "only"},
            }
            capture(store, source, meta, now="2026-11-25T13:00Z")
            results = pd.DataFrame(
                [
                    {
                        "game_id": "2026_12_A_B",
                        "player_id": "p",
                        "market": "receptions",
                        "status": "scored",
                        "actual": 0.0,
                    }
                ]
            )
            proof = {
                "allowed_games": [{"game_id": "2026_12_A_B"}],
                "models": meta["models"],
            }
            with (
                patch("performance_research.weekly.ROOT", root),
                patch(
                    "performance_research.weekly.validate_receipt", return_value=proof
                ),
            ):
                paths = evaluate(
                    store,
                    "synthetic-cycle",
                    "synthetic",
                    results,
                    receipt,
                    now="2026-12-01T13:00Z",
                )
                report = json.loads((paths[0] / "report.json").read_text())
                self.assertEqual(report["status"], "RETAIN_CHAMPION")
                self.assertEqual(report["scored_rows"], 1)
                self.assertEqual(len(report["candidate_metrics"]), 3)
                self.assertTrue(
                    all(r["zero_outcomes"] == 1 for r in report["candidate_metrics"])
                )
            with (
                patch("performance_research.weekly.ROOT", root),
                patch(
                    "performance_research.weekly.validate_receipt",
                    side_effect=ValueError("closed"),
                ),
                patch("performance_research.weekly.pd.read_parquet") as read,
                self.assertRaises(ValueError),
            ):
                evaluate(
                    store,
                    "another",
                    "synthetic",
                    results,
                    receipt,
                    now="2026-11-23T12:00Z",
                )
            read.assert_not_called()
