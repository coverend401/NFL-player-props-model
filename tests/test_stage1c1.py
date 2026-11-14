"""Synthetic credit/accounting fixtures are not realised betting evidence."""

import json, copy
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from stage1c1.reconcile import event_credits, reconcile, STATS, COLS
from stage1c1.models import choose, fit, cdf, bounds
from stage1c1.oracles import substitutions
from stage1c1.diagnostics import effective_samples, feature_diagnostics
from stage1b.data import prepare_panel, market_panel, feature_columns
from stage1b.runner import fit_fold, model_predictions
from stage1b1.runner import phases
from stage1c.context import states, attach
from stage1b.probability import outcomes
from test_stage1c import data

ROOT = Path(__file__).resolve().parents[1]
P = json.loads((ROOT / "stage1c1/protocol.json").read_text())
OLD = json.loads((ROOT / "stage1b/protocol.json").read_text())


def credit_fixture():
    def play(i, **kw):
        d = {c: np.nan for c in COLS}
        d.update(
            game_id="g",
            play_id=i,
            season=2021,
            week=1,
            season_type="REG",
            posteam="BUF",
            play_type="pass",
            play_deleted=0,
            two_point_attempt=0,
            pass_attempt=0,
            rush_attempt=0,
            sack=0,
            complete_pass=0,
            incomplete_pass=0,
            interception=0,
            qb_spike=0,
        )
        d.update(kw)
        return d

    pbp = pd.DataFrame(
        [
            play(
                1,
                pass_attempt=1,
                complete_pass=1,
                passer_player_id="q",
                receiver_player_id="w",
                passing_yards=10,
                receiving_yards=10,
            ),
            play(
                2,
                pass_attempt=1,
                incomplete_pass=1,
                passer_player_id="q",
                receiver_player_id="x",
            ),
            play(
                3,
                play_type="run",
                rush_attempt=1,
                rusher_player_id="r",
                rushing_yards=5,
            ),
        ]
    )
    for col in [c for c in COLS if c.endswith("_player_id")]:
        pbp[col] = pbp[col].astype(object)
    rows = []
    for pid, pos, observed in [
        ("q", "QB", True),
        ("r", "RB", True),
        ("w", "WR", True),
        ("x", "WR", False),
        ("t", "TE", False),
    ]:
        r = dict(
            game_id="g",
            team="BUF",
            player_id=pid,
            position=pos,
            offense_pct=50.0,
            stats_observed=observed,
        )
        r.update({k: 0.0 if observed else np.nan for k in STATS})
        rows.append(r)
    source = pd.DataFrame(rows).set_index("player_id")
    source.loc["q", ["attempts", "completions", "passing_yards"]] = [2, 1, 10]
    source.loc["r", ["carries", "rushing_yards"]] = [1, 5]
    source.loc["w", ["targets", "receptions", "receiving_yards"]] = [1, 1, 10]
    source = source.reset_index()
    total = dict(
        attempts=2.0,
        completions=1.0,
        passing_yards=10.0,
        carries=1.0,
        rushing_yards=5.0,
        targets=2.0,
        receptions=1.0,
        receiving_yards=10.0,
    )
    legacy = []
    for kind in ["pass", "rush_QB", "rush_RB", "rec_RB", "rec_WR", "rec_TE"]:
        values = total.copy() if kind == "pass" else {k: 0.0 for k in STATS}
        known = kind not in ["rec_WR", "rec_TE"]
        if kind == "rush_RB":
            values.update(carries=1.0, rushing_yards=5.0)
        if not known:
            values = {k: np.nan for k in STATS}
        legacy.append(
            dict(
                game_id="g",
                team="BUF",
                kind=kind,
                known_complete=known,
                unknown_players=0 if known else 1,
                **values,
            )
        )
    return (
        pbp,
        source,
        pd.DataFrame(legacy),
        pd.DataFrame([dict(game_id="g", team="BUF")]),
    )


class CreditTests(unittest.TestCase):
    def test_recover_positive_and_zero_opportunity_without_changing_box_targets(self):
        pbp, s, l, g = credit_fixture()
        original = s.copy(deep=True)
        r, a, players, e = reconcile(event_credits(pbp), s, l, g)
        self.assertTrue(a[["pass_strict", "rush_strict", "rec_strict"]].all().all())
        x = r.set_index("kind")
        self.assertEqual(x.loc["rec_WR", "targets"], 2)
        self.assertEqual(x.loc["rec_TE", "targets"], 0)
        self.assertTrue(x.loc["rec_TE", "recovered_from_events"])
        player = players.set_index("player_id")
        self.assertEqual(player.loc["x", "targets_event_validated"], 1)
        self.assertEqual(player.loc["t", "targets_event_validated"], 0)
        pd.testing.assert_frame_equal(s, original)
        self.assertTrue(pd.isna(s.set_index("player_id").loc["t", "targets"]))

    def test_incomplete_count_ledger_cannot_infer_missing_player_zero(self):
        pbp, s, l, g = credit_fixture()
        l.loc[l.kind.eq("pass"), "targets"] = 3
        r, a, players, e = reconcile(event_credits(pbp), s, l, g)
        self.assertFalse(a.rec_strict.iloc[0])
        self.assertTrue(
            pd.isna(players.set_index("player_id").loc["t", "targets_event_validated"])
        )
        self.assertFalse(r.set_index("kind").loc["rec_TE", "known_complete"])

    def test_lateral_yards_do_not_add_targets_catches_or_carries(self):
        pbp, s, l, g = credit_fixture()
        pbp.loc[
            0,
            ["passing_yards", "lateral_receiver_player_id", "lateral_receiving_yards"],
        ] = [13, "r", 3]
        s.loc[s.player_id.eq("q"), "passing_yards"] = 13
        s.loc[s.player_id.eq("r"), "receiving_yards"] = 3
        l.loc[l.kind.eq("pass"), ["passing_yards", "receiving_yards"]] = [13, 13]
        e = event_credits(pbp)
        r, a, players, e = reconcile(e, s, l, g)
        self.assertTrue(a.rec_strict.iloc[0])
        rplayer = players.set_index("player_id").loc["r"]
        self.assertEqual(rplayer.receiving_yards_event_validated, 3)
        self.assertEqual(rplayer.targets_event_validated, 0)
        self.assertEqual(rplayer.receptions_event_validated, 0)
        self.assertEqual(rplayer.carries_event_validated, 1)

    def test_missing_actor_and_missing_credit_fail_closed(self):
        pbp, s, l, g = credit_fixture()
        pbp.loc[0, "receiver_player_id"] = "unmapped"
        r, a, players, e = reconcile(event_credits(pbp), s, l, g)
        self.assertFalse(a.rec_strict.iloc[0])
        self.assertGreater(e.position_missing.sum(), 0)
        pbp, s, l, g = credit_fixture()
        pbp.loc[0, "passing_yards"] = np.nan
        r, a, players, e = reconcile(event_credits(pbp), s, l, g)
        self.assertFalse(a.pass_strict.iloc[0])
        self.assertGreater(e.credit_missing.sum(), 0)

    def test_no_play_deleted_and_two_point_events_not_counted(self):
        pbp, s, l, g = credit_fixture()
        extra = []
        for i, kw in [
            (4, {"play_type": "no_play"}),
            (5, {"play_deleted": 1}),
            (6, {"two_point_attempt": 1}),
        ]:
            row = pbp.iloc[0].copy()
            row["play_id"] = i
            for key, v in kw.items():
                row[key] = v
            extra.append(row)
        e = event_credits(pd.concat([pbp, pd.DataFrame(extra)], ignore_index=True))
        self.assertEqual(e[e.stat.eq("attempts")].value.sum(), 2)

    def test_aliases_normalize_before_identity_join(self):
        pbp, s, l, g = credit_fixture()
        pbp["posteam"] = "OAK"
        s["team"] = "LV"
        l["team"] = "LV"
        g["team"] = "LV"
        r, a, players, e = reconcile(event_credits(pbp), s, l, g)
        self.assertTrue(a.rec_strict.iloc[0])
        self.assertFalse(e.position_missing.any())

    def test_negative_production_and_duplicate_play_guard(self):
        pbp, _, _, _ = credit_fixture()
        pbp.loc[0, "receiving_yards"] = -5
        e = event_credits(pbp)
        self.assertEqual(e[e.stat.eq("receiving_yards")].value.sum(), -5)
        with self.assertRaises(ValueError):
            event_credits(pd.concat([pbp, pbp.iloc[:1]]))

    def test_final_events_refused(self):
        pbp, _, _, _ = credit_fixture()
        pbp["season"] = 2026
        pbp["week"] = 11
        with self.assertRaises(ValueError):
            event_credits(pbp)


class OracleTests(unittest.TestCase):
    def test_hand_computed_four_factor_shapley(self):
        values, phi, share, eff, extra = substitutions(10, 0.5, 2, 20, 10, 30)
        self.assertEqual(values[0], 10)
        self.assertEqual(values[15], 30)
        np.testing.assert_allclose(phi, [12.5, 0, 7.5, 0])
        self.assertEqual(share, 0.5)
        self.assertEqual(eff, 3)

    def test_zero_individual_opportunity_has_no_observed_efficiency_error(self):
        values, phi, share, eff, extra = substitutions(20, 0.5, 2, 20, 0, 0)
        self.assertEqual(eff, 2)
        self.assertEqual(values[4], values[0])
        self.assertAlmostEqual(phi[2], 0)
        self.assertAlmostEqual(phi[1], 20)

    def test_zero_team_opportunity_does_not_invent_zero_share(self):
        values, phi, share, eff, extra = substitutions(20, 0.5, 2, 0, 0, 0)
        self.assertEqual(share, 0.5)
        np.testing.assert_allclose(phi, [20, 0, 0, 0])
        self.assertEqual(values[15], 0)

    def test_nonopportunity_credit_is_a_separate_factor(self):
        values, phi, share, eff, extra = substitutions(20, 0, 2, 20, 0, 3)
        self.assertEqual(extra, 3)
        self.assertEqual(values[15], 3)
        np.testing.assert_allclose(phi, [0, 0, 0, 3])

    def test_signed_yards_and_attribution_identity(self):
        values, phi, *_ = substitutions(25, 0.3, 4, 20, 5, -7)
        self.assertEqual(values[15], -7)
        self.assertAlmostEqual(phi.sum(), abs(values[0] + 7))


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src, g, rates = data()
        src["team"] = np.where(src.player_id.str[1:].astype(int).lt(6), "BUF", "MIA")
        src["opponent_team"] = np.where(src.team.eq("BUF"), "MIA", "BUF")
        cls.src = src.copy()
        cls.games = g.copy()
        cls.rates = rates.copy()
        cls.context = states(g, rates)
        cls.d = attach(
            market_panel(prepare_panel(src, P), "passing_attempts"),
            states(g, rates),
            "passing_attempts",
        )
        cls.old, _, _ = fit_fold(cls.d, "passing_attempts", 2022, OLD)
        cls.b, cls.info, cls.e, cls.sel, cls.train = fit(
            cls.d, "passing_attempts", 2022, "b1_none", P, cls.old
        )

    def test_native_recipe_reconstructs_original_point_selection(self):
        initial, sel, train, *_ = phases(self.d, 2022, P)
        cols = feature_columns("passing_attempts")
        m, name, records = choose(
            initial, sel, train, "passing_attempts", cols, "b1", P
        )
        np.testing.assert_allclose(
            np.maximum(m.predict(self.e[cols]), 0),
            model_predictions(self.old, self.e)[0],
            rtol=0,
            atol=1e-10,
        )
        self.assertEqual(type(m).__name__, type(self.old["point"]).__name__)

    def test_archived_control_is_exact_and_probability_method_constant(self):
        np.testing.assert_allclose(
            self.b["point"].predict(self.e[self.b["features"]]),
            self.old["point"].predict(self.e[self.b["features"]]),
        )
        self.assertEqual(self.b["probability_method"], P["probability_method"])
        self.assertLess(
            pd.Timestamp(self.b["information_available_at"]), self.e.prediction_at.min()
        )

    def test_calibrated_bounds_are_quantiles_of_same_cdf(self):
        for ab in [[1, 0], [0.25, -3], [0.25, 3], [4, 3]]:
            b = copy.deepcopy(self.b)
            b["calibrator"].ab = np.array(ab)
            curve = cdf(b, self.e)
            lo, hi = bounds(b, self.e)
            for q, level in [(lo, 0.05), (hi, 0.95)]:
                self.assertTrue((curve(q) >= level - 1e-9).all())
                self.assertTrue((curve(q - 1) < level + 1e-9).all())
            self.assertTrue((lo >= 0).all())
            self.assertTrue((hi >= lo).all())
            np.testing.assert_allclose(
                outcomes(curve, np.repeat(2.0, len(self.e))).sum(axis=1), 1
            )

    def test_signed_support_and_tail_limits(self):
        b = copy.deepcopy(self.b)
        b["count"] = False
        curve = cdf(b, self.e)
        self.assertTrue((curve(-2) > 0).all())
        self.assertTrue((curve(-1e6) < 1e-5).all())
        self.assertTrue((curve(1e6) > 1 - 1e-5).all())

    def test_outer_labels_do_not_change_fitted_metadata_or_calibration(self):
        changed = self.d.copy()
        changed.loc[changed.season.eq(2022), "y"] = 999999
        b, info, *_ = fit(changed, "passing_attempts", 2022, "b1_none", P, self.old)
        self.assertEqual(info, self.info)
        np.testing.assert_allclose(b["calibrator"].ab, self.b["calibrator"].ab)

    def test_outer_outcomes_cannot_select_context_backbone(self):
        a, info, *_ = fit(self.d, "passing_attempts", 2022, "b1_context", P, self.old)
        changed = self.d.copy()
        changed.loc[changed.season.eq(2022), "y"] = 999999
        b, other, *_ = fit(changed, "passing_attempts", 2022, "b1_context", P, self.old)
        self.assertEqual(info, other)
        np.testing.assert_allclose(
            a["point"].predict(self.e[a["features"]]),
            b["point"].predict(self.e[b["features"]]),
        )
        np.testing.assert_allclose(a["calibrator"].ab, b["calibrator"].ab)

    def test_diagnostic_window_guard_rejects_outer_year(self):
        with self.assertRaises(ValueError):
            feature_diagnostics(self.b, self.train, self.e, P)

    def test_permutation_preserves_fixture_side_and_is_deterministic(self):
        from stage1c1.data import CONTEXTS

        cols = feature_columns("passing_attempts") + CONTEXTS["c1_c2"]
        groups = self.sel.groupby(["game_id", "team_key", "kind"]).groups

        class Checked:
            def predict(obj, x):
                for idx in groups.values():
                    assert x.loc[idx, CONTEXTS["c1_c2"]].nunique().le(1).all()
                return np.zeros(len(x))

        b = {**self.b, "point": Checked(), "features": cols, "context": "c1_c2"}
        r, red, w = feature_diagnostics(b, self.train, self.sel, P)
        r2, _, _ = feature_diagnostics(b, self.train, self.sel, P)
        self.assertEqual(r, r2)
        self.assertEqual(len(r), 10)
        self.assertTrue(all(x["window"] == "prior_year_weeks11to18_ONLY" for x in r))

    def test_oracle_strawman_only_uses_prior_information(self):
        from stage1c1.oracles import build

        e = self.e[self.e.game_id.eq("2022-1")].copy()
        e["market"] = "passing_attempts"
        e["row_id"] = e.market + "|" + e.player_id + "|" + e.game_id
        first = build(e, self.src, self.games, self.rates, self.context)
        changed = self.src.copy()
        changed.loc[changed.season.eq(2022), "attempts"] = 999
        second = build(e, changed, self.games, self.rates, self.context)
        np.testing.assert_allclose(
            first[["T_hat", "S_hat", "E_hat"]], second[["T_hat", "S_hat", "E_hat"]]
        )
        self.assertTrue(first.historical_information_max.lt(first.prediction_at).all())
        self.assertTrue(first.team_information_max.lt(first.prediction_at).all())
        self.assertFalse(first.candidate_forecast.any())
        np.testing.assert_allclose(first.corner_15, first.y)
        np.testing.assert_allclose(
            first.shapley_efficiency_error_reduction, 0, atol=1e-10
        )

    def test_c0_thin_selection_does_not_admit_new_method(self):
        initial, sel, train, *_ = phases(self.d, 2022, P)
        sel = sel[sel.week.le(4)]
        m, name, records = choose(
            initial,
            sel,
            train,
            "passing_attempts",
            feature_columns("passing_attempts"),
            "c0",
            P,
        )
        self.assertEqual(name, "career_mean")


class EvidenceTests(unittest.TestCase):
    def test_effective_sample_size_uses_sum_squared_weights(self):
        src, g, r = data()
        g = g[(g.season == 2019) & g.week.le(4)].copy()
        r = r[r.game_id.isin(g.game_id)].copy()
        r.loc[
            r.game_id.eq("2019-2") & r.kind.eq("pass"),
            ["passing_yards", "attempts", "completions"],
        ] = np.nan
        ctx = states(g, r)
        d = effective_samples(g, r, ctx)
        x = d[(d.game_id == "2019-4") & d.team.eq("BUF") & d.kind.eq("pass")].iloc[0]
        self.assertAlmostEqual(x.weighted_games, 1.81)
        self.assertAlmostEqual(x.kish_game_ess, 1.81**2 / (1 + 0.81**2))
        self.assertEqual(x.known_games, 2)
        self.assertEqual(x.total_games, 3)

    def test_factorial_interaction_is_paired_not_unrelated_means(self):
        from stage1c1.metrics import paired

        frames = []
        probes = []
        levels = {
            "b1_none": 2.0,
            "c0_none": 3.0,
            "b1_context": 1.5,
            "c0_context": 2.8,
            "b1_context_legacy": 2.0,
            "b1_context_fixed": 2.0,
            "b1_c1": 2.0,
            "b1_c2": 2.0,
            "frozen_b1": 2.0,
        }
        for version, value in levels.items():
            for week in range(1, 9):
                key = str(week)
                frames.append(
                    dict(
                        row_id=key,
                        version=version,
                        market="passing_yards",
                        season=2022,
                        week=week,
                        evaluation_tier="development_oos",
                        position="QB",
                        y=1.0,
                        projection=value,
                        interval_score=3.0,
                    )
                )
                for i in range(3):
                    probes.append(
                        dict(
                            row_id=key, version=version, brier=0.25, log_loss=np.log(2)
                        )
                    )
        result = paired(
            pd.DataFrame(frames), pd.DataFrame(probes), {**P, "bootstrap_replicates": 5}
        )
        row = result[
            (result.variant == "factorial_interaction")
            & (result.metric == "absolute_error")
            & (result.week_block == 4)
        ].iloc[0]
        self.assertAlmostEqual(row.delta, -0.3)

    def test_primary_secondary_and_fixed_method_are_registered(self):
        self.assertEqual(len(P["variants"]), 8)
        self.assertIn("RB receiving_yards", P["secondary"])
        self.assertEqual(P["prediction_lead_hours"], 1)
        self.assertEqual(P["final_week"], 11)
        self.assertFalse(any("injury" in k or "allocation" in k for k in P["variants"]))


if __name__ == "__main__":
    unittest.main()
