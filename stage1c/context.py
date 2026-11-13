"""Online, market-free C0–C2 fixture states. All aggregates precede decisions.

Defensive schedule adjustment is first-order: past production minus the opposing
offence's shrunk ENTERING-game efficiency. Not a full simultaneous causal rating.
"""

from collections import defaultdict
import numpy as np
import pandas as pd
from scipy.stats import t
from stage1c.contracts import team, availability, assert_development

KINDS = {
    "pass": ("passing_yards", "attempts"),
    "rush_QB": ("rushing_yards", "carries"),
    "rush_RB": ("rushing_yards", "carries"),
    "rec_RB": ("receiving_yards", "targets"),
    "rec_WR": ("receiving_yards", "targets"),
    "rec_TE": ("receiving_yards", "targets"),
}
# Weak cold-start modelling priors, not fabricated data or measured improvements.
PRIOR = {
    "pass": 7.0,
    "rush_QB": 4.0,
    "rush_RB": 4.0,
    "rec_RB": 6.0,
    "rec_WR": 8.0,
    "rec_TE": 7.0,
}
VOLUME_PRIOR = {
    "pass": 34.0,
    "rush_QB": 5.0,
    "rush_RB": 22.0,
    "rec_RB": 6.0,
    "rec_WR": 20.0,
    "rec_TE": 7.0,
}
OPPORTUNITY = [
    "def_opportunities",
    "def_production",
    "def_history_games",
    "def_known_fraction",
]
EFFICIENCY = [
    "def_efficiency",
    "def_completion_rate",
    "def_eff_exposure",
    "def_known_fraction",
]
SCHEDULE = [
    "def_schedule_efficiency",
    "def_schedule_delta",
    "def_schedule_exposure",
    "def_known_fraction",
]
VOLUME = [
    "expected_plays",
    "expected_play_variance",
    "expected_dropback_variance",
    "expected_dropbacks",
    "expected_nondropback_plays",
    "expected_dropback_share",
    "own_pace",
    "opp_pace",
    "own_no_huddle",
    "opp_no_huddle",
    "margin_mean",
    "margin_scale",
    "script_trailing",
    "script_close",
    "script_leading",
    "is_home",
    "rest_days",
    "opp_rest_days",
    "team_history_games",
    "opp_history_games",
]
FAMILIES = {
    "player_control": [],
    "c1_opportunity": OPPORTUNITY,
    "c1_efficiency": EFFICIENCY,
    "c1_schedule": SCHEDULE,
    "c2_volume": VOLUME,
    "c1_c2": list(dict.fromkeys(OPPORTUNITY + EFFICIENCY + SCHEDULE + VOLUME)),
}


class Accumulator:
    def __init__(self):
        self.values = defaultdict(float)

    def add(self, values):
        for k in self.values:
            self.values[k] *= 0.9
        for k, v in values.items():
            self.values[k] += float(v)

    def mean(self, key, prior, strength=4):
        return (self.values[key] + strength * prior) / (self.values["n"] + strength)

    def rate(self, num, den, prior, strength=100):
        return (self.values[num] + strength * prior) / (self.values[den] + strength)


class FixtureStates:
    def __init__(self):
        self.off = defaultdict(Accumulator)
        self.defence = defaultdict(Accumulator)
        self.volume = defaultdict(Accumulator)
        self.league = defaultdict(lambda: defaultdict(float))
        self.latest = {}
        self.information_at = pd.NaT
        self.margin_n = 0
        self.margin_ss = 0.0
        self.script_counts = np.zeros(3)

    def league_rate(self, kind):
        d = self.league[kind]
        return (d["production"] + 100 * PRIOR[kind]) / (d["opportunities"] + 100)

    def update_batch(self, games, rates):
        """Compute entering-game expectations BEFORE applying any same-time outcomes."""
        pending = []
        for r in games.itertuples():
            for kind, (target, opportunity) in KINDS.items():
                x = rates.get((r.game_id, r.team, kind))
                if x is None:
                    pending.append((r, kind, {}))
                    continue
                y, n, c = (
                    x[target],
                    x[opportunity],
                    x["completions"]
                    if kind == "pass"
                    else x["receptions"]
                    if kind.startswith("rec")
                    else 0,
                )
                if not np.isfinite([y, n, c]).all() or n < 0:
                    pending.append((r, kind, {}))
                    continue
                expected = self.off[(r.team, kind)].rate(
                    "production", "opportunities", self.league_rate(kind)
                )
                pending.append(
                    (
                        r,
                        kind,
                        {
                            "n": 1,
                            "production": y,
                            "opportunities": n,
                            "completions": c,
                            "schedule_residual": y - expected * n,
                        },
                    )
                )
        for r, kind, values in pending:
            self.off[(r.team, kind)].add(values)
            self.defence[(r.opponent, kind)].add(values)
            for k in ["production", "opportunities", "completions"]:
                self.league[kind][k] += values.get(k, 0)
        counterparts = {(r.game_id, r.team): r for r in games.itertuples()}
        for r in games.itertuples():
            bucket = "trail" if r.margin < -7 else "lead" if r.margin > 7 else "close"
            values = {
                "n": 1,
                "plays": r.plays,
                "plays_allowed": counterparts[(r.game_id, r.opponent)].plays,
                "plays2": r.plays**2,
                "dropbacks": r.dropbacks,
                "rushes": r.rushes,
                "pace_sum": r.pace_sum,
                "pace_n": r.pace_n,
                "no_huddle": r.no_huddle,
                "points_for": r.points_for,
                "points_against": r.points_against,
                bucket + "_n": 1,
                bucket + "_plays": r.plays,
                bucket + "_dropbacks": r.dropbacks,
            }
            self.volume[r.team].add(values)
            self.latest[r.team] = r.kickoff_at
            self.margin_ss += r.margin**2
            self.margin_n += 1
            self.script_counts[["trail", "close", "lead"].index(bucket)] += 1
        self.information_at = games.available_at_proxy.max()

    def fixture(self, home, away, decision):
        a, b = self.volume[home], self.volume[away]
        ma = 0.5 * (a.mean("points_for", 22) + b.mean("points_against", 22))
        mb = 0.5 * (b.mean("points_for", 22) + a.mean("points_against", 22))
        margin = ma - mb
        sd = np.sqrt((self.margin_ss + 40 * 20**2) / (self.margin_n + 40))
        scale = max(sd, 8.0)
        c = t.cdf((np.array([-7.0, 7.0]) - margin) / (scale * np.sqrt(3 / 5)), df=5)
        probs = np.array([c[0], c[1] - c[0], 1 - c[1]])
        plays = []
        shares = []
        for bucket in ["trail", "close", "lead"]:
            n = a.values[bucket + "_n"]
            base = a.mean("plays", 62)
            count = (a.values[bucket + "_plays"] + 4 * base) / (n + 4)
            overall = a.rate("dropbacks", "plays", 0.57)
            share = (a.values[bucket + "_dropbacks"] + 100 * overall) / (
                a.values[bucket + "_plays"] + 100
            )
            plays.append(count)
            shares.append(share)
        component_plays = 0.5 * (np.asarray(plays) + b.mean("plays_allowed", 62))
        component_dropbacks = component_plays * np.asarray(shares)
        meanplays = float(np.dot(probs, component_plays))
        meandropbacks = float(np.dot(probs, component_dropbacks))
        pass_share = meandropbacks / meanplays
        prior_mean = a.mean("plays", 62)
        prior_var = max(a.mean("plays2", 62**2 + 100) - prior_mean**2, prior_mean)
        alpha = max((prior_var - prior_mean) / max(prior_mean**2, 1), 1e-6)
        play_var = float(
            np.dot(
                probs,
                component_plays
                + alpha * component_plays**2
                + (component_plays - meanplays) ** 2,
            )
        )
        drop_var = float(
            np.dot(
                probs,
                component_dropbacks
                + alpha * component_dropbacks**2
                + (component_dropbacks - meandropbacks) ** 2,
            )
        )

        def pace(s):
            return s.rate("pace_sum", "pace_n", 28.0, strength=100)

        def rest(k):
            return (
                min((decision - self.latest[k]).total_seconds() / 86400, 30)
                if k in self.latest
                else 7.0
            )

        return dict(
            own_prior_plays=a.mean("plays", 62),
            own_prior_dropbacks=a.mean("dropbacks", 35),
            league_script_trailing=(self.script_counts[0] + 4) / (self.margin_n + 12),
            league_script_close=(self.script_counts[1] + 4) / (self.margin_n + 12),
            league_script_leading=(self.script_counts[2] + 4) / (self.margin_n + 12),
            volume_alpha=float(alpha),
            plays_trailing_mean=float(component_plays[0]),
            plays_close_mean=float(component_plays[1]),
            plays_leading_mean=float(component_plays[2]),
            dropbacks_trailing_mean=float(component_dropbacks[0]),
            dropbacks_close_mean=float(component_dropbacks[1]),
            dropbacks_leading_mean=float(component_dropbacks[2]),
            expected_play_variance=play_var,
            expected_dropback_variance=drop_var,
            expected_plays=float(meanplays),
            expected_dropbacks=meandropbacks,
            expected_nondropback_plays=float(meanplays * (1 - pass_share)),
            expected_dropback_share=pass_share,
            own_pace=pace(a),
            opp_pace=pace(b),
            own_no_huddle=a.rate("no_huddle", "plays", 0.1),
            opp_no_huddle=b.rate("no_huddle", "plays", 0.1),
            margin_mean=float(margin),
            margin_scale=float(scale),
            script_trailing=float(probs[0]),
            script_close=float(probs[1]),
            script_leading=float(probs[2]),
            rest_days=rest(home),
            opp_rest_days=rest(away),
            team_history_games=a.values["n"],
            opp_history_games=b.values["n"],
        )

    def defence_row(self, opponent, kind):
        d = self.defence[(opponent, kind)]
        league = self.league_rate(kind)
        prior = VOLUME_PRIOR[kind]
        return dict(
            def_known_fraction=d.values["n"]
            / max(self.volume[opponent].values["n"], 1e-9),
            def_opportunities=d.mean("opportunities", prior),
            def_production=d.mean("production", prior * league),
            def_history_games=d.values["n"],
            def_efficiency=d.rate("production", "opportunities", league),
            def_completion_rate=d.rate(
                "completions",
                "opportunities",
                0.65 if kind == "pass" else 0.6 if kind.startswith("rec") else 0,
            ),
            def_eff_exposure=d.values["opportunities"],
            def_schedule_efficiency=league
            + d.rate("schedule_residual", "opportunities", 0),
            def_schedule_delta=d.rate("schedule_residual", "opportunities", 0),
            def_schedule_exposure=d.values["opportunities"],
        )


def states(games, rates, lag_hours=36, fixtures=None):
    games = games.copy()
    assert_development(games)
    for c in ["team", "opponent"]:
        games[c] = games[c].map(team)
    games["evidence_tier"] = "retrospective"
    games["available_at_proxy"] = games.apply(
        lambda r: availability(r, lag_hours=lag_hours), axis=1
    )
    games["prediction_at"] = pd.to_datetime(games.kickoff_at, utc=True) - pd.Timedelta(
        hours=1
    )
    if games.duplicated(["game_id", "team"]).any():
        raise ValueError("Duplicate fixture side")
    if rates.duplicated(["game_id", "team", "kind"]).any():
        raise ValueError("Duplicate positional totals")
    mapping = {
        (r.game_id, team(r.team), r.kind): r._asdict()
        for r in rates.itertuples(index=False)
    }
    updates = list(games.groupby("available_at_proxy", sort=True))
    index = 0
    s = FixtureStates()
    rows = []
    requests = games.copy() if fixtures is None else fixtures.copy()
    assert_development(requests)
    for key in ["team", "opponent"]:
        requests[key] = requests[key].map(team)
    requests["prediction_at"] = pd.to_datetime(
        requests.kickoff_at, utc=True
    ) - pd.Timedelta(hours=1)
    if requests.duplicated(["game_id", "team"]).any():
        raise ValueError("Duplicate fixture request")
    for decision, fixtures in requests.groupby("prediction_at", sort=True):
        while index < len(updates) and updates[index][0] < decision:
            s.update_batch(updates[index][1], mapping)
            index += 1
        for r in fixtures.itertuples():
            f = s.fixture(r.team, r.opponent, decision)
            for kind in KINDS:
                rows.append(
                    dict(
                        game_id=r.game_id,
                        team=r.team,
                        opponent=r.opponent,
                        kind=kind,
                        prediction_at=decision,
                        context_information_at=s.information_at,
                        evidence_tier="retrospective",
                        is_home=r.is_home,
                        **f,
                        **s.defence_row(r.opponent, kind),
                    )
                )
    return pd.DataFrame(rows)


def attach(panel, context, market):
    d = panel.copy()
    d["team_key"] = d.team.map(team)
    if market in ["passing_yards", "passing_attempts", "completions"]:
        kind = pd.Series("pass", index=d.index)
    elif market.startswith("qb_rushing"):
        kind = pd.Series("rush_QB", index=d.index)
    elif market.startswith("rushing"):
        kind = pd.Series("rush_RB", index=d.index)
    else:
        kind = "rec_" + d.position
    d["kind"] = kind
    c = context.rename(columns={"team": "team_key"})
    joined = d.merge(
        c.drop(columns=["opponent", "prediction_at"]),
        on=["game_id", "team_key", "kind"],
        how="left",
        validate="many_to_one",
    )
    if joined[FAMILIES["c1_c2"]].isna().any().any():
        raise ValueError(
            "Missing fixture state; do not silently drop benchmark players"
        )
    if (joined.context_information_at >= joined.prediction_at).any():
        raise ValueError("Future fixture information")
    return joined


def volume_cdf(context, quantity="plays"):
    """C2 team count mixture, not player allocation or a joint C6 model."""
    from scipy.stats import nbinom

    if quantity not in ["plays", "dropbacks"]:
        raise ValueError("Unknown team count")
    weights = context[["script_trailing", "script_close", "script_leading"]].to_numpy()
    means = context[
        [quantity + "_" + s + "_mean" for s in ["trailing", "close", "leading"]]
    ].to_numpy()
    size = 1 / context.volume_alpha.to_numpy()
    return lambda n: np.sum(
        weights
        * nbinom.cdf(
            np.asarray(n)[:, None],
            size[:, None],
            size[:, None] / (size[:, None] + means),
        ),
        axis=1,
    )
