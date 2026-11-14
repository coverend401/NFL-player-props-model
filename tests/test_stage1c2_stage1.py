"""Data-only mechanics. Synthetic fixtures are not historical evidence."""

import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd
from stage1c1.reconcile import COLS
from stage1c2_stage1.contracts import (
    classify_count,
    predecision_verified,
    bounded_read,
    check_count_ledger,
)
from stage1c2_stage1.credits import repair
from stage1c2_stage1.audit import roster_audit, snap_audit

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "research_inputs/stage1c2/data-quality-20261114-v6"


def event():
    row = {x: np.nan for x in COLS}
    row.update(
        game_id="2024_15_MIA_HOU",
        season=2024,
        week=15,
        play_id=2274,
        posteam="HOU",
        play_type="no_play",
        play_deleted=0,
        two_point_attempt=0,
        pass_attempt=0,
        rush_attempt=1,
        sack=0,
        complete_pass=0,
        incomplete_pass=0,
        rusher_player_id="p",
        rushing_yards=35,
        desc="run for 35 yards; reviewed reversed",
    )
    s = pd.DataFrame(
        [
            dict(
                game_id=row["game_id"],
                team="HOU",
                player_id="p",
                player_display_name="Player",
            )
        ]
    )
    spec = dict(
        event_inclusions=[
            dict(
                game_id=row["game_id"],
                play_id=2274,
                team="HOU",
                actor="p",
                type="run",
                stat="carries",
                yard_stat="rushing_yards",
                yards=35,
                fragments=["run for 35 yards", "reviewed reversed"],
            )
        ],
        missing_lateral_credits=[],
    )
    return pd.DataFrame([row]), s, spec


class CountContractTests(unittest.TestCase):
    def test_missing_box_is_not_zero(self):
        self.assertEqual(
            classify_count(False, True, np.nan, False, 0), "missing_unknown"
        )
        self.assertEqual(
            classify_count(False, False, np.nan, True, 0), "missing_unknown"
        )
        self.assertEqual(
            classify_count(False, True, np.nan, True, np.nan), "missing_unknown"
        )

    def test_supported_counts_and_invalid_counts(self):
        self.assertEqual(
            classify_count(False, True, np.nan, True, 0), "ledger_confirmed_zero"
        )
        self.assertEqual(
            classify_count(False, True, np.nan, True, 2), "ledger_recovered_positive"
        )
        self.assertEqual(classify_count(True, True, 0, True, 0), "observed_zero")
        self.assertEqual(classify_count(True, True, -1, True, -1), "invalid_count")

    def test_status_or_publisher_time_alone_does_not_prove_asof(self):
        cutoff = "2024-09-08T16:00Z"
        self.assertFalse(
            predecision_verified(
                dict(status="ACT", published_at="2024-09-06T10:00Z"), cutoff
            )
        )
        e = dict(
            published_at="2024-09-06T10:00Z",
            received_at="2024-09-06T10:01Z",
            version_archived_at="2024-09-06T10:02Z",
            row_content_bound=True,
            official_predecision_status=True,
        )
        self.assertTrue(predecision_verified(e, cutoff))
        self.assertFalse(
            predecision_verified({**e, "published_at": "2024-09-06T10:00"}, cutoff)
        )
        self.assertFalse(predecision_verified(e, "2024-09-08T16:00"))
        self.assertFalse(
            predecision_verified({**e, "received_at": "2024-09-08T16:01Z"}, cutoff)
        )
        self.assertFalse(
            predecision_verified({**e, "version_archived_at": None}, cutoff)
        )

    def test_pushdown_removes_final_week_and_future_seasons(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "r.parquet"
            pd.DataFrame(
                dict(
                    season=[2025, 2026, 2026, 2027],
                    week=[18, 10, 11, 1],
                    game_type=["REG"] * 4,
                    team=["HOU"] * 4,
                )
            ).to_parquet(p, index=False)
            d = bounded_read(p, ["season", "week", "game_type", "team"])
            self.assertEqual(list(zip(d.season, d.week)), [(2025, 18), (2026, 10)])

    def test_absent_injury_timestamp_remains_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "r.parquet"
            pd.DataFrame(
                dict(season=[2025], week=[1], game_type=["REG"], team=["JAC"])
            ).to_parquet(p, index=False)
            d = bounded_read(
                p, ["season", "week", "game_type", "team", "date_modified"]
            )
            self.assertTrue(d.date_modified.isna().all())
            self.assertEqual(d.team.iloc[0], "JAX")
            with self.assertRaisesRegex(ValueError, "Required source"):
                bounded_read(p, ["season", "week", "game_type", "team", "gsis_id"])

    def test_overlay_cannot_be_promoted_to_verified(self):
        d = pd.DataFrame(
            [
                dict(
                    game_id="2024_01_BUF_MIA",
                    team="BUF",
                    player_id="p",
                    field="targets",
                    season=2024,
                    week=1,
                    value=0,
                    evidence_tier="retrospective_internal_reconciliation",
                    usable_at_verified=pd.NaT,
                )
            ]
        )
        check_count_ledger(d)
        with self.assertRaisesRegex(ValueError, "archived historical"):
            check_count_ledger(
                d.assign(usable_at_verified=pd.Timestamp("2024-09-01T00:00Z"))
            )
        with self.assertRaisesRegex(ValueError, "Invalid recovered"):
            check_count_ledger(d.assign(value=-1))


class CreditTests(unittest.TestCase):
    def test_allowlisted_counted_no_play_only_and_no_source_mutation(self):
        d, s, p = event()
        original = d.copy(deep=True)
        other = d.iloc[0].copy()
        other.play_id = 999
        other.desc = "other no play"
        other.rushing_yards = 99
        d = pd.concat([d, pd.DataFrame([other])], ignore_index=True)
        c, _ = repair(d, s, p)
        self.assertEqual(c[c.stat.eq("carries")].value.sum(), 1)
        self.assertEqual(c[c.stat.eq("rushing_yards")].value.sum(), 35)
        pd.testing.assert_frame_equal(d.iloc[:1].reset_index(drop=True), original)

    def test_changed_description_actor_or_deleted_play_rejected(self):
        d, s, p = event()
        for field, value in [
            ("desc", "unrelated"),
            ("rusher_player_id", "other"),
            ("play_deleted", 1),
            ("two_point_attempt", 1),
        ]:
            with self.assertRaises(ValueError):
                repair(d.assign(**{field: value}), s, p)

    def test_lateral_yards_never_create_target_or_catch(self):
        d, s, p = event()
        d = d.assign(
            play_type="pass",
            pass_attempt=1,
            rush_attempt=0,
            complete_pass=1,
            passer_player_id="q",
            receiver_player_id="r",
            receiving_yards=5,
            passing_yards=2,
            lateral_receiver_player_id=None,
            lateral_receiving_yards=np.nan,
            desc="Lateral to p for -3 yards",
        )
        p = dict(
            event_inclusions=[],
            missing_lateral_credits=[
                dict(
                    game_id=d.game_id.iloc[0],
                    play_id=2274,
                    team="HOU",
                    actor="p",
                    value=-3,
                    segments=[-3],
                    fragments=["Lateral to p for -3 yards"],
                )
            ],
        )
        c, _ = repair(d, s, p)
        added = c[c.player_id.eq("p")]
        self.assertEqual(added.stat.tolist(), ["receiving_yards"])
        self.assertEqual(added.value.tolist(), [-3.0])
        bad = copy.deepcopy(p)
        bad["missing_lateral_credits"][0]["value"] = -4
        with self.assertRaisesRegex(ValueError, "Invalid lateral"):
            repair(d, s, bad)
        with self.assertRaisesRegex(ValueError, "duplicate an already"):
            repair(d.assign(lateral_receiver_player_id="p"), s, p)


class AvailabilityAuditTests(unittest.TestCase):
    def test_retrospective_ACT_and_injury_Out_never_prove_cutoff_status(self):
        source = pd.DataFrame(
            [
                dict(
                    game_id="2024_01_BUF_MIA",
                    team="BUF",
                    player_id="p",
                    season=2024,
                    week=1,
                    offense_pct=0.5,
                )
            ]
        )
        roster = pd.DataFrame(
            [dict(season=2024, week=1, team="BUF", gsis_id="p", status="ACT")]
        )
        injuries = pd.DataFrame(
            [
                dict(
                    season=2024,
                    week=1,
                    team="BUF",
                    gsis_id="p",
                    report_status="Out",
                    date_modified=pd.Timestamp("2024-09-01T10:00Z"),
                )
            ]
        )
        games = pd.DataFrame(
            [
                dict(
                    game_id="2024_01_BUF_MIA",
                    team="BUF",
                    season=2024,
                    week=1,
                    kickoff_at=pd.Timestamp("2024-09-02T17:00Z"),
                )
            ]
        )
        f = pd.DataFrame([dict(game_id="2024_01_BUF_MIA", player_id="p", row_id="x")])
        _, m, c, e = roster_audit(roster, injuries, source, games, f)
        self.assertTrue(m.present_in_retrospective_roster.iloc[0])
        self.assertEqual(c.injury_Out_claim_before_cutoff.iloc[0], 1)
        self.assertFalse(e.feasible_verified_share_state.any())

    def test_special_teams_zero_count_needs_unambiguous_id_and_full_ledger(self):
        snaps = pd.DataFrame(
            [
                dict(
                    game_id="2024_01_BUF_MIA",
                    season=2024,
                    week=1,
                    team="BUF",
                    pfr_player_id="Pfr",
                    offense_snaps=0,
                    defense_snaps=0,
                    st_snaps=5,
                )
            ]
        )
        roster = pd.DataFrame(
            [dict(season=2024, week=1, team="BUF", pfr_id="Pfr", gsis_id="p")]
        )
        source = pd.DataFrame(
            [dict(game_id="2024_01_BUF_MIA", team="BUF", player_id="other")]
        )
        box = pd.DataFrame(
            [
                dict(
                    game_id="2024_01_BUF_MIA",
                    team="BUF",
                    player_id="p",
                    attempts=0,
                    carries=1,
                    targets=0,
                )
            ]
        )
        ledger = pd.DataFrame(
            [
                dict(
                    game_id="2024_01_BUF_MIA",
                    team="BUF",
                    attempts_strict=True,
                    carries_strict=True,
                    targets_strict=True,
                )
            ]
        )
        d, _ = snap_audit(snaps, roster, source, box, ledger)
        self.assertTrue(d.special_teams_only.iloc[0])
        self.assertTrue(d.targets_supported_zero_candidate.iloc[0])
        self.assertFalse(d.carries_supported_zero_candidate.iloc[0])
        duplicate = pd.concat(
            [roster, roster.assign(gsis_id="ambiguous")], ignore_index=True
        )
        d, amb = snap_audit(snaps, duplicate, source, box, ledger)
        self.assertEqual(amb, 2)
        self.assertFalse(d.targets_supported_zero_candidate.any())

    def test_static_ID_mapping_does_not_import_current_team_or_status(self):
        snaps = pd.DataFrame(
            [
                dict(
                    game_id="2024_01_BUF_MIA",
                    season=2024,
                    week=1,
                    team="BUF",
                    pfr_player_id="Pfr",
                    offense_snaps=2,
                    defense_snaps=0,
                    st_snaps=0,
                )
            ]
        )
        roster = pd.DataFrame(
            [dict(season=2024, week=1, team="BUF", pfr_id="Other", gsis_id="q")]
        )
        source = pd.DataFrame(
            [dict(game_id="2024_01_BUF_MIA", team="BUF", player_id="p")]
        )
        box = pd.DataFrame(
            [
                dict(
                    game_id="2024_01_BUF_MIA",
                    team="BUF",
                    player_id="p",
                    attempts=0,
                    carries=0,
                    targets=0,
                )
            ]
        )
        ledger = pd.DataFrame(
            [
                dict(
                    game_id="2024_01_BUF_MIA",
                    team="BUF",
                    attempts_strict=True,
                    carries_strict=True,
                    targets_strict=True,
                )
            ]
        )
        identities = pd.DataFrame(
            [
                dict(
                    pfr_id="Pfr",
                    gsis_id="p",
                    latest_team="DEN",
                    status="INA",
                    position="TE",
                )
            ]
        )
        d, _ = snap_audit(snaps, roster, source, box, ledger, identities)
        self.assertEqual(d.player_id.iloc[0], "p")
        self.assertEqual(d.team.iloc[0], "BUF")
        self.assertIn("retrospectively", d.identity_method.iloc[0])
        self.assertFalse(d.absent_from_frozen_features.iloc[0])
        conflict = roster.assign(pfr_id="Pfr")
        d, _ = snap_audit(snaps, conflict, source, box, ledger, identities)
        self.assertTrue(d.identity_conflict.iloc[0])
        self.assertTrue(d.identity_unresolved.iloc[0])
        self.assertFalse(d.absent_from_frozen_features.iloc[0])


@unittest.skipUnless(
    sys.version_info[:2] == (3, 14), "Exact archive runtime is Python 3.14"
)
class ArchiveTests(unittest.TestCase):
    def test_complete_data_audit_without_any_model(self):
        from stage1c2_stage1.validate import validate

        result = validate(ARCHIVE, ROOT)
        self.assertEqual(result["models_fitted"], 0)
        self.assertFalse(result["stage2_authorised"])
        self.assertEqual(result["player_market_games"], 55303)
        self.assertEqual(result["supported_internal_repairs"], 12)
        self.assertEqual(result["unresolved"], 5)

    def test_manifest_cannot_authorise_fitting(self):
        from stage1c2_stage1.validate import validate

        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "archive"
            shutil.copytree(ARCHIVE, d)
            p = d / "manifest.json"
            m = json.loads(p.read_text())
            m["stage2_authorised"] = True
            p.write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError, "Stage 2 is not authorised"):
                validate(d, ROOT)


if __name__ == "__main__":
    unittest.main()
