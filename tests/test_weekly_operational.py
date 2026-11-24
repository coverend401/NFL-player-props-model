"""Prospective controls using synthetic finals; never reads sealed real outcomes."""

import json
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from weekly_learning.admission import (
    _proof_check,
    scoreboard_finality,
    time_gate,
    validate_receipt,
)
from weekly_learning.engine import POLICY
from weekly_learning.operations import preflight
from weekly_learning.store import ROOT, Store


class OperationalTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(POLICY.read_text())
        self.capture = {
            "capture_tier": "genuine_predecision_capture",
            "frozen_at": "2026-11-20T22:00:00Z",
            "game_kickoffs": {"2026_11_X_Y": "2026-11-24T01:15:00Z"},
        }

    def test_cutoff_and_capture_timing(self):
        with self.assertRaisesRegex(ValueError, "window closed"):
            time_gate(
                self.policy, 2026, 11, capture=self.capture, now="2026-11-24T11:59:59Z"
            )
        self.assertEqual(
            time_gate(
                self.policy, 2026, 11, capture=self.capture, now="2026-11-24T12:00:00Z"
            ),
            pd.Timestamp("2026-11-24T12:00:00Z"),
        )
        self.capture["frozen_at"] = "2026-11-24T01:00:00Z"
        with self.assertRaisesRegex(ValueError, "late"):
            time_gate(
                self.policy, 2026, 11, capture=self.capture, now="2026-11-24T12:00:00Z"
            )

    def test_receipt_gate_before_file_access(self):
        with patch("pathlib.Path.read_text") as read:
            with self.assertRaises(ValueError):
                validate_receipt(
                    ROOT, "does-not-exist", self.policy, now="2026-11-21T12:00:00Z"
                )
            read.assert_not_called()

    def test_preflight_no_results_or_network(self):
        # Exercise the sealed preflight, not the Python-3.14-only model loader.
        # Keep real capture-integrity checks; runtime compatibility has its own tests.
        with (
            patch(
                "weekly_learning.selection.resolve_current",
                return_value=(
                    None,
                    {"release_id": "research-week11-frozen-20261120-r2"},
                ),
            ) as resolve,
            patch("requests.get") as get,
            patch(
                "weekly_learning.operations.time_gate", side_effect=ValueError("closed")
            ),
        ):
            result = preflight(
                Store(ROOT / "weekly_learning_state"), record_capture=False
            )
        resolve.assert_called_once_with()
        self.assertTrue(result["capture_valid"])
        self.assertEqual(result["status"], "waiting_for_settlement")
        self.assertFalse(result["source_results_accessed"])
        self.assertFalse(result["candidate_generated"])
        get.assert_not_called()

    def evidence(self, final=True):
        game = pd.DataFrame(
            [
                {
                    "game_id": "2026_11_NE_DET",
                    "week": 11,
                    "home_team": "DET",
                    "away_team": "NE",
                    "kickoff_at": "2026-11-22T18:00:00Z",
                }
            ]
        )
        body = {
            "season": {"year": 2026, "type": 2},
            "week": {"number": 11},
            "events": [
                {
                    "date": "2026-11-22T18:00:00Z",
                    "competitions": [
                        {
                            "status": {
                                "type": {
                                    "completed": final,
                                    "state": "post" if final else "in",
                                }
                            },
                            "competitors": [
                                {
                                    "homeAway": "home",
                                    "team": {"abbreviation": "DET"},
                                    "score": "20"
                                    if final
                                    else {"must_not_parse": True},
                                },
                                {
                                    "homeAway": "away",
                                    "team": {"abbreviation": "NE"},
                                    "score": "0",
                                },
                            ],
                        }
                    ],
                }
            ],
        }
        response = Mock(status_code=200)
        response.iter_content.return_value = [json.dumps(body).encode()]
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return game, Mock(return_value=response)

    def test_unfinished_status_blocks_before_score_parsing(self):
        game, get = self.evidence(False)
        with self.assertRaisesRegex(ValueError, "not confirmed final"):
            scoreboard_finality(game, get=get, now="2026-11-24T12:00:00Z")
        self.assertEqual(get.call_count, 1)
        self.assertFalse(get.call_args.kwargs["allow_redirects"])

    def test_finality_rejects_other_weeks_and_preserves_kickoff_check(self):
        games, get = self.evidence()
        body = json.loads(get.return_value.iter_content.return_value[0])
        body["week"]["number"] = 12
        get.return_value.iter_content.return_value = [json.dumps(body).encode()]
        with self.assertRaisesRegex(ValueError, "different or unverified"):
            scoreboard_finality(games, get=get, now="2026-11-24T12:00:00Z")
        games, get = self.evidence()
        games["kickoff_at"] = "2026-11-22T21:25:00Z"
        with self.assertRaisesRegex(ValueError, "finality fixture match"):
            scoreboard_finality(games, get=get, now="2026-11-24T12:00:00Z")

    def test_finality_one_call_zero_and_score_mismatch(self):
        games, get = self.evidence()
        proof = scoreboard_finality(games, get=get, now="2026-11-24T12:00:00Z")
        self.assertEqual(proof["games"][0]["away_score"], 0)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(
            get.call_args.kwargs["params"],
            {"dates": "2026", "seasontype": 2, "week": 11, "limit": 100},
        )
        games["home_score"] = 20
        games["away_score"] = 0
        games["completed_at"] = "2026-11-23T02:00:00Z"
        proof["games"][0]["completed_at"] = games.iloc[0].completed_at
        cutoff = pd.Timestamp("2026-11-24T12:00:00Z")
        _proof_check(proof, games, cutoff, cutoff)
        games["home_score"] = 21
        with self.assertRaisesRegex(ValueError, "differs"):
            _proof_check(proof, games, cutoff, cutoff)

    def test_postponement_extends_cutoff_and_scope_is_bounded(self):
        self.capture["game_kickoffs"]["2026_11_X_Y"] = "2026-11-25T01:00:00Z"
        with self.assertRaises(ValueError):
            time_gate(
                self.policy, 2026, 11, capture=self.capture, now="2026-11-24T12:00:00Z"
            )
        with self.assertRaises(ValueError):
            time_gate(self.policy, 2027, 1, now="2027-01-01T12:00:00Z")


class ScopedSourceTests(unittest.TestCase):
    def test_future_outcomes_not_persisted(self):
        import tempfile
        from pathlib import Path

        from weekly_learning.admission import seal_source_files
        from weekly_learning.store import sha

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schedule = pd.DataFrame(
                [
                    {
                        "season": 2026,
                        "week": w,
                        "game_id": str(w),
                        "game_type": "REG",
                        "home_score": 900 + w,
                        "away_score": 800 + w,
                    }
                    for w in [10, 11, 12]
                ]
            )
            schedule.to_parquet(root / "schedule.parquet", index=False)
            pd.DataFrame(
                [{"season": 2026, "week": w, "targets": w} for w in [10, 11, 12]]
            ).to_parquet(root / "player_stats.parquet", index=False)
            records = {
                name: {"sha256": sha(root / (name + ".parquet"))}
                for name in ["schedule", "player_stats"]
            }
            (root / "sources.json").write_text(json.dumps(records))
            seal_source_files(root, 2026, 11, pd.Timestamp("2026-11-24T12:00:00Z"))
            self.assertEqual(
                pd.read_parquet(root / "player_stats.parquet").week.tolist(), [10, 11]
            )
            saved = pd.read_parquet(root / "schedule.parquet")
            self.assertTrue(saved[saved.week.eq(12)].home_score.isna().all())
            self.assertEqual(saved[saved.week.eq(11)].home_score.iloc[0], 911)
            for name, r in json.loads((root / "sources.json").read_text()).items():
                self.assertEqual(r["sha256"], sha(root / (name + ".parquet")))
                self.assertNotEqual(r["download_sha256"], r["sha256"])


@unittest.skipUnless(
    __import__("sys").version_info[:2] == (3, 14),
    "Frozen parent runtime is Python 3.14",
)
class OperationalReplayTests(unittest.TestCase):
    def test_new_contract_full_replay_retains_original_models(self):
        """Synthetic admission isolates v2 mechanics on the old unsealed W10 history.

        This is not a live Week12 certificate or a synthetic outcome evaluation.
        The time/finality gates themselves are exercised unmocked above.
        """
        import shutil
        import tempfile
        from pathlib import Path

        from release_utils import sha256
        from research_platform.slate import model_candidates, top_two
        from weekly_learning import contract
        from weekly_learning.game_script import build_game_research

        source = ROOT / "research_inference_releases/research-week11-frozen-20261120-r2"
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "copy"
            shutil.copytree(source, d)
            m = json.loads((d / "manifest.json").read_text())
            original_models = dict(m["models"])
            m["release_type"] = contract.TYPE
            m["certification"]["contract"] = contract.TYPE
            m["source_sha256"] = {p: sha256(ROOT / p) for p in contract.CODE}
            admission = {
                "season": 2026,
                "target_week": 11,
                "created_at": m["forecast_build_started_at"],
                "models": m["models"],
                "allowed_games": [],
            }
            (d / "admission.json").write_text(json.dumps(admission))
            f = pd.read_parquet(d / "features.parquet")
            s = pd.read_parquet(d / "schedule.parquet")
            slate = pd.read_parquet(d / "slate.parquet")
            groups = top_two(
                [],
                model_candidates(
                    slate, m, pd.Timestamp(m["prediction_at"]).to_pydatetime()
                ),
                m,
            )
            pd.DataFrame([r for rows in groups.values() for r in rows]).to_parquet(
                d / "top_two.parquet", index=False
            )
            (d / "game_script.json").write_text(
                json.dumps(build_game_research(f, s, m), allow_nan=False)
            )
            m["files"] = {
                p: {"sha256": sha256(d / p), "bytes": (d / p).stat().st_size}
                for p in contract.FILES
            }
            (d / "manifest.json").write_text(json.dumps(m))
            with (
                patch.object(contract, "time_gate"),
                patch.object(contract, "validate_receipt", return_value=admission),
            ):
                result = contract.validate_operational(d, ROOT, replay=True)
                self.assertEqual(result["models_verified"], 9)
                self.assertEqual(result["forecast_rows"], 618)
                self.assertEqual(result["top_two_rows"], 22)
                self.assertTrue(result["exact_replay"])
                self.assertEqual(m["models"], original_models)
                (d / "top_two.parquet").write_bytes(b"corrupted")
                with self.assertRaisesRegex(ValueError, "integrity"):
                    contract.validate_operational(d, ROOT)
            from research_platform.inference_release import validate_inference

            with self.assertRaisesRegex(ValueError, "Not a frozen"):
                validate_inference(d, ROOT)


class AdmissionReceiptTests(unittest.TestCase):
    def test_end_to_end_synthetic_admission_and_tamper(self):
        import tempfile
        from pathlib import Path

        from weekly_learning.admission import ESPN, approve_snapshot, validate_receipt
        from weekly_learning.store import sha

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("weekly_learning.sources.pd", wraps=pd) as source_pd,
        ):
            # Source freshness must use the same historical clock as this
            # synthetic receipt. Keep the real age, finality and hash checks.
            source_pd.Timestamp = Mock(wraps=pd.Timestamp)
            source_pd.Timestamp.now.return_value = pd.Timestamp("2026-11-20T12:02:00Z")
            repo = Path(tmp)
            (repo / "weekly_learning").mkdir()
            policy = json.loads(POLICY.read_text())
            policy["operational_scope"]["not_before"] = "2026-11-17T12:00:00Z"
            (repo / "weekly_learning/policy.json").write_text(json.dumps(policy))
            store = Store(repo / "weekly_learning_state")
            capture = {
                "capture_tier": "genuine_predecision_capture",
                "frozen_at": "2026-11-13T12:00:00Z",
                "game_kickoffs": {"2026_11_NE_DET": "2026-11-15T18:00:00Z"},
                "models": {},
            }
            with store.transaction():
                cap = store.publish(
                    "captures",
                    "synthetic",
                    frames={
                        "forecasts.parquet": pd.DataFrame(
                            [{"prediction_at": "2026-11-13T10:00:00Z"}]
                        )
                    },
                    documents={"capture.json": capture},
                )
            source = store.root / "sources/synthetic"
            source.mkdir(parents=True)
            pd.DataFrame(
                [
                    {
                        "season": 2026,
                        "week": 11,
                        "game_id": "2026_11_NE_DET",
                        "game_type": "REG",
                        "gameday": "2026-11-15",
                        "gametime": "13:00",
                        "home_team": "DET",
                        "away_team": "NE",
                        "home_score": 20,
                        "away_score": 0,
                    }
                ]
            ).to_parquet(source / "schedule.parquet", index=False)
            for name in ["player_stats", "team_stats", "snaps"]:
                pd.DataFrame(
                    [{"season": 2026, "week": 11, "observed_stat": 0}]
                ).to_parquet(source / (name + ".parquet"), index=False)
            records = {
                name: {
                    "url": f"https://github.com/nflverse/nflverse-data/releases/download/synthetic/{name}.parquet",
                    "retrieved_at": "2026-11-20T12:01:00Z",
                    "sha256": sha(source / (name + ".parquet")),
                }
                for name in ["schedule", "player_stats", "team_stats", "snaps"]
            }
            (source / "sources.json").write_text(json.dumps(records))
            proof = {
                "url": ESPN + "?synthetic=1",
                "retrieved_at": "2026-11-20T12:00:00Z",
                "response_sha256": "a" * 64,
                "games": [
                    {
                        "game_id": "2026_11_NE_DET",
                        "week": 11,
                        "home_team": "DET",
                        "away_team": "NE",
                        "home_score": 20,
                        "away_score": 0,
                        "confirmed_final": True,
                        "kickoff_at": "2026-11-15T18:00:00Z",
                        "completed_at": "2026-11-16T02:00:00Z",
                    }
                ],
            }
            path = approve_snapshot(
                repo,
                source,
                str(cap.relative_to(repo)),
                policy,
                now="2026-11-20T12:02:00Z",
                proof=proof,
            )
            r = validate_receipt(repo, path, policy, now="2026-11-20T12:02:00Z")
            self.assertEqual(r["target_week"], 12)
            self.assertEqual(
                pd.read_parquet(source / "player_stats.parquet").observed_stat.iloc[0],
                0,
            )
            self.assertEqual(len(r["allowed_games"]), 1)
            data = json.loads(path.read_text())
            data["models"] = {"forged": True}
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "model mismatch"):
                validate_receipt(repo, path, policy, now="2026-11-20T12:02:00Z")
            # The isolation fix must not make genuinely expired snapshots valid.
            from weekly_learning.sources import verify_snapshot

            source_pd.Timestamp.now.return_value = pd.Timestamp("2026-11-22T12:01:01Z")
            with self.assertRaisesRegex(ValueError, "snapshot is stale"):
                verify_snapshot(source, max_age_hours=48)


class SelectionAndRefreshTests(unittest.TestCase):
    def test_target_week_depth_requires_new_evidence_not_fresh_download_alone(self):
        from weekly_learning.forecast import require_current_depth

        depth = pd.DataFrame(
            {"team": ["DET"], "observed": [pd.Timestamp("2026-11-23T20:00:00Z")]}
        )
        with self.assertRaisesRegex(ValueError, "stale"):
            require_current_depth(depth, {"DET"}, "2026-11-24T12:00:00Z")
        depth["observed"] = pd.Timestamp("2026-11-24T09:00:00Z")
        require_current_depth(depth, {"DET"}, "2026-11-24T12:00:00Z")
        with self.assertRaisesRegex(ValueError, "missing"):
            require_current_depth(depth, {"DET", "NE"}, "2026-11-24T12:00:00Z")

    def test_refresh_gate_precedes_network_and_receipt_read(self):
        from weekly_learning.operations import prepare_latest

        with (
            patch(
                "weekly_learning.operations.time_gate", side_effect=ValueError("closed")
            ),
            patch("weekly_learning.sources.fetch") as fetch,
        ):
            with self.assertRaisesRegex(ValueError, "closed"):
                prepare_latest(
                    Store(ROOT / "weekly_learning_state"), "synthetic-no-write"
                )
            fetch.assert_not_called()

    def test_explicit_selection_and_deadline_preserve_old_pointer(self):
        import tempfile
        from pathlib import Path

        from weekly_learning import selection

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            store = Store(repo / "weekly_learning_state")
            candidate = repo / "research_inference_releases/synthetic"
            candidate.mkdir(parents=True)
            manifest = {
                "release_id": "synthetic",
                "release_type": selection.TYPE,
                "game_kickoffs": {"synthetic": "2026-11-29T18:00:00Z"},
            }
            (candidate / "manifest.json").write_text(json.dumps(manifest))
            pointer = repo / selection.POINTER
            with (
                patch.object(selection, "ROOT", repo),
                patch.object(
                    selection,
                    "validate_operational",
                    return_value={"exact_replay": True},
                ) as validate,
            ):
                selection.select(store, candidate, now="2026-11-24T12:00:00Z")
                before = pointer.read_bytes()
                self.assertEqual(json.loads(before)["release_id"], "synthetic")
                self.assertTrue(validate.call_args.kwargs["replay"])
                with self.assertRaisesRegex(ValueError, "deadline"):
                    selection.select(store, candidate, now="2026-11-29T17:00:00Z")
                self.assertEqual(pointer.read_bytes(), before)
            self.assertFalse((repo / "research_active_inference.json").exists())

    def test_invalid_selection_falls_back_without_production_change(self):
        from weekly_learning import selection

        slate = pd.DataFrame([{"sentinel": True}])
        release = {
            "release_type": "research_frozen_model_inference_v1",
            "release_id": "previous",
        }
        with (
            patch.dict("os.environ", {"NFL_RESEARCH_INFERENCE_POINTER": ""}),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                selection, "resolve_current", side_effect=AssertionError("invalid")
            ),
        ):
            actual, meta = selection.for_app(slate, release)
        self.assertIs(actual, slate)
        self.assertEqual(meta["release_id"], "previous")
        self.assertIn("warning", next(k for k in meta if "warning" in k))


if __name__ == "__main__":
    unittest.main()
