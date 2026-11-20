"""Read-only experimental scenarios; no changes to certified forecasts/pricing."""

import json
from datetime import UTC, datetime, timedelta

import pandas as pd
import streamlit as st

from .sunday_script import OUT, ROOT, digest


def render(release):
    with st.expander(
        "Experimental game script — separate from certified forecasts", expanded=False
    ):
        try:
            manifest = json.loads((OUT / "manifest.json").read_text())
            if manifest["final_period_sealed"] is not True or manifest[
                "code_sha256"
            ] != digest(ROOT / "research_platform/sunday_script.py"):
                raise ValueError("Experiment code/provenance differs")
            for name, checksum in manifest["files"].items():
                if Path(name).name != name or digest(OUT / name) != checksum:
                    raise ValueError("Experiment integrity mismatch")
            for name, checksum in manifest["inputs"].items():
                path = (ROOT / name).resolve()
                path.relative_to(ROOT)
                if digest(path) != checksum:
                    raise ValueError("Experiment input changed")
            report = json.loads((OUT / "report.json").read_text())
            if (
                report["source_release"] != release["release_id"]
                or report["activation"] is not False
            ):
                raise ValueError("Wrong release or activation policy")
            games = pd.read_csv(OUT / "sunday_games.csv")
            players = pd.read_parquet(OUT / "sunday_experimental.parquet")
        except (OSError, ValueError, KeyError, TypeError):
            st.info(
                "Experimental scenario bundle unavailable or failed integrity checks. Certified forecasts remain unchanged."
            )
            return
        st.warning(
            "EXPERIMENTAL — NOT ACTIVATED. These probabilities describe the final score margin, not how long a team leads or trails during the game. Previously inspected historical data is not a fresh independent test. No adjusted probability, EV or bet recommendation is supplied."
        )
        recent = next(m for m in report["team_metrics"] if m["season"] == 2026)
        st.caption(
            f"2026 holdout: {recent['n']} games; win Brier {recent['win_brier']:.4f}, log loss {recent['win_log_loss']:.4f}; home-margin bias {recent['bias']:+.2f} points. Probability bands are uneven; these figures are not calibrated betting prices."
        )

        from sgo_research.contracts import utc

        eligible = [
            gid
            for gid, when in release["game_kickoffs"].items()
            if datetime.now(UTC) < utc(when) - timedelta(minutes=60)
        ]
        if not eligible:
            st.info("No fixtures remain before the T−60 decision cutoff.")
            return
        gid = st.selectbox(
            "Experimental fixture", eligible, key="experimental_script_fixture"
        )
        for _, row in games[games.game_id.eq(gid)].iterrows():
            st.markdown(
                f"**{row.team}** · expected margin {row.expected_margin:+.1f} points · win {row.win_probability:.1%}"
            )
            st.caption(
                f"Final margin: behind by 8+ {row.p_trailing:.1%} · within 7 {row.p_close:.1%} · ahead by 8+ {row.p_leading:.1%}. Historical data available through {row.history_available_at}; {int(row.cdf_n)} earlier out-of-sample residual observations."
            )
            st.dataframe(
                pd.DataFrame(
                    {
                        "Final-margin scenario": [
                            "Behind by 8+",
                            "Within 7",
                            "Ahead by 8+",
                        ],
                        "Team pass attempts": [
                            row.attempts_trailing,
                            row.attempts_close,
                            row.attempts_leading,
                        ],
                        "Team carries": [
                            row.carries_trailing,
                            row.carries_close,
                            row.carries_leading,
                        ],
                    }
                ).round(1),
                hide_index=True,
                width="stretch",
            )
        frame = players[players.game_id.eq(gid)]
        if frame.empty:
            st.info(
                "No complete player forecasts; roof scenarios and unresolved eligibility remain excluded."
            )
            return
        keys = list(frame.index)
        chosen = st.selectbox(
            "Player / prop",
            keys,
            format_func=lambda i: (
                f"{frame.loc[i, 'player']} · {frame.loc[i, 'market']}"
            ),
            key="experimental_script_player",
        )
        row = frame.loc[chosen]
        st.write(
            f"Certified baseline: {row.baseline:.1f}. Experimental projection: {row.adjusted:.1f}. Difference: {row.adjusted - row.baseline:+.1f}. The certified projection and its pricing remain unchanged."
        )
        st.dataframe(
            pd.DataFrame(
                {
                    "Final-margin scenario": [
                        "Behind by 8+",
                        "Within 7",
                        "Ahead by 8+",
                    ],
                    "Exploratory player projection": [
                        row.projection_trailing,
                        row.projection_close,
                        row.projection_leading,
                    ],
                }
            ).round(1),
            hide_index=True,
            width="stretch",
        )
        st.caption(
            "Scenario workloads are associations learned from prior games grouped by final margin, not causal effects. Individual allocation coherence and in-game state occupancy have not been validated. Team carries include all positions; QB scrambles are not inferred from RB-style lead protection."
        )
        st.markdown("**2026 chronological holdout — all nine markets**")
        table = [
            {
                "Market": r["market"],
                "N": r["baseline"]["n"],
                "Baseline MAE": r["baseline"]["mae"],
                "Adjusted MAE": r["adjusted"]["mae"],
                "Unselected full-strength MAE": next(
                    c["mae"] for c in r["candidate_holdout_metrics"] if c["weight"] == 1
                ),
                "MAE change %": -100 * r["relative_mae_gain"],
                "Bias": r["adjusted"]["bias"],
                "95% paired MAE change": str(
                    [round(v, 3) for v in r["paired_mae_delta95"]]
                ),
            }
            for r in report["player_metrics"]
        ]
        st.dataframe(pd.DataFrame(table).round(3), hide_index=True, width="stretch")
        st.caption(
            "Historical baseline uses archived chronological Stage 1B models, not the November-trained live models; applying those live models to earlier 2026 games would leak training outcomes."
        )
        st.caption(
            "Model selection used 2025 only, following adjustment fitting on 2022–24. 2026 Weeks 1–10 were held out from this experiment’s fitting and selection but had been inspected in previous research. No player probability calibration is claimed for the adjusted point forecasts."
        )


from pathlib import Path
