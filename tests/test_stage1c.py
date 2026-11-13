"""Synthetic fixtures test research mechanics, not authentic betting returns."""

import json
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from stage1c.contracts import team, availability, effective_identity, assert_development
from stage1c.context import states, attach, FixtureStates, FAMILIES
from stage1c.inputs import aggregate_pbp, position_aggregates
from stage1c.models import fit, curve
from stage1c.runner import evaluate
from stage1b.data import prepare_panel, market_panel
from stage1b.probability import outcomes
from test_stage1b import fixture

ROOT = Path(__file__).resolve().parents[1]
P = json.loads((ROOT / "stage1c/protocol.json").read_text())


def data():
    src = fixture()
    src["team"] = "BUF"
    src["opponent_team"] = "MIA"
    games = []
    rates = []
    for r in src.drop_duplicates("game_id").itertuples():
        for t, o, sgn in [("BUF", "MIA", 1), ("MIA", "BUF", -1)]:
            games.append(
                dict(
                    game_id=r.game_id,
                    team=t,
                    opponent=o,
                    season=r.season,
                    week=r.week,
                    kickoff_at=r.kickoff_at,
                    completed_at=r.completed_at,
                    is_home=int(t == "BUF"),
                    plays=60.0 + r.week % 3,
                    dropbacks=35.0,
                    rushes=25.0,
                    no_huddle=4.0,
                    pace_sum=560.0,
                    pace_n=20.0,
                    points_for=22.0 + sgn * 2,
                    points_against=22.0 - sgn * 2,
                    margin=sgn * 4.0,
                )
            )
            for kind in ["pass", "rush_QB", "rush_RB", "rec_RB", "rec_WR", "rec_TE"]:
                rates.append(
                    dict(
                        game_id=r.game_id,
                        team=t,
                        kind=kind,
                        passing_yards=200.0,
                        attempts=30.0,
                        completions=20.0,
                        rushing_yards=60.0,
                        carries=15.0,
                        receiving_yards=100.0,
                        targets=20.0,
                        receptions=10.0,
                    )
                )
    return src, pd.DataFrame(games), pd.DataFrame(rates)


class ContractTests(unittest.TestCase):
    def test_aliases_and_unknown_ids(self):
        self.assertEqual(team("OAK"), "LV")
        self.assertEqual(team("LAR"), "LA")
        with self.assertRaises(ValueError):
            team("UNKNOWN")

    def test_availability_is_not_kickoff_and_postseason_source_refused(self):
        r = dict(
            kickoff_at="2021-09-05T17:00Z",
            completed_at="2021-09-06T01:00Z",
            evidence_tier="retrospective",
        )
        self.assertEqual(availability(r), pd.Timestamp("2021-09-07T05:00Z"))
        with self.assertRaises(ValueError):
            availability({**r, "release_policy": "postseason_only"})
        with self.assertRaises(ValueError):
            availability(r, lag_hours=1)
        with self.assertRaises(ValueError):
            availability({**r, "completed_at": "2021-09-05T18:00Z"})

    def test_verified_requires_actual_receipt_and_source(self):
        r = dict(
            kickoff_at="2021-09-05T17:00Z",
            completed_at="2021-09-06T01:00Z",
            evidence_tier="verified_predecision",
            source_sha256="a" * 64,
            published_at="2021-09-06T08:00Z",
            captured_at="2021-09-06T09:00Z",
        )
        self.assertEqual(availability(r, verified=True), pd.Timestamp(r["captured_at"]))
        with self.assertRaises(ValueError):
            availability({**r, "captured_at": "2021-09-06 09:00"}, verified=True)
        with self.assertRaises(ValueError):
            availability({**r, "source_sha256": ""}, verified=True)
        with self.assertRaises(ValueError):
            availability(r)

    def test_effective_identity_does_not_backfill_current_team(self):
        r = pd.DataFrame(
            [
                dict(
                    player_id="p",
                    team="BUF",
                    valid_from="2021-01-01T00:00Z",
                    valid_to="2021-10-01T00:00Z",
                    available_at="2021-01-01T00:00Z",
                ),
                dict(
                    player_id="p",
                    team="MIA",
                    valid_from="2021-10-01T00:00Z",
                    valid_to=None,
                    available_at="2021-10-01T01:00Z",
                ),
            ]
        )
        self.assertEqual(effective_identity(r, "p", "2021-09-01T00:00Z"), "BUF")
        with self.assertRaises(ValueError):
            effective_identity(r, "p", "2021-10-01T00:30Z")
        self.assertEqual(effective_identity(r, "p", "2021-10-02T00:00Z"), "MIA")

    def test_sealed_by_season_week_and_date(self):
        for r in [
            dict(season=2026, week=11),
            dict(season=2027, week=1),
            dict(season=2026, week=10, kickoff_at=pd.Timestamp("2026-11-20T00:00Z")),
        ]:
            with self.assertRaises(ValueError):
                assert_development(pd.DataFrame([r]))

    def test_partial_positional_totals_are_unknown_not_zero(self):
        stats = [
            "passing_yards",
            "attempts",
            "completions",
            "rushing_yards",
            "carries",
            "receiving_yards",
            "targets",
            "receptions",
        ]
        rows = []
        for observed in [True, False]:
            r = dict(game_id="g", team="BUF", position="WR", stats_observed=observed)
            r.update({x: 1.0 if observed else np.nan for x in stats})
            r.update({"team_total_" + x: 20.0 for x in stats})
            rows.append(r)
        result = position_aggregates(pd.DataFrame(rows)).set_index("kind")
        self.assertTrue(result.loc["rec_WR", stats].isna().all())
        self.assertFalse(result.loc["rec_WR", "known_complete"])
        self.assertTrue(result.loc["pass", "known_complete"])
        self.assertEqual(result.loc["pass", "attempts"], 20)

    def test_pace_manual_and_not_wall_clock(self):
        d = pd.DataFrame(
            [
                dict(
                    game_id="g",
                    play_id=i,
                    season=2021,
                    week=1,
                    posteam="BUF",
                    defteam="MIA",
                    play_type="pass",
                    two_point_attempt=0,
                    qb_dropback=1,
                    rush_attempt=0,
                    half_seconds_remaining=c,
                    drive=1,
                    qtr=1,
                    score_differential=0,
                    no_huddle=0,
                    home_score=24,
                    away_score=20,
                )
                for i, c in enumerate([900, 870, 845])
            ]
        )
        r = aggregate_pbp(d).iloc[0]
        self.assertEqual(r.plays, 3)
        self.assertEqual(r.pace_sum, 55)
        self.assertEqual(r.pace_n, 2)
        with self.assertRaises(ValueError):
            aggregate_pbp(pd.concat([d, d.iloc[:1]]))


class FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src, cls.games, cls.rates = data()
        cls.ctx = states(cls.games, cls.rates)

    def test_current_and_future_outcomes_do_not_change_entering_state(self):
        changed = self.games.copy()
        changed.loc[changed.season >= 2022, ["plays", "points_for", "margin"]] = 99999
        rates = self.rates.copy()
        rates.loc[
            rates.game_id.str.startswith("2022"),
            ["passing_yards", "attempts", "receiving_yards"],
        ] = 99999
        new = states(changed, rates)
        old = self.ctx.query("game_id=='2022-1'").reset_index(drop=True)
        new = new.query("game_id=='2022-1'").reset_index(drop=True)
        pd.testing.assert_frame_equal(old, new)

    def test_upcoming_fixture_needs_no_same_game_outcomes(self):
        history = self.games[(self.games.season == 2019) & (self.games.week == 1)]
        future = self.games[(self.games.season == 2019) & (self.games.week == 2)]
        future = future[
            ["game_id", "team", "opponent", "season", "week", "kickoff_at", "is_home"]
        ]
        out = states(history, self.rates, fixtures=future)
        expected = self.ctx.query("game_id=='2019-2'")
        keys = ["game_id", "team", "kind"]
        pd.testing.assert_frame_equal(
            out.sort_values(keys).reset_index(drop=True),
            expected.sort_values(keys).reset_index(drop=True),
        )

    def test_latest_eligible_game_bye_and_season_boundary(self):
        g = self.games[self.games.season.eq(2021)].copy()
        r = self.rates[self.rates.game_id.isin(g.game_id)]
        g = g[~g.week.eq(2)]
        c = states(g, r)
        d = c.query("game_id=='2021-3' and team=='BUF' and kind=='pass'").iloc[0]
        self.assertAlmostEqual(d.def_history_games, 1.0)
        self.assertLess(d.context_information_at, d.prediction_at)
        d = self.ctx.query("game_id=='2022-1' and team=='BUF' and kind=='pass'").iloc[0]
        self.assertGreater(d.def_history_games, 0)

    def test_delay_cannot_admit_unpublished_game(self):
        c = states(self.games, self.rates, lag_hours=200)
        d = c.query("game_id=='2019-2' and team=='BUF' and kind=='pass'").iloc[0]
        self.assertEqual(d.def_history_games, 0)

    def test_batch_order_invariant_and_duplicate_rejected(self):
        x = states(self.games.sample(frac=1, random_state=1), self.rates)
        cols = ["game_id", "team", "kind"]
        pd.testing.assert_frame_equal(
            self.ctx.sort_values(cols).reset_index(drop=True),
            x.sort_values(cols).reset_index(drop=True),
            check_exact=False,
            atol=1e-12,
            rtol=1e-12,
        )
        with self.assertRaises(ValueError):
            states(pd.concat([self.games, self.games.iloc[:1]]), self.rates)

    def test_shrinkage_hand_computation_and_schedule_entering_expectation(self):
        g = self.games[(self.games.season == 2019) & (self.games.week == 1)].copy()
        g["available_at_proxy"] = g.completed_at
        s = FixtureStates()
        mapping = {
            (r.game_id, r.team, r.kind): r._asdict()
            for r in self.rates.itertuples(index=False)
        }
        s.update_batch(g, mapping)
        d = s.defence_row("BUF", "pass")
        self.assertAlmostEqual(
            d["def_efficiency"],
            (200 + 100 * ((400 + 100 * 7) / (60 + 100))) / (30 + 100),
        )
        self.assertAlmostEqual(d["def_schedule_delta"], (200 - 7 * 30) / (30 + 100))
        self.assertGreater(d["def_known_fraction"], 0)

    def test_missing_positional_outcomes_do_not_become_zeros(self):
        rates = self.rates.copy()
        rates.loc[
            rates.kind.eq("rec_TE"), ["receiving_yards", "targets", "receptions"]
        ] = np.nan
        c = states(self.games, rates)
        d = c.query("game_id=='2022-1' and team=='BUF' and kind=='rec_TE'").iloc[0]
        self.assertEqual(d.def_history_games, 0)
        self.assertEqual(d.def_known_fraction, 0)
        self.assertGreater(d.def_opportunities, 0)

    def test_scenarios_partition_and_no_book_information(self):
        np.testing.assert_allclose(
            self.ctx[["script_trailing", "script_close", "script_leading"]].sum(axis=1),
            1,
        )
        self.assertTrue(self.ctx.expected_plays.gt(0).all())
        self.assertTrue(self.ctx.expected_dropback_share.between(0, 1).all())
        self.assertTrue(self.ctx.evidence_tier.eq("retrospective").all())
        self.assertFalse(
            any("spread" in c or "coverage" in c or "injury" in c for c in self.ctx)
        )
        for cols in FAMILIES.values():
            self.assertEqual(len(cols), len(set(cols)))

    def test_all_player_rows_attach_and_missing_fixture_fails(self):
        d = market_panel(prepare_panel(self.src, P), "passing_yards")
        x = attach(d, self.ctx, "passing_yards")
        self.assertEqual(len(x), len(d))
        with self.assertRaises(ValueError):
            attach(d, self.ctx[self.ctx.game_id != "2022-1"], "passing_yards")


class ForecastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src, games, rates = data()
        cls.d = attach(
            market_panel(prepare_panel(src, P), "passing_attempts"),
            states(games, rates),
            "passing_attempts",
        )
        cls.b, cls.info, cls.e = fit(cls.d, "passing_attempts", 2022, "c1_c2", P)

    def test_outer_labels_cannot_choose_model_or_calibration(self):
        d = self.d.copy()
        d.loc[d.season.eq(2022), "y"] = 999999
        _, info, _ = fit(d, "passing_attempts", 2022, "c1_c2", P)
        self.assertEqual(self.info, info)

    def test_thin_selection_window_cannot_pass_bootstrap_superiority_gate(self):
        d = self.d[~(self.d.season.eq(2021) & self.d.week.gt(14))]
        b, info, _ = fit(d, "passing_attempts", 2022, "c1_c2", P)
        self.assertEqual(b["selected_probability"], "normal|identity")
        self.assertTrue(
            all(
                not r["accepted"]
                for r in info["probability_candidates"]
                if r["key"] != "normal|identity"
            )
        )

    def test_thin_point_window_retains_naive(self):
        d = self.d[~(self.d.season.eq(2020) & self.d.week.gt(4))]
        b, info, _ = fit(d, "passing_attempts", 2022, "c1_c2", P)
        self.assertEqual(b["point_method"], "career_mean")

    def test_support_intervals_zeroes_and_probes(self):
        f, q = evaluate(self.b, self.e, P)
        self.assertGreater(f.y.eq(0).sum(), 0)
        self.assertTrue(f.lower90.ge(0).all())
        self.assertTrue(f.lower90.le(f.upper90).all())
        cdf = curve(self.b, self.e, self.b["selected_probability"])
        p = outcomes(cdf, np.repeat(2.0, len(self.e)))
        np.testing.assert_allclose(p.sum(axis=1), 1)
        self.assertTrue((p >= 0).all())
        self.assertTrue((cdf(-1) == 0).all())
        self.assertEqual(len(q), len(f) * 3)
        self.assertLess(pd.Timestamp(self.info["selection_max"]), f.prediction_at.min())


if __name__ == "__main__":
    unittest.main()
