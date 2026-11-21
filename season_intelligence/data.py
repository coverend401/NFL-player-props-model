"""Point-in-time player workloads; no normalisation over eventual participants."""

import numpy as np
import pandas as pd

from scripts.forecast_features import observation_status, pregame_eligible
from stage1b.data import MARKETS
from stage1c.contracts import team as canonical_team
from weekly_learning.store import ROOT, sha

STATS = [
    "passing_yards",
    "attempts",
    "completions",
    "rushing_yards",
    "carries",
    "receiving_yards",
    "receptions",
    "targets",
    "offense_pct",
]
KEYS = ["game_id", "player_id"]
TEAM = [
    "own_plays",
    "own_attempts",
    "own_carries",
    "own_pass_rate",
    "own_pace",
    "opp_allowed_plays",
    "opp_allowed_attempts",
    "opp_allowed_carries",
    "opp_pass_rate",
    "own_margin",
    "opp_margin",
    "is_home",
]


def history_features(source):
    """Candidate's outcome cannot enter its own features. Missing snaps/boxes stay missing."""
    d = source.sort_values(["player_id", "kickoff_at"]).reset_index(drop=True).copy()
    d["kickoff_at"] = pd.to_datetime(d.kickoff_at, utc=True)
    d["prediction_at"] = d.kickoff_at - pd.Timedelta(minutes=60)
    available = pd.concat(
        [
            pd.to_datetime(d.completed_at, utc=True),
            d.kickoff_at + pd.Timedelta(hours=36),
        ],
        axis=1,
    ).max(axis=1)
    played = d.offense_pct.gt(0)
    h = d[played].copy()
    additions = {}
    for col in STATS:
        x = pd.to_numeric(h[col], errors="coerce")
        if col != "offense_pct":
            x = x.where(h.stats_observed.eq(True))
        g = x.groupby(h.player_id, sort=False)
        additions[col + "_career"] = g.expanding().mean().droplevel(0)
        additions[col + "_last3"] = g.rolling(3, min_periods=1).mean().droplevel(0)
        additions[col + "_last5"] = g.rolling(5, min_periods=1).mean().droplevel(0)
        additions[col + "_sd5"] = g.rolling(5, min_periods=2).std().droplevel(0)
        missing = x.isna().astype(int).groupby(h.player_id, sort=False)
        for n in [3, 5]:
            bad = missing.rolling(n, min_periods=1).sum().droplevel(0).gt(0)
            additions[col + f"_last{n}"] = additions[col + f"_last{n}"].mask(bad)
        sg = x.groupby([h.player_id, h.season], sort=False)
        additions[col + "_season"] = sg.expanding().mean().droplevel([0, 1])
        additions[col + "_season_n"] = sg.cumcount() + 1
    for opportunity, total in [
        ("attempts", "team_total_attempts"),
        ("carries", "team_total_carries"),
        ("targets", "team_total_targets"),
    ]:
        ratio = (h[opportunity] / h[total].replace(0, np.nan)).where(
            h.stats_observed.eq(True)
        )
        for n in [3, 5]:
            additions[opportunity + f"_share{n}"] = (
                ratio.groupby(h.player_id, sort=False)
                .rolling(n, min_periods=1)
                .mean()
                .droplevel(0)
            )
        additions[opportunity + "_share_sd5"] = (
            ratio.groupby(h.player_id, sort=False)
            .rolling(5, min_periods=2)
            .std()
            .droplevel(0)
        )
    additions["history_season"] = h.season
    additions["last_known_team"] = h.team
    additions["history_available_at"] = available.loc[h.index]
    additions["last_game_at"] = h.kickoff_at
    additions["history_n"] = h.groupby("player_id", sort=False).cumcount() + 1
    states = pd.DataFrame(additions, index=h.index)
    ix = pd.Series(d.index, index=d.index, dtype=float).where(played)
    ix = (
        ix.groupby(d.player_id, sort=False)
        .ffill()
        .groupby(d.player_id, sort=False)
        .shift(1)
    )
    aligned = states.reindex(ix.to_numpy()).set_axis(d.index)
    unavailable = pd.to_datetime(aligned.history_available_at, utc=True).ge(
        d.prediction_at
    )
    if unavailable.any():
        # Never impute a future value into history. An incomplete state is explicit.
        aligned.loc[unavailable] = np.nan
    result = pd.concat([d, aligned], axis=1)
    boundary = result.season.ne(result.history_season)
    for stat in STATS:
        result.loc[boundary, stat + "_season"] = np.nan
        result.loc[boundary, stat + "_season_n"] = 0
    result["days_rest"] = (
        result.kickoff_at - pd.to_datetime(result.last_game_at, utc=True)
    ).dt.total_seconds() / 86400
    result["known_team_continuity"] = result.team.eq(result.last_known_team).astype(
        float
    )
    result["role_snap_change"] = result.offense_pct_last3 - result.offense_pct_career
    return result


CERTIFIED = ROOT / "research_inference_releases/research-week11-frozen-20261120-r2"
FILTERS = [[("season", "<", 2026)], [("season", "==", 2026), ("week", "<", 11)]]


def team_features(source, requests=None):
    """Box-derived team counts refreshed through Week10; pace uses known PBP only."""
    source = source.copy()
    source["team"] = source.team.map(canonical_team)
    source["opponent_team"] = source.opponent_team.map(canonical_team)
    fields = ["team_total_attempts", "team_total_carries"]
    raw = (
        source[
            [
                "game_id",
                "team",
                "opponent_team",
                "season",
                "week",
                "kickoff_at",
                "completed_at",
            ]
            + fields
        ]
        .groupby(["game_id", "team"], as_index=False)
        .first()
        .copy()
    )
    raw["plays"] = raw.team_total_attempts + raw.team_total_carries
    qb = (
        source[source.position.eq("QB") & source.stats_observed.eq(True)]
        .groupby(["game_id", "team"])
        .agg(
            sacks=("sacks_suffered", lambda x: x.sum(min_count=1)),
            observed_attempts=("attempts", lambda x: x.sum(min_count=1)),
        )
    )
    raw = raw.merge(qb, on=["game_id", "team"], how="left", validate="one_to_one")
    raw["plays"] = (raw.plays + raw.sacks).where(
        raw.observed_attempts.eq(raw.team_total_attempts)
    )
    scores = pd.read_parquet(
        CERTIFIED / "schedule.parquet",
        filters=FILTERS,
        columns=["game_id", "home_team", "away_team", "home_score", "away_score"],
    )
    scores["home_team"] = scores.home_team.map(canonical_team)
    scores["away_team"] = scores.away_team.map(canonical_team)
    raw = raw.merge(scores, on="game_id", how="left", validate="many_to_one")
    raw["is_home"] = raw.team.eq(raw.home_team).astype(float)
    raw["margin"] = np.where(
        raw.is_home.eq(1),
        raw.home_score - raw.away_score,
        raw.away_score - raw.home_score,
    )
    pbp = pd.read_parquet(
        ROOT / "research_inputs/script_adjustment/pbp-20261121-v2/games.parquet"
    )
    pbp["pace"] = pbp.pace_sum / pbp.pace_n.replace(0, np.nan)
    raw = raw.merge(
        pbp[["game_id", "team", "pace"]],
        on=["game_id", "team"],
        how="left",
        validate="one_to_one",
    )
    opponent = raw[
        ["game_id", "team", "plays", "team_total_attempts", "team_total_carries"]
    ].rename(
        columns={
            "team": "opponent_team",
            "plays": "allowed_plays",
            "team_total_attempts": "allowed_attempts",
            "team_total_carries": "allowed_carries",
        }
    )
    raw = raw.merge(
        opponent, on=["game_id", "opponent_team"], how="left", validate="one_to_one"
    )
    raw["pass_rate"] = raw.team_total_attempts / (
        raw.team_total_attempts + raw.team_total_carries
    ).replace(0, np.nan)
    raw["kickoff_at"] = pd.to_datetime(raw.kickoff_at, utc=True)
    raw["available_at"] = pd.concat(
        [
            pd.to_datetime(raw.completed_at, utc=True),
            raw.kickoff_at + pd.Timedelta(hours=36),
        ],
        axis=1,
    ).max(axis=1)
    requests_frame = raw[["game_id", "team", "opponent_team", "kickoff_at", "is_home"]]
    if requests is not None:
        requests_frame = pd.concat(
            [requests_frame, requests[requests_frame.columns]], ignore_index=True
        ).drop_duplicates(["game_id", "team"])
    fields = {
        "plays": "plays",
        "attempts": "team_total_attempts",
        "carries": "team_total_carries",
        "pass_rate": "pass_rate",
        "pace": "pace",
        "allowed_plays": "allowed_plays",
        "allowed_attempts": "allowed_attempts",
        "allowed_carries": "allowed_carries",
        "margin": "margin",
    }
    updates = raw.sort_values("available_at").to_dict("records")
    known = {}
    i = 0
    rows = []
    for r in requests_frame.sort_values(["kickoff_at", "team"]).to_dict("records"):
        decision = pd.Timestamp(r["kickoff_at"]) - pd.Timedelta(minutes=60)
        while i < len(updates) and updates[i]["available_at"] < decision:
            u = updates[i]
            known.setdefault(u["team"], []).append(u)
            i += 1
        row = {"game_id": r["game_id"], "team": r["team"], "is_home": r["is_home"]}
        for prefix, t in [("own_", r["team"]), ("opp_", r["opponent_team"])]:
            h = pd.DataFrame(known.get(t, [])[-8:])
            for name, col in fields.items():
                key = prefix + name
                if key in TEAM:
                    row[key] = (
                        float(h[col].mean())
                        if not h.empty and h[col].notna().any()
                        else np.nan
                    )
        rows.append(row)
    return pd.DataFrame(rows)


def champion_baselines(source):
    """Reuse immutable annual champion replicas, including newly available Week10 rows."""
    import joblib

    from scripts.train_all_markets import MARKETS as CHAMPION

    # CHAMPION is a configuration mapping, never a call to the trainer.
    outputs = []
    for key, cfg in CHAMPION.items():
        market = cfg.get("model_name", key)
        target = cfg.get("target_col", key)
        cols = cfg["features"]
        d = (
            source[
                pregame_eligible(source, cfg["positions"])
                & observation_status(source).eq("participated")
                & source.stats_observed.eq(True)
            ]
            .dropna(subset=cols + [target, "completed_at"])
            .copy()
        )
        for year in range(2022, 2027):
            e = d[d.season.eq(year)].copy()
            bundle = joblib.load(
                ROOT
                / f"experiments/script_adjustment/numerical-20261121-v5/chronological_backbones/{market}-{year}.joblib"
            )
            e["prediction_at"] = pd.to_datetime(e.kickoff_at, utc=True) - pd.Timedelta(
                minutes=60
            )
            if (
                not pd.Timestamp(bundle["last_training_outcome"])
                < e.prediction_at.min()
            ):
                raise ValueError("Future champion fit")
            e["baseline"] = (
                e[cols[0]]
                if bundle["model"] is None
                else bundle["model"].predict(e[cols])
            )
            e["champion_sigma"] = bundle["sigma"]
            e["market"] = market
            e["y"] = e[target]
            outputs.append(
                e[
                    [
                        "game_id",
                        "player_id",
                        "market",
                        "season",
                        "baseline",
                        "champion_sigma",
                        "y",
                    ]
                ]
            )
    return pd.concat(outputs, ignore_index=True)


def columns(market, family):
    target, _, opp, _ = MARKETS[market]
    basic = [
        target + s
        for s in ["_career", "_last3", "_last5", "_season", "_season_n", "_sd5"]
    ]
    basic += [opp + "_last3", opp + "_last5", "history_n", "days_rest"]
    role = basic + [
        "offense_pct_last3",
        "offense_pct_career",
        "role_snap_change",
        "known_team_continuity",
        opp + "_share3",
        opp + "_share5",
        opp + "_share_sd5",
    ]
    if target != opp:
        role += ["efficiency3", "efficiency_career"]
    return list(
        dict.fromkeys(
            basic
            if family in ["recent_shrunk", "player_ridge"]
            else role
            if family == "role_ridge"
            else role + TEAM
        )
    )


def market_data(frame, market):
    target, _, opp, _ = MARKETS[market]
    d = frame.copy()
    d["efficiency3"] = d[target + "_last3"] / d[opp + "_last3"].replace(0, np.nan)
    d["efficiency_career"] = d[target + "_career"] / d[opp + "_career"].replace(
        0, np.nan
    )
    return d


def load_panel():
    path = CERTIFIED / "features.parquet"
    source, _ = reconciled_source()
    if ((source.season == 2026) & (source.week >= 11)).any() or source.season.gt(
        2026
    ).any():
        raise ValueError("Sealed outcomes in intelligence input")
    source["team"] = source.team.map(canonical_team)
    source["opponent_team"] = source.opponent_team.map(canonical_team)
    history = history_features(source[source.season.ge(2019)])
    teams = team_features(source)
    history = history.merge(
        teams[["game_id", "team"] + TEAM],
        on=["game_id", "team"],
        how="left",
        validate="many_to_one",
        suffixes=("_legacy", ""),
    )
    return path, history


def reconciled_source():
    """Recover an observed older record from an incomplete refresh, never invent zeros.

    No explicit retraction field exists in either source. Nonmissing newer values
    always win. An identity conflict prevents fallback and remains auditable.
    """
    from release_utils import resolve_release

    latest = pd.read_parquet(CERTIFIED / "features.parquet", filters=FILTERS).set_index(
        KEYS
    )
    old_dir, _ = resolve_release(ROOT)
    old_path = old_dir / "player_features.parquet"
    old = pd.read_parquet(old_path, filters=FILTERS).set_index(KEYS)
    shared = latest.index.intersection(old.index)
    same = (
        latest.loc[shared, "team"]
        .map(canonical_team)
        .eq(old.loc[shared, "team"].map(canonical_team))
    )
    safe_index = shared[same.to_numpy()]
    fallback = old.loc[safe_index.union(old.index.difference(latest.index))]
    result = latest.combine_first(fallback)
    restored = latest.loc[safe_index, "stats_observed"].ne(
        True
    ) & fallback.stats_observed.eq(True)
    restored_index = safe_index[restored.to_numpy()]
    # A missing newer box record is not evidence that an older observed box was void.
    result.loc[restored_index, "stats_observed"] = True
    for c in STATS:
        if c != "offense_pct":
            result.loc[restored_index, c] = fallback.loc[restored_index, c]
    audit = {
        "latest_sha256": sha(CERTIFIED / "features.parquet"),
        "fallback_sha256": sha(old_path),
        "latest_source": str((CERTIFIED / "features.parquet").relative_to(ROOT)),
        "fallback_source": str(old_path.relative_to(ROOT)),
        "restored_observed_box_records": len(restored_index),
        "identity_conflicts_no_fallback": int((~same).sum()),
        "newer_nonmissing_values_preserved": True,
        "genuine_missing_outcomes_not_zeroed": True,
        "historical_publication_vintages_verified": False,
    }
    result = rebuild_legacy(result.reset_index())
    audit["legacy_pregame_features_rebuilt_from_raw"] = True
    return result, audit


def rebuild_legacy(source):
    """Consistent research copy: discard stale/reset entering-game feature columns."""
    from scripts.build_features import AUX_STAT_COLS, STAT_COLS
    from scripts.forecast_features import defense_features, player_features

    d = source.copy()
    d["team"] = d.team.map(canonical_team)
    d["opponent_team"] = d.opponent_team.map(canonical_team)
    for c in STAT_COLS:
        d[c] = d[c].where(d.stats_observed.eq(True))
    d = player_features(d, STAT_COLS, AUX_STAT_COLS)
    allowed = defense_features(d, STAT_COLS)
    fields = [c for c in allowed if c.startswith("opp_")]
    return d.drop(columns=fields, errors="ignore").merge(
        allowed[["opponent_team", "season", "week"] + fields],
        on=["opponent_team", "season", "week"],
        how="left",
        validate="many_to_one",
    )
