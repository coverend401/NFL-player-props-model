"""
NFL Player Prop Models - v1: multiple markets

Same approach as the passing-yards model, applied to each requested market:
chronological train/test split (train on earlier seasons, test on the most
recent complete season), compare against a naive baseline, pick whichever
model actually beats that baseline, check calibration, save the model.

Each market defines its own:
  - which positions/snap-type are eligible (e.g. rushing markets need RBs
    who actually got a carry that game, not every offensive player)
  - which engineered feature columns to use (built by build_features.py)
"""
import pandas as pd
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.ensemble import GradientBoostingRegressor
from scipy.stats import norm
import joblib

MIN_PRIOR_GAMES = 3

MARKETS = {
    "passing_yards": {
        "positions": ["QB"],
        "snap_filter": ("attempts", 0),
        "features": ["passing_yards_season_avg", "passing_yards_last3_avg", "passing_yards_last5_avg",
                     "passing_yards_trend", "attempts_season_avg", "attempts_last3_avg",
                     "games_played_prior", "opp_passing_yards_allowed_season_avg"],
    },
    "attempts": {  # passing attempts (QB)
        "positions": ["QB"],
        "snap_filter": ("attempts", 0),
        "features": ["attempts_season_avg", "attempts_last3_avg", "attempts_last5_avg", "attempts_trend",
                     "games_played_prior"],
        "model_name": "passing_attempts",
    },
    "completions": {
        "positions": ["QB"],
        "snap_filter": ("attempts", 0),
        "features": ["completions_season_avg", "completions_last3_avg", "completions_last5_avg",
                     "completions_trend", "attempts_season_avg", "attempts_last3_avg",
                     "games_played_prior"],
    },
    "rushing_yards": {
        "positions": ["RB"],
        "snap_filter": ("carries", 0),
        "features": ["rushing_yards_season_avg", "rushing_yards_last3_avg", "rushing_yards_last5_avg",
                     "rushing_yards_trend", "carries_season_avg", "carries_last3_avg",
                     "games_played_prior", "opp_rushing_yards_allowed_season_avg"],
    },
    "carries": {  # rushing attempts
        "positions": ["RB"],
        "snap_filter": ("carries", 0),
        "features": ["carries_season_avg", "carries_last3_avg", "carries_last5_avg", "carries_trend",
                     "games_played_prior"],
        "model_name": "rushing_attempts",
    },
    "receiving_yards": {
        "positions": ["WR", "TE", "RB"],
        "snap_filter": ("targets", 0),
        "features": ["receiving_yards_season_avg", "receiving_yards_last3_avg", "receiving_yards_last5_avg",
                     "receiving_yards_trend", "targets_season_avg", "targets_last3_avg",
                     "games_played_prior", "opp_receiving_yards_allowed_season_avg"],
    },
    "receptions": {
        "positions": ["WR", "TE", "RB"],
        "snap_filter": ("targets", 0),
        "features": ["receptions_season_avg", "receptions_last3_avg", "receptions_last5_avg",
                     "receptions_trend", "targets_season_avg", "targets_last3_avg",
                     "games_played_prior", "opp_receptions_allowed_season_avg"],
    },
}


def prepare_dataset(features: pd.DataFrame, market: str, config: dict) -> pd.DataFrame:
    snap_col, min_val = config["snap_filter"]
    df = features[
        features["position"].isin(config["positions"]) & (features[snap_col] > min_val)
    ].copy()
    df = df[df["games_played_prior"] >= MIN_PRIOR_GAMES]
    df = df.dropna(subset=config["features"] + [market])
    return df


def time_based_split(df: pd.DataFrame):
    seasons = sorted(df["season"].unique())
    test_season = seasons[-1]
    return df[df["season"] < test_season], df[df["season"] == test_season], test_season


def mae(preds, actual):
    return np.mean(np.abs(preds - actual))


def calibration_summary(preds, y_test, resid_std, baseline_line, n_bins=5):
    implied_prob_over = 1 - norm.cdf(baseline_line, preds, resid_std)
    actual_over = (y_test.values > baseline_line.values).astype(int)
    results = pd.DataFrame({"implied_prob": implied_prob_over, "actual_over": actual_over})
    try:
        results["bucket"] = pd.qcut(results["implied_prob"], n_bins, duplicates="drop")
    except ValueError:
        return "  (not enough spread in predictions to bucket - sample size likely too small)"
    lines = []
    for name, group in results.groupby("bucket", observed=True):
        lines.append(f"    {str(name):<20} predicted~{group['implied_prob'].mean():.2f}  "
                      f"actual={group['actual_over'].mean():.2f}  n={len(group)}")
    return "\n".join(lines)


def train_market(features: pd.DataFrame, market: str, config: dict):
    label = config.get("model_name", market)
    print(f"\n{'='*60}\nMARKET: {label}  (target column: {market})\n{'='*60}")

    df = prepare_dataset(features, market, config)
    if len(df) < 200:
        print(f"SKIPPED - only {len(df)} usable rows, too small to train/validate honestly.")
        return None

    train, test, test_season = time_based_split(df)
    if len(test) < 30:
        print(f"SKIPPED - only {len(test)} test-season rows, too small to validate honestly.")
        return None

    X_train, y_train = train[config["features"]], train[market]
    X_test, y_test = test[config["features"]], test[market]
    print(f"Train: {len(train)} rows (seasons < {test_season}) | Test: {len(test)} rows (season {test_season})")

    naive_col = config["features"][0]
    naive_mae = mae(X_test[naive_col], y_test)
    print(f"Naive (season avg only): MAE={naive_mae:.2f}")

    ridge = Ridge(alpha=1.0).fit(X_train, y_train)
    ridge_preds = ridge.predict(X_test)
    ridge_mae = mae(ridge_preds, y_test)
    print(f"Ridge: MAE={ridge_mae:.2f}")

    gbr = GradientBoostingRegressor(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42)
    gbr.fit(X_train, y_train)
    gbr_preds = gbr.predict(X_test)
    gbr_mae = mae(gbr_preds, y_test)
    print(f"Gradient Boosting: MAE={gbr_mae:.2f}")

    if min(ridge_mae, gbr_mae) >= naive_mae:
        print(f"WARNING: neither model beat the naive baseline for {label}. "
              f"NOT saving a model file - shipping this would be worse than a simple average.")
        return None

    if gbr_mae < ridge_mae:
        best_model, best_preds, best_name = gbr, gbr_preds, "gradient_boosting"
    else:
        best_model, best_preds, best_name = ridge, ridge_preds, "ridge"
    print(f"Selected: {best_name}")

    train_preds = best_model.predict(X_train)
    resid_std = np.std(y_train - train_preds)
    print(f"Residual std: {resid_std:.2f}")

    print("Calibration (vs. player's own season average as a stand-in line):")
    print(calibration_summary(best_preds, y_test, resid_std, test[naive_col]))

    out_path = f"data/model_{label}.joblib"
    joblib.dump({"model": best_model, "features": config["features"], "resid_std": resid_std,
                 "market": market, "positions": config["positions"]}, out_path)
    print(f"Saved -> {out_path}")
    return out_path


if __name__ == "__main__":
    features = pd.read_parquet("data/player_features.parquet")
    saved = []
    for market, config in MARKETS.items():
        result = train_market(features, market, config)
        if result:
            saved.append(result)

    print(f"\n\n{'='*60}\nSUMMARY: {len(saved)} of {len(MARKETS)} markets produced a usable model")
    for path in saved:
        print(f"  {path}")
    skipped = len(MARKETS) - len(saved)
    if skipped:
        print(f"  {skipped} market(s) skipped - see warnings above. These need more data or better "
              f"features before they're trustworthy; they should not appear in the app yet.")