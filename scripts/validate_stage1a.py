"""Reproduce Stage 1A coverage/forecast comparisons without overwriting data/.

Requires source snapshots schedules.parquet, players.parquet, snaps.parquet in
--sources. The snapshot files contain public nflverse data, never credentials.
Generated artifacts and diagnostics are written only to --output.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import types

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

try:
    from .build_features import (
        build_player_features,
        AUX_STAT_COLS,
        leakage_check,
    )
    from .build_slate import build_slate, build_game_context_for_week
    from .train_all_markets import MARKETS, prepare_dataset, coverage_report
except ImportError:
    from build_features import (
        build_player_features,
        AUX_STAT_COLS,
        leakage_check,
    )
    from build_slate import build_slate, build_game_context_for_week
    from train_all_markets import MARKETS, prepare_dataset, coverage_report

KEYS = ["player_id", "season", "week"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prediction-at", default="2026-11-12T20:00:00Z")
    parser.add_argument(
        "--baseline-ref", default="0c6029002be0820c0502d957372d5261610ba927"
    )
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if out == Path("data").resolve() or Path("data").resolve() in out.parents:
        raise ValueError(
            "Use a separate output directory; validation must not overwrite bundled artifacts"
        )
    old = pd.read_parquet("data/player_features.parquet")
    raw = pd.read_parquet("data/weekly_player_data.parquet")
    sched = pd.read_parquet(args.sources / "schedules.parquet")
    players = pd.read_parquet(args.sources / "players.parquet")
    snaps = pd.read_parquet(args.sources / "snaps.parquet")
    snaps = snaps[snaps.game_type.eq("REG")].copy()
    snaps = snaps.merge(
        players[["gsis_id", "pfr_id"]].dropna().drop_duplicates(),
        left_on="pfr_player_id",
        right_on="pfr_id",
        how="left",
        validate="many_to_one",
    )
    unmapped = int((snaps.offense_snaps.gt(0) & snaps.gsis_id.isna()).sum())
    part = snaps.dropna(subset=["gsis_id"]).rename(
        columns={
            "gsis_id": "player_id",
            "player": "player_display_name",
            "opponent": "opponent_team",
            "game_type": "season_type",
        }
    )
    part = part[
        KEYS
        + [
            "game_id",
            "season_type",
            "team",
            "opponent_team",
            "position",
            "player_display_name",
            "offense_pct",
        ]
    ].drop_duplicates(KEYS)
    # Hold auxiliary statistics at their bundled snapshot, isolating code changes
    # from subsequent upstream revisions. Snap-only observations stay missing.
    aux_columns = [
        c for c in AUX_STAT_COLS if c not in raw.columns and c != "offense_pct"
    ]
    aux = part.merge(
        old[KEYS + aux_columns].drop_duplicates(KEYS),
        on=KEYS,
        how="outer",
        validate="one_to_one",
    )
    contexts = []
    for _, game in sched[
        sched.game_type.eq("REG") & sched.season.isin(raw.season.unique())
    ].iterrows():
        c = build_game_context_for_week(pd.DataFrame([game])).reset_index()
        c["season"] = game.season
        c["week"] = game.week
        c["opponent_team"] = c.team.map(
            {game.home_team: game.away_team, game.away_team: game.home_team}
        )
        contexts.append(c)
    team_stats = pd.read_parquet(args.sources / "team_stats.parquet")
    new = build_player_features(
        raw,
        aux=aux,
        game_context=pd.concat(contexts, ignore_index=True),
        schedule=sched,
        team_stats=team_stats,
    )
    leakage_check(new)
    new.to_parquet(out / "player_features.parquet", index=False)
    observed = part[part.offense_pct.gt(0)].merge(
        raw[raw.season_type.eq("REG")][KEYS].drop_duplicates(),
        on=KEYS,
        how="left",
        indicator=True,
    )
    missing = observed[observed._merge.eq("left_only")]
    report = dict(
        prediction_at=args.prediction_at,
        baseline_ref=args.baseline_ref,
        source_sha256={
            name: hashlib.sha256((args.sources / name).read_bytes()).hexdigest()
            for name in [
                "schedules.parquet",
                "players.parquet",
                "snaps.parquet",
                "team_stats.parquet",
            ]
        },
        original_feature_rows=len(old),
        new_feature_rows=len(new),
        missing_positive_snap_outcomes_by_position=missing.groupby("position")
        .size()
        .to_dict(),
        unmapped_positive_snap_rows=unmapped,
        markets={},
    )
    baseline = types.ModuleType("baseline_training")
    source = subprocess.run(
        ["git", "show", f"{args.baseline_ref}:scripts/train_all_markets.py"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    exec(compile(source, "baseline_training.py", "exec"), baseline.__dict__)
    for market, config in MARKETS.items():
        target = config.get("target_col", market)
        label = config.get("model_name", market)
        before = baseline.prepare_dataset(old, target, baseline.MARKETS[market])
        after = prepare_dataset(new, target, config)
        oldkeys = set(before[KEYS].itertuples(index=False, name=None))
        newkeys = set(after[KEYS].itertuples(index=False, name=None))
        position_counts = coverage_report(new, target, config)
        for item in position_counts:
            position = item["position"]
            bk = set(
                before[before.position.eq(position)][KEYS].itertuples(
                    index=False, name=None
                )
            )
            ak = set(
                after[after.position.eq(position)][KEYS].itertuples(
                    index=False, name=None
                )
            )
            item.update(
                before_retained=len(bk),
                added_vs_baseline=len(ak - bk),
                removed_vs_baseline=len(bk - ak),
            )
        entry = dict(
            old_retained=len(before),
            new_retained=len(after),
            added=len(newkeys - oldkeys),
            removed=len(oldkeys - newkeys),
            by_position=position_counts,
        )
        # Fixed Ridge benchmark: fit only seasons before 2025 on each population,
        # then evaluate both on exactly the same observed 2025 player-games.
        # This is diagnostic, NOT an untouched holdout or a betting backtest.
        common = before[before.season.eq(2025)][KEYS].merge(
            after[after.season.eq(2025)][KEYS], on=KEYS
        )
        metrics = {}
        for name, frame in [("before", before), ("after", after)]:
            train = frame[frame.season.lt(2025)]
            test = common.merge(frame, on=KEYS, validate="one_to_one")
            model = Ridge(alpha=1.0).fit(train[config["features"]], train[target])
            preds = model.predict(test[config["features"]])
            metrics[name] = float(np.abs(preds - test[target]).mean())
        entry["diagnostic_ridge_common_2025_n"] = len(common)
        entry["diagnostic_ridge_common_2025_mae"] = metrics
        report["markets"][label] = entry
        print(label, entry, flush=True)
    # Reuse the same frozen models to isolate changes to feature timing/coverage.
    corrected = build_slate(
        new,
        sched,
        pd.Timestamp(args.prediction_at),
        allow_unverified_models=True,
        allow_unverified_context=True,
    )
    corrected.to_parquet(out / "slate.parquet", index=False)
    baseline_slate = types.ModuleType("baseline_slate")
    source = subprocess.run(
        ["git", "show", f"{args.baseline_ref}:scripts/build_slate.py"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    exec(compile(source, "baseline_slate.py", "exec"), baseline_slate.__dict__)
    previous = baseline_slate.build_slate(
        old,
        sched[sched.season.eq(pd.Timestamp(args.prediction_at).year)],
        pd.Timestamp(args.prediction_at).tz_convert(None).normalize(),
    )
    merged = previous.merge(
        corrected, on=["market", "player"], suffixes=("_before", "_after")
    )
    merged["projection_change"] = merged.projection_after - merged.projection_before
    report["forecast_comparison"] = dict(
        before_rows=len(previous),
        after_rows=len(corrected),
        common_rows=len(merged),
        mean_absolute_change_by_market=merged.groupby("market")
        .projection_change.apply(lambda x: float(x.abs().mean()))
        .to_dict(),
        # No depth-chart override is passed to either version; isolate code/data
        # changes rather than introducing a new live starter snapshot.
        note="Frozen model weights; baseline and corrected code with same model weights; no QB starter override. No accuracy claim.",
    )
    merged.to_csv(out / "forecast_comparison.csv", index=False)
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Report:", out / "report.json")


if __name__ == "__main__":
    main()
