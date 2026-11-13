"""Research-only regression fixtures. Simulated quotes are NOT betting evidence."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import tempfile
import shutil
import sys
import unittest
from unittest.mock import Mock, patch

import joblib
import numpy as np
import pandas as pd

from stage1b.data import prepare_panel, market_panel, feature_columns
from stage1b.probability import outcomes
from stage1b.runner import fit_fold
from stage1b1.models import CompletionThinning, LagBlend
from stage1b1.probability import (
    ShrunkSigmoid,
    student_cdf,
    mix_cdf,
    nb_cdf,
    conformal_offset,
    interval_score,
)
from stage1b1.runner import fit, evaluate, phases, point_policy
from stage1b1.odds_capture import event_odds, settlement_rule, CaptureUnavailable
from test_stage1b import fixture, PROTOCOL as OLD_PROTOCOL

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = json.loads((ROOT / "stage1b1/protocol.json").read_text())


class ProbabilityTests(unittest.TestCase):
    def test_thinning_never_uses_actual_future_trials(self):
        rng = np.random.default_rng(19)
        x = pd.DataFrame(rng.normal(size=(160, 3)), columns=["lag1", "lag2", "lag3"])
        a = rng.poisson(20, len(x))
        c = rng.binomial(a, 0.65)
        m = CompletionThinning().fit(x, a, c)
        q = m.predict(x.iloc[:5])
        am = m.attempt_mean(x.iloc[:5])
        self.assertTrue(((q >= 0) & (q <= am)).all())
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "model.joblib"
            joblib.dump(m, path)
            np.testing.assert_allclose(joblib.load(path).predict(x.iloc[:5]), q)
        with self.assertRaises(ValueError):
            CompletionThinning().fit(x, np.ones(160), np.ones(160) * 2)

    def test_calibrated_integer_cdf_is_monotone_and_push_coherent(self):
        cal = ShrunkSigmoid().fit(
            np.linspace(0.01, 0.99, 100), np.arange(100) > 40, np.repeat(0.5, 100), 0.15
        )
        mu = np.repeat(4.0, 3)
        base = nb_cdf(mu, 0.3)
        anchor = student_cdf(mu, 0, 3, True)
        cdf = mix_cdf(cal.cdf(base), anchor, 0.15)
        self.assertTrue((cdf(-1) == 0).all())
        previous = cdf(-1)
        for n in range(25):
            now = cdf(n)
            self.assertTrue((now >= previous).all())
            previous = now
        p = outcomes(cdf, np.array([0.0, 4.0, 4.5]))
        np.testing.assert_allclose(p.sum(axis=1), 1)
        self.assertGreater(p[1, 2], 0)
        self.assertEqual(p[2, 2], 0)
        self.assertEqual(cal(np.array([0, 1])).tolist(), [0, 1])

    def test_signed_yardage_not_censored_and_tail_mass_retained(self):
        cdf = student_cdf(np.array([0.0]), 0, 10, False)
        self.assertGreater(cdf(-2)[0], 0)
        self.assertLess(cdf(100)[0], 1)
        self.assertGreater(outcomes(cdf, np.array([-1.0]))[0, 2], 0)

    def test_conformal_rank_and_interval_score_manual(self):
        y = np.arange(10)
        lo = np.repeat(2.0, 10)
        hi = np.repeat(4.0, 10)
        # Scores: 2,1,0,0,0,1,2,3,4,5; ceil(11*.9)=10 -> 5.
        self.assertEqual(conformal_offset(y, lo, hi), 5)
        np.testing.assert_allclose(
            interval_score([1, 3, 6], [2, 2, 2], [4, 4, 4]), [22, 2, 42]
        )
        with self.assertRaises(ValueError):
            interval_score([1], [3], [2])

    def test_point_fallback_requires_independent_week_evidence(self):
        cols = ["a", "b", "c"]
        d = pd.DataFrame(
            {
                "a": [5] * 12,
                "b": [0] * 12,
                "c": [0] * 12,
                "y": [0] * 12,
                "season": [2020] * 12,
                "week": [1] * 12,
            }
        )
        model, name, rows = point_policy(d, d, d, cols, PROTOCOL)
        self.assertEqual(name, "career_mean")
        np.testing.assert_allclose(model.predict(d[cols]), 5)
        np.testing.assert_allclose(LagBlend((0.5, 0.5, 0)).predict(d[cols]), 2.5)


class ChronologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = market_panel(prepare_panel(fixture(), PROTOCOL), "passing_attempts")
        cls.base, _, _ = fit_fold(cls.d, "passing_attempts", 2022, OLD_PROTOCOL)
        cls.b, cls.info, cls.e = fit(
            cls.d, "passing_attempts", 2022, cls.base, PROTOCOL
        )

    def test_phases_do_not_overlap_and_labels_precede_next_decision(self):
        _, _, train, res, cal, sel, e = phases(self.d, 2022, PROTOCOL)
        self.assertLess(train.completed_at.max(), res.prediction_at.min())
        self.assertLess(res.completed_at.max(), cal.prediction_at.min())
        self.assertLess(cal.completed_at.max(), sel.prediction_at.min())
        self.assertLess(sel.completed_at.max(), e.prediction_at.min())
        self.assertEqual(sorted(sel.week.unique()), list(range(11, 19)))
        self.assertTrue(set(res.index).isdisjoint(cal.index))
        self.assertTrue(set(cal.index).isdisjoint(sel.index))

    def test_outer_outcomes_cannot_change_method_selection(self):
        changed = self.d.copy()
        changed.loc[changed.season == 2022, "y"] = 999999
        _, info, _ = fit(changed, "passing_attempts", 2022, self.base, PROTOCOL)
        self.assertEqual(self.info, info)

    def test_scoring_preserves_zeroes_and_truthful_intervals(self):
        f, q = evaluate(self.b, self.e, PROTOCOL)
        self.assertGreater(f.y.eq(0).sum(), 0)
        self.assertTrue((f.lower90 <= f.upper90).all())
        self.assertTrue((f.lower90 >= 0).all())
        self.assertTrue(q.groupby("row_id").size().eq(6).all())
        self.assertEqual(
            q.line_kind.unique().tolist(),
            ["hypothetical_pregame_halfline_NOT_BOOKMAKER"],
        )
        np.testing.assert_allclose(
            f.interval_score, interval_score(f.y, f.lower90, f.upper90)
        )
        self.assertLess(
            pd.Timestamp(self.b["information_available_at"]), f.prediction_at.min()
        )
        self.assertNotIn("attempts", feature_columns("passing_attempts"))

    def test_seal_unchanged_and_future_period_removed_before_features(self):
        self.assertEqual(PROTOCOL["final_start"], OLD_PROTOCOL["final_start"])
        self.assertEqual(PROTOCOL["final_week"], 11)
        src = fixture()
        future = src.iloc[:1].copy()
        future["season"] = 2026
        future["week"] = 11
        future["kickoff_at"] = pd.Timestamp("2026-11-20T01:15Z")
        future["completed_at"] = pd.Timestamp("2026-11-20T09:15Z")
        pd.testing.assert_frame_equal(
            prepare_panel(src, PROTOCOL),
            prepare_panel(pd.concat([src, future]), PROTOCOL),
        )


class CaptureTests(unittest.TestCase):
    def response(self, started=False):
        now = datetime.now(timezone.utc)
        body = {
            "id": "example",
            "sport_key": "americanfootball_nfl",
            "commence_time": (now + timedelta(days=-1 if started else 1)).isoformat(),
            "bookmakers": [
                {
                    "key": "synthetic_fixture",
                    "markets": [
                        {
                            "key": "player_pass_yds",
                            "last_update": (now - timedelta(minutes=1)).isoformat(),
                            "outcomes": [
                                {
                                    "name": "Over",
                                    "description": "TEST PLAYER",
                                    "price": 1.91,
                                    "point": 200.5,
                                },
                                {
                                    "name": "Under",
                                    "description": "TEST PLAYER",
                                    "price": 1.91,
                                    "point": 200.5,
                                },
                            ],
                        }
                    ],
                }
            ],
        }
        return SimpleNamespace(
            status_code=200,
            content=json.dumps(body).encode(),
            headers={"Date": now.isoformat()},
        )

    def test_missing_credential_makes_no_request(self):
        get = Mock()
        with (
            tempfile.TemporaryDirectory() as t,
            patch.dict("os.environ", {}, clear=True),
        ):
            with self.assertRaises(CaptureUnavailable):
                event_odds("example", Path(t) / "missing", get=get)
        get.assert_not_called()

    def test_raw_capture_hash_real_clock_and_no_credential_persisted(self):
        response = self.response()
        get = Mock(return_value=response)
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "capture"
            before = datetime.now(timezone.utc)
            meta = event_odds(
                "example", out, get=get, api_key="TEST_CREDENTIAL_NEVER_ARCHIVE"
            )
            self.assertGreaterEqual(datetime.fromisoformat(meta["observed_at"]), before)
            self.assertEqual(
                meta["sha256"], hashlib.sha256(response.content).hexdigest()
            )
            self.assertEqual((out / "response.bin").read_bytes(), response.content)
            self.assertNotIn("TEST_CREDENTIAL", (out / "capture.json").read_text())
            self.assertFalse(meta["backtest_ready"])
            self.assertEqual(meta["quote_count"], 2)
            self.assertFalse(get.call_args.kwargs["allow_redirects"])
            with self.assertRaises(ValueError):
                event_odds("example", out, get=get, api_key="TEST_KEY")

    def test_postkickoff_and_future_quote_refused(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "capture"
            with self.assertRaises(ValueError):
                event_odds(
                    "example",
                    out,
                    get=Mock(return_value=self.response(True)),
                    api_key="TEST_KEY",
                )
            self.assertFalse(out.exists())
            r = self.response()
            body = json.loads(r.content)
            body["bookmakers"][0]["markets"][0]["last_update"] = (
                datetime.now(timezone.utc) + timedelta(hours=1)
            ).isoformat()
            r.content = json.dumps(body).encode()
            with self.assertRaises(ValueError):
                event_odds("example", out, get=Mock(return_value=r), api_key="TEST_KEY")
            self.assertFalse(out.exists())

    def test_http_and_network_errors_do_not_expose_response_or_secret(self):
        with tempfile.TemporaryDirectory() as t:
            r = SimpleNamespace(status_code=403, content=b"TEST_SECRET", headers={})
            with self.assertRaises(CaptureUnavailable) as cm:
                event_odds(
                    "example",
                    Path(t) / "x",
                    get=Mock(return_value=r),
                    api_key="TEST_SECRET",
                )
            self.assertNotIn("TEST_SECRET", str(cm.exception))
            self.assertFalse((Path(t) / "x").exists())

    def test_output_guard_and_rules_no_redirect_credentials_or_effective_date_guess(
        self,
    ):
        with self.assertRaises(ValueError):
            event_odds(
                "example", ROOT / "not-research-capture", get=Mock(), api_key="TEST_KEY"
            )
        get = Mock()
        with tempfile.TemporaryDirectory() as t:
            for url in [
                "http://book.example/rules",
                "https://book.example/rules?token=secret",
                "https://name:secret@book.example/rules",
                "https://wrong.example/rules",
            ]:
                with self.assertRaises(ValueError):
                    settlement_rule(
                        url, Path(t) / "rules", approved_hosts=["book.example"], get=get
                    )
            get.assert_not_called()
            get.return_value = SimpleNamespace(
                status_code=200, content=b"Test rule fixture", headers={}
            )
            meta = settlement_rule(
                "https://book.example/rules",
                Path(t) / "rules",
                approved_hosts=["book.example"],
                get=get,
            )
            self.assertIn("not inferred", meta["rule_effective_date"])
            self.assertFalse(meta["backtest_ready"])
            self.assertFalse(get.call_args.kwargs["allow_redirects"])


@unittest.skipUnless(
    sys.version_info[:2] == (3, 14),
    "Archive runtime is pinned to production Python 3.14",
)
class ArchivedIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / "experiments/stage1b1/improvements-20261113-v1"
        if not cls.directory.exists():
            raise unittest.SkipTest("Full frozen experiment not present yet")

    def test_full_archive_has_all_models_and_exact_benchmark_population(self):
        from stage1b1.artifacts import validate_results

        result = validate_results(self.directory, ROOT)
        self.assertEqual(result["models"], 45)
        self.assertEqual(result["player_market_games"], 55303)
        self.assertTrue(result["final_sealed"])

    def test_payload_mutation_is_rejected(self):
        from stage1b1.artifacts import validate

        with tempfile.TemporaryDirectory() as t:
            copy = Path(t) / "archive"
            shutil.copytree(self.directory, copy)
            with (copy / "accuracy.csv").open("a") as f:
                f.write("tampered")
            with self.assertRaisesRegex(ValueError, "Payload integrity mismatch"):
                validate(copy, ROOT)

    def test_sealed_period_rejected_even_with_recomputed_payload_hash(self):
        from stage1b1.artifacts import validate_results
        from stage1b.artifacts import digest

        with tempfile.TemporaryDirectory() as t:
            copy = Path(t) / "archive"
            shutil.copytree(self.directory, copy)
            f = pd.read_parquet(copy / "forecasts.parquet")
            f.loc[0, "prediction_at"] = pd.Timestamp("2026-11-20T00:00Z")
            f.to_parquet(copy / "forecasts.parquet", index=False)
            m = json.loads((copy / "manifest.json").read_text())
            m["files"]["forecasts.parquet"] = digest(copy / "forecasts.parquet")
            (copy / "manifest.json").write_text(json.dumps(m))
            # The frozen chronology check may reject before the explicit seal check.
            with self.assertRaisesRegex(ValueError, "chronology changed|unsealed"):
                validate_results(copy, ROOT)


if __name__ == "__main__":
    unittest.main()
