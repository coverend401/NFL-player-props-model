"""Retrospective data coverage and honest predecision availability audits only."""

import pandas as pd
import numpy as np
from stage1c2_stage1.contracts import COUNT_FIELDS, classify_count


def histories(players, source):
    keys = ["game_id", "team", "player_id"]
    s = source[
        keys + ["season", "week", "kickoff_at", "completed_at", "player_display_name"]
    ]
    d = players.merge(s, on=keys, validate="one_to_one")
    records, overlay = [], []
    for field in COUNT_FIELDS:
        z = d[
            keys
            + [
                "season",
                "week",
                "position",
                "offense_pct",
                "stats_observed",
                "kickoff_at",
                "completed_at",
                "player_display_name",
            ]
        ].copy()
        z["field"] = field
        z["original_value"] = d[field + "_official"]
        z["event_value"] = d[field + "_event_validated"]
        z["ledger_strict"] = d[field + "_strict"]
        z["participation_established"] = d.offense_pct.gt(0)
        z["classification"] = [
            classify_count(
                bool(obs) if pd.notna(obs) else False, part, val, bool(strict), event
            )
            for obs, part, val, strict, event in zip(
                d.stats_observed,
                z.participation_established,
                z.original_value,
                z.ledger_strict,
                z.event_value,
            )
        ]
        records.append(z)
        keep = z.classification.isin(
            ["ledger_confirmed_zero", "ledger_recovered_positive"]
        )
        x = z[keep].copy()
        x["value"] = x.event_value
        x["usable_at_retrospective_proxy"] = pd.concat(
            [
                pd.to_datetime(x.kickoff_at, utc=True) + pd.Timedelta(hours=36),
                pd.to_datetime(x.completed_at, utc=True),
            ],
            axis=1,
        ).max(axis=1)
        x["usable_at_verified"] = pd.Series(
            pd.NaT, index=x.index, dtype="datetime64[ns, UTC]"
        )
        x["evidence_tier"] = "retrospective_internal_reconciliation"
        overlay.append(x)
    return pd.concat(records, ignore_index=True), pd.concat(overlay, ignore_index=True)


def roster_audit(rosters, injuries, source, games, scored):
    key = ["season", "week", "team", "gsis_id"]
    r = rosters.copy()
    r["ambiguous"] = r.duplicated(key, keep=False) | r.gsis_id.isna() | r.team.isna()
    clean = r[~r.ambiguous]
    participants = source[source.offense_pct.gt(0)].rename(
        columns={"player_id": "gsis_id"}
    )
    matches = participants.merge(
        clean,
        on=key,
        how="left",
        suffixes=("", "_roster"),
        validate="many_to_one",
        indicator=True,
    )
    matches["present_in_retrospective_roster"] = matches._merge.eq("both")
    matches["retrospective_active"] = matches.status.eq("ACT")
    # Current historical weekly snapshots have no archived original row/status
    # versions with receipt/publication provenance. Never convert ACT/INA to T-60.
    matches["verified_predecision_membership"] = False
    matches["verified_predecision_inactive"] = False
    summary = []
    lookup = dict(tuple(clean.groupby(["season", "week", "team"])))
    part = dict(tuple(matches.groupby(["game_id", "team"])))
    injury_lookup = dict(tuple(injuries.groupby(["season", "week", "team"])))
    for g in games.itertuples():
        rr = lookup.get((g.season, g.week, g.team), clean.iloc[:0])
        pp = part.get((g.game_id, g.team), matches.iloc[:0])
        ii = injury_lookup.get((g.season, g.week, g.team), injuries.iloc[:0])
        cutoff = pd.Timestamp(g.kickoff_at) - pd.Timedelta(hours=1)
        dated = pd.to_datetime(ii.date_modified, utc=True, errors="coerce")
        summary.append(
            dict(
                game_id=g.game_id,
                team=g.team,
                season=g.season,
                week=g.week,
                prediction_at=cutoff,
                roster_rows=len(rr),
                retrospective_ACT=int(rr.status.eq("ACT").sum()),
                retrospective_INA=int(rr.status.eq("INA").sum()),
                offensive_participants=len(pp),
                participants_matched=int(pp.present_in_retrospective_roster.sum()),
                participants_not_ACT=int(
                    (
                        pp.present_in_retrospective_roster & ~pp.retrospective_active
                    ).sum()
                ),
                injury_rows=len(ii),
                injury_publisher_claim_before_cutoff=int((dated < cutoff).sum()),
                injury_Out_claim_before_cutoff=int(
                    ((dated < cutoff) & ii.report_status.eq("Out")).sum()
                ),
                verified_complete_pregame_universe=False,
                verified_complete_inactive_list=False,
                reason="weekly_snapshot_no_archived_row_publication_or_receipt_history",
            )
        )
    summary = pd.DataFrame(summary)
    # Frozen forecasts have no team column; attach exact historical source IDs.
    eval_source = source[["game_id", "player_id", "team"]]
    f = scored.merge(
        eval_source, on=["game_id", "player_id"], how="left", validate="many_to_one"
    )
    f = f.merge(
        summary[
            [
                "game_id",
                "team",
                "verified_complete_pregame_universe",
                "verified_complete_inactive_list",
            ]
        ],
        on=["game_id", "team"],
        validate="many_to_one",
    )
    f["feasible_verified_share_state"] = (
        f.verified_complete_pregame_universe & f.verified_complete_inactive_list
    )
    return r, matches, summary, f


def snap_audit(snaps, rosters, source, raw_box, team_audit, identities=None):
    key = ["season", "week", "team", "pfr_id"]
    r = rosters[rosters.pfr_id.notna() & rosters.gsis_id.notna()].copy()
    # No name-only or cross-season ID guessing.
    ambiguous = r.duplicated(key, keep=False)
    unique = r[~ambiguous][key + ["gsis_id"]]
    z = snaps.rename(columns={"pfr_player_id": "pfr_id"}).merge(
        unique, on=key, how="left", validate="many_to_one"
    )
    z["identity_method"] = np.where(
        z.gsis_id.notna(), "same_week_retrospective_roster", "unresolved"
    )
    z["identity_conflict"] = False
    if identities is not None:
        pairs = identities[["pfr_id", "gsis_id"]].dropna().drop_duplicates()
        bad = pairs.pfr_id.duplicated(keep=False)
        mapping = pairs[~bad].set_index("pfr_id").gsis_id
        static = z.pfr_id.map(mapping)
        conflict = z.gsis_id.notna() & static.notna() & z.gsis_id.ne(static)
        use = z.gsis_id.isna() & static.notna()
        z.loc[use, "gsis_id"] = static[use]
        z.loc[use, "identity_method"] = "static_ID_crosswalk_discovered_retrospectively"
        z.loc[conflict, "gsis_id"] = None
        z.loc[conflict, "identity_method"] = "conflicting_ID_sources"
        z.loc[conflict, "identity_conflict"] = True
    z["any_participation"] = (
        z[["offense_snaps", "defense_snaps", "st_snaps"]].gt(0).any(axis=1)
    )
    z["special_teams_only"] = (
        z.st_snaps.gt(0) & z.offense_snaps.eq(0) & z.defense_snaps.eq(0)
    )
    z = z.rename(columns={"gsis_id": "player_id"})
    skeys = ["game_id", "team", "player_id"]
    seen = source[skeys].assign(in_frozen_features=True)
    z = z.merge(seen, on=skeys, how="left", validate="many_to_one")
    z["in_frozen_features"] = z.in_frozen_features.astype("boolean")
    box = raw_box[skeys + COUNT_FIELDS]
    if box.duplicated(skeys).any():
        raise ValueError("Ambiguous raw box identity")
    z = z.merge(box, on=skeys, how="left", validate="many_to_one")
    z = z.merge(
        team_audit[["game_id", "team"] + [f + "_strict" for f in COUNT_FIELDS]],
        on=["game_id", "team"],
        how="left",
        validate="many_to_one",
    )
    z["identity_unresolved"] = z.player_id.isna()
    z["absent_from_frozen_features"] = (
        z.player_id.notna() & ~z.in_frozen_features.fillna(False).astype(bool)
    )
    z["identity_review_required_for_new_history"] = z.absent_from_frozen_features
    for field in COUNT_FIELDS:
        positive_box = z[field].gt(0)
        z[field + "_supported_zero_candidate"] = (
            z.absent_from_frozen_features
            & z.any_participation
            & z.player_id.notna()
            & z[field + "_strict"].fillna(False).astype(bool)
            & ~positive_box
        )
    z["evidence_tier"] = "retrospective_snaps_and_weekly_identity_not_pregame_verified"
    return z, int(ambiguous.sum())
