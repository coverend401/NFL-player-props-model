"""Pregame game-outcome, clock/state occupancy and conditional action models."""

import numpy as np
import pandas as pd
from scipy.special import softmax
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .data import ACTIONS, BASE

FEATURES = (
    ["is_home"]
    + [f"{side}_{c}" for side in ["own", "opp"] for c in BASE]
    + ["own_n", "opp_n"]
)
OUTCOME_FEATURES = [
    c
    for c in FEATURES
    if not any(
        x in c
        for x in ["leading_share", "tied_share", "trailing_share", "scramble_rate"]
    )
]
SCRIPT_FEATURES = FEATURES + ["expected_margin", "win_probability", "tie_probability"]


def reg(alpha=100):
    return make_pipeline(StandardScaler(), Ridge(alpha=alpha))


class Outcome:
    """Single home-game outcome model; away probabilities mirror the same game."""

    def fit(self, d):
        h = d[d.is_home.eq(1)].dropna(subset=OUTCOME_FEATURES + ["margin"])
        self.margin = reg().fit(h[OUTCOME_FEATURES], h.margin)
        self.win = make_pipeline(
            StandardScaler(), LogisticRegression(C=0.1, max_iter=500)
        ).fit(h[OUTCOME_FEATURES], np.sign(h.margin).astype(int))
        return self

    def predict(self, d):
        home = d[d.is_home.eq(1)].copy()
        pred = self.win.predict_proba(home[OUTCOME_FEATURES])
        classes = self.win[-1].classes_
        probabilities = {c: pred[:, i] for i, c in enumerate(classes)}
        h = pd.DataFrame(
            {
                "game_id": home.game_id,
                "home_margin": self.margin.predict(home[OUTCOME_FEATURES]),
                "home_win": probabilities.get(1, np.zeros(len(home))),
                "away_win": probabilities.get(-1, np.zeros(len(home))),
                "tie_probability": probabilities.get(0, np.zeros(len(home))),
            }
        )
        out = d.merge(h, on="game_id", validate="many_to_one")
        out["expected_margin"] = np.where(
            out.is_home.eq(1), out.home_margin, -out.home_margin
        )
        out["win_probability"] = np.where(out.is_home.eq(1), out.home_win, out.away_win)
        return out.drop(columns=["home_margin", "home_win", "away_win"])


def action_matrix(d):
    """Hypothetical score/clock cells integrated over predicted occupancy, not actual script."""
    rows = []
    for cell in range(15):
        x = d[SCRIPT_FEATURES].reset_index(drop=True).copy()
        phase, state = divmod(cell, 5)
        x["score_band"] = state - 2
        x["late"] = int(phase == 2)
        x["early"] = int(phase == 0)
        x["score_late"] = (state - 2) * int(phase == 2)
        x["score_margin"] = (state - 2) * x.expected_margin
        rows.append(x)
    return pd.concat(rows, ignore_index=True)


class Script:
    def fit(self, d, cells):
        d = d.dropna(subset=SCRIPT_FEATURES + ["plays", "cell_0"]).reset_index(
            drop=True
        )
        self.volume = reg().fit(d[SCRIPT_FEATURES], np.log(d.plays))
        self.smearing = float(
            np.mean(np.exp(np.log(d.plays) - self.volume.predict(d[SCRIPT_FEATURES])))
        )
        counts = d[[f"cell_{i}" for i in range(15)]].to_numpy(float)
        logs = np.log(counts + 0.5)
        logs -= logs.mean(axis=1, keepdims=True)
        self.occupancy = reg().fit(d[SCRIPT_FEATURES], logs)
        x = action_matrix(d)
        keys = pd.concat(
            [d[["game_id", "team"]].assign(cell=i) for i in range(15)],
            ignore_index=True,
        )
        totals = keys.merge(cells, on=["game_id", "team", "cell"], how="left")
        weights = totals.pivot_table(
            index=["game_id", "team", "cell"],
            columns="action",
            values="n",
            aggfunc="sum",
            fill_value=0,
        ).reindex(columns=ACTIONS, fill_value=0)
        weights = (
            keys.merge(
                weights.reset_index(), on=["game_id", "team", "cell"], how="left"
            )[ACTIONS]
            .fillna(0)
            .to_numpy()
        )
        parts = []
        labels = []
        sample_weights = []
        for k, a in enumerate(ACTIONS):
            valid = weights[:, k] > 0
            parts.append(x.loc[valid])
            labels += [a] * int(valid.sum())
            sample_weights.extend(weights[valid, k])
        xx = pd.concat(parts, ignore_index=True)
        self.action = make_pipeline(
            StandardScaler(), LogisticRegression(C=0.01, max_iter=600)
        ).fit(xx, labels, logisticregression__sample_weight=np.array(sample_weights))
        return self

    def predict(self, d):
        out = d.copy()
        plays = np.clip(
            np.exp(self.volume.predict(d[SCRIPT_FEATURES])) * self.smearing, 1, 200
        )
        probabilities = softmax(self.occupancy.predict(d[SCRIPT_FEATURES]), axis=1)
        action = (
            self.action.predict_proba(action_matrix(d))
            .reshape(15, len(d), -1)
            .transpose(1, 0, 2)
        )
        aligned = np.zeros((len(d), 15, len(ACTIONS)))
        for j, a in enumerate(self.action[-1].classes_):
            aligned[:, :, ACTIONS.index(a)] = action[:, :, j]
        volumes = plays[:, None, None] * probabilities[:, :, None] * aligned
        out["expected_plays"] = plays
        for j, a in enumerate(ACTIONS):
            out["expected_" + a] = volumes[:, :, j].sum(axis=1)
        out["expected_attempts"] = out.expected_attempt
        out["expected_carries"] = (
            out.expected_designed_carry + out.expected_scramble + out.expected_kneel
        )
        out["expected_dropbacks"] = (
            out.expected_attempts + out.expected_scramble + out.expected_other
        )
        for label, idx in [
            ("leading", [3, 4, 8, 9, 13, 14]),
            ("tied", [2, 7, 12]),
            ("trailing", [0, 1, 5, 6, 10, 11]),
        ]:
            out["prob_" + label] = probabilities[:, idx].sum(axis=1)
            out["plays_" + label] = plays * out["prob_" + label]
            out["attempts_" + label] = volumes[:, idx, 0].sum(axis=1)
            out["carries_" + label] = volumes[:, idx, 1:4].sum(axis=(1, 2))
        for i in range(15):
            out["prob_cell_" + str(i)] = probabilities[:, i]
        return out


def chronological_team(panel, cells):
    """Annual origins: all fitted outcomes predate every evaluated prediction."""
    d = panel.dropna(subset=OUTCOME_FEATURES).copy()
    outcomes = []
    scripts = []
    bundles = {}
    for year in range(2021, 2027):
        evaluate = d[d.season.eq(year)]
        if evaluate.empty:
            continue
        cutoff = evaluate.prediction_at.min()
        train = d[d.season.lt(year) & d.available_at.lt(cutoff)]
        if len(train) < 100:
            continue
        model = Outcome().fit(train)
        e = model.predict(evaluate)
        e["outcome_fit_before"] = train.available_at.max()
        outcomes.append(e)
        historic = pd.concat(outcomes, ignore_index=True)
        fit = historic[
            historic.season.lt(year)
            & historic.available_at.lt(cutoff)
            & historic.cell_0.notna()
        ]
        if len(fit) < 100:
            continue
        script = Script().fit(fit, cells)
        pred = script.predict(e.dropna(subset=SCRIPT_FEATURES))
        pred["script_fit_before"] = fit.available_at.max()
        scripts.append(pred)
        bundles[year] = {
            "outcome": model,
            "script": script,
            "fit_before": cutoff.isoformat(),
        }
    return pd.concat(scripts, ignore_index=True), bundles
