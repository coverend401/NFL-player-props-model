"""Read-only numerical challenger evidence, separate from every recommendation/pricing path."""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from weekly_learning.store import ROOT, Store

from .runner import DEFAULT
from .validate import validate


def render(release):
    st.subheader("Numerical game-script research")
    try:
        validate(DEFAULT)
        report = json.loads((DEFAULT / "report.json").read_text())
    except (OSError, ValueError, KeyError, TypeError, AssertionError):
        st.info(
            "Numerical challenger unavailable or failed integrity checks. Certified forecasts and prices are unchanged."
        )
        return
    st.warning(
        "EXPERIMENTAL — NOT SELECTED. Original forecasts, Top Picks, Top 2 rankings and all prices remain unchanged. No adjusted betting probability or EV is certified."
    )
    status = json.loads((DEFAULT / "week12_status.json").read_text())
    if pd.Timestamp.now(tz="UTC") < pd.Timestamp("2026-11-24T12:00Z"):
        st.caption("Week12: " + status["blocker"])
    elif release.get("fixture_slate", {}).get("week", 0) < 12:
        st.caption(
            "Week12 has not been selected. Fresh operational source, eligibility and certification gates still apply."
        )
    else:
        st.caption(
            "Current champion slate is separate from this unselected numerical challenger."
        )
    # Prefer a genuine independently frozen overlay for the caller's exact release.
    sidecar = ROOT / "weekly_learning_state/script_captures" / release["release_id"]
    if sidecar.exists():
        try:
            Store(ROOT / "weekly_learning_state").validate(sidecar)
            frame = pd.read_parquet(sidecar / "predictions.parquet")
            teams = pd.read_parquet(sidecar / "teams.parquet")
        except (OSError, ValueError, KeyError):
            st.error(
                "Experimental capture failed integrity checks. No adjusted forecasts displayed."
            )
            return
    elif release["release_id"] == "research-week11-frozen-20261120-r2":
        frame = pd.read_parquet(DEFAULT / "reference_week11_adjustments.parquet")
        teams = pd.read_parquet(DEFAULT / "reference_week11_teams.parquet")
    else:
        st.info(
            "No predecision numerical overlay has been frozen for this release. No old player forecast is relabelled current."
        )
        frame = pd.DataFrame()
        teams = pd.DataFrame()
    with st.expander("Baseline versus experimental player forecasts", expanded=True):
        if frame.empty:
            st.info(
                "Awaiting a certified target-week champion slate and fresh admitted inputs."
            )
        else:
            game = st.selectbox(
                "Numerical research fixture",
                sorted(frame.game_id.unique()),
                key="numeric_script_fixture",
            )
            current = frame[frame.game_id.eq(game)]
            columns = {
                "player": "Player",
                "market": "Market",
                "baseline": "Original",
                "adjusted": "Experimental",
                "delta": "Change",
                "prior_opportunities": "Recent workload",
                "allocated_opportunities": "Structural opportunities",
                "predicted_share": "Workload share",
            }
            st.dataframe(
                current[list(columns)].rename(columns=columns).round(2),
                hide_index=True,
                width="stretch",
            )
            player = st.selectbox(
                "Explain numerical change",
                list(current.index),
                format_func=lambda i: (
                    f"{current.loc[i, 'player']} · {current.loc[i, 'market']}"
                ),
                key="numeric_script_player",
            )
            row = current.loc[player]
            st.write(
                f"{row.player}: original {row.baseline:.2f} → experimental {row.adjusted:.2f} ({row.delta:+.2f}). Recent workload averaged {row.prior_opportunities:.2f}; the raw allocation estimates {row.allocated_opportunities:.2f} opportunities. The final change is a historically fitted residual correction, not a direct replacement with that raw allocation."
            )
            t = teams[teams.game_id.eq(game) & teams.team.eq(row.team)].iloc[0]
            st.write(
                f"{row.team}: expected {t.expected_plays:.1f} offensive plays, {t.expected_attempts:.1f} pass attempts and {t.expected_carries:.1f} carries. Win {t.win_probability:.1%}; expected margin {t.expected_margin:+.1f}."
            )
            st.dataframe(
                pd.DataFrame(
                    {
                        "State": ["Leading", "Tied", "Trailing"],
                        "Expected share of offensive plays": [
                            t.prob_leading,
                            t.prob_tied,
                            t.prob_trailing,
                        ],
                        "Weighted team plays": [
                            t.plays_leading,
                            t.plays_tied,
                            t.plays_trailing,
                        ],
                        "Weighted player opportunities": [
                            row.weighted_player_opportunities_leading,
                            row.weighted_player_opportunities_tied,
                            row.weighted_player_opportunities_trailing,
                        ],
                    }
                ).round(3),
                hide_index=True,
                width="stretch",
            )
            st.caption(
                f"Overlay made {row.prediction_at}; original forecast {row.baseline_prediction_at}. State percentages describe a randomly selected offensive play, not the chance of leading throughout the game. Historic roster availability and matchup uncertainty remain; no injury or defensive-scheme facts are invented."
            )
            if row.cap_applied:
                st.caption("The predeclared adjustment cap limited this change.")
    with st.expander("Historical numerical evidence and promotion decision"):
        st.write("Promotion: FAILED / CHAMPION RETAINED")
        for reason in report["promotion_reasons"]:
            st.caption(reason)
        metrics = pd.read_parquet(DEFAULT / "metrics.parquet")
        season = st.selectbox(
            "Numerical evaluation season",
            sorted(metrics.season.unique()),
            index=3,
            key="numeric_script_season",
        )
        st.dataframe(
            metrics[metrics.season.eq(season)][
                [
                    "market",
                    "baseline_n",
                    "baseline_mae",
                    "adjusted_mae",
                    "mae_gain",
                    "baseline_rmse",
                    "adjusted_rmse",
                    "baseline_bias",
                    "adjusted_bias",
                    "baseline_brier",
                    "adjusted_brier",
                    "baseline_coverage90",
                    "adjusted_coverage90",
                ]
            ],
            hide_index=True,
            width="stretch",
        )
        st.caption(
            "2025 selected the scale;2026weeks1–10 are previously inspected diagnostics. Historical comparator uses chronological replicas of the champion recipe, not leaked forecasts from the frozen2026 weights. Player Brier/interval columns are constant-scale normal diagnostics at hypothetical half-lines, not certified prices or genuine betting results."
        )
        st.dataframe(
            pd.read_parquet(DEFAULT / "team_metrics.parquet"),
            hide_index=True,
            width="stretch",
        )
        st.dataframe(
            pd.read_parquet(DEFAULT / "ablations.parquet").query("season==@season")[
                ["market", "ablation", "baseline_n", "adjusted_mae", "mae_gain"]
            ],
            hide_index=True,
            width="stretch",
        )
        st.caption(
            "Ablations are reported, not retrospectively selected for deployment. Failed/missing context stays on baseline in identical populations."
        )
    with st.expander("Early Week12 team-only preview — not a certified player slate"):
        preview = pd.read_parquet(DEFAULT / "week12_team_preview.parquet")
        st.dataframe(
            preview[
                [
                    "game_id",
                    "team",
                    "prediction_at",
                    "win_probability",
                    "expected_margin",
                    "expected_plays",
                    "expected_attempts",
                    "expected_carries",
                    "prob_leading",
                    "prob_tied",
                    "prob_trailing",
                ]
            ],
            hide_index=True,
            width="stretch",
        )
        st.caption(
            "This early preview uses only admitted pre-seal history throughWeek10 and the timestamped fixture plan. No Week11 results or stale Week11 player eligibility are substituted."
        )


def render_weekly_status(root):
    with st.expander("Numerical challenger: weekly monitoring"):
        reports = sorted((Path(root) / "script_evaluations").glob("*/report.json"))
        if not reports:
            st.info(
                "No prospective numerical challenger results yet. Forecast sidecars freeze before T−60; scoring requires authorised completed-game admission. No challenger is promoted automatically."
            )
            return
        path = reports[-1]
        try:
            Store(root).validate(path.parent)
            r = json.loads(path.read_text())
            st.write(r["cycle_id"])
            st.json(r["measured"])
            st.dataframe(
                pd.read_parquet(path.parent / "team_metrics.parquet"),
                hide_index=True,
                width="stretch",
            )
            st.caption(
                "Observed game-state/team-volume errors and workload/efficiency decompositions are monitoring evidence, not unique causal explanations or untouched final validation."
            )
        except (OSError, ValueError, KeyError):
            st.warning(
                "Numerical monitoring failed integrity checks; champion retained."
            )
