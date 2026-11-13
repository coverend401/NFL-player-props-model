"""Standalone experimental dashboard: streamlit run stage1b_dashboard.py.

No secrets, ledger, authentication or bankroll settings from production are read.
"""

from pathlib import Path
import json
import pandas as pd
import streamlit as st
from stage1b.artifacts import validate
from stage1b.betting import economics

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Stage 1B validation lab", layout="wide")
st.title("Forecast validation lab — experimental")
st.warning(
    "Research only. Production Stage 1A is unchanged. Historical probes are not bookmaker lines or realised betting returns."
)
paths = sorted(p.parent for p in (ROOT / "experiments/stage1b").glob("*/manifest.json"))
if not paths:
    st.info(
        "No validated experiment yet. Run python -m stage1b.runner --id YOUR_ID in the pinned Python 3.14 environment."
    )
    st.stop()
path = st.selectbox("Experiment", paths, format_func=lambda p: p.name)
try:
    manifest = validate(path, ROOT)
except Exception as e:
    st.error("Experiment integrity/runtime check failed: " + str(e))
    st.stop()
st.caption(
    f"{manifest['experiment_id']} · source {manifest['source_commit'][:8]} · {manifest['n_player_games']:,} scored player-market games"
)
st.info(
    "Final evaluation remains SEALED: 2026 week 11 onward. All displayed results are retrospective development OOS or monitoring."
)
a = pd.read_csv(path / "accuracy.csv")
pm = pd.read_csv(path / "probability_metrics.csv")
r = pd.read_csv(path / "reliability.csv")
coverage = pd.read_csv(path / "coverage.csv")
market = st.selectbox("Market", sorted(a.market.unique()))
tier = st.selectbox("Evaluation period", ["development_oos", "monitoring"])
tabs = st.tabs(
    [
        "Accuracy",
        "Calibration",
        "Versions and uncertainty",
        "Historical betting",
        "Hypothetical pricing",
        "Provenance",
    ]
)
with tabs[0]:
    st.subheader("Accuracy by season and cohort")
    st.caption(
        "Identical pregame point engine is used for both probability versions. Bias = prediction minus outcome. Counts condition on observed offensive participation and complete features."
    )
    st.dataframe(a[a.market == market], hide_index=True)
    st.subheader("Coverage and missing observations")
    st.dataframe(coverage[coverage.market == market], hide_index=True)
with tabs[1]:
    st.dataframe(
        pm[(pm.market == market) & (pm.evaluation_tier == tier)], hide_index=True
    )
    data = r[(r.market == market) & (r.evaluation_tier == tier)]
    st.line_chart(
        data.pivot_table(index="mean_probability", columns="version", values="observed")
    )
    st.dataframe(data, hide_index=True)
    st.caption(
        "Diagonal means calibrated. Wilson bands are descriptive probe-level intervals and do not account for repeated thresholds/players; do not treat them as individual probability confidence intervals. Band and main score intervals use week-block bootstrap; sparse bands may have no interval. These intervals condition on fitted models and do not include full model-selection uncertainty."
    )
with tabs[2]:
    differences = pd.read_csv(path / "paired_differences.csv")
    st.dataframe(
        differences[
            (differences.market == market) & (differences.evaluation_tier == tier)
        ],
        hide_index=True,
    )
    st.caption(
        "Negative deltas favour Stage 1B. Multiple-market comparisons are exploratory; a confidence interval crossing zero does not establish improvement."
    )
    selected = pd.read_json(path / "folds.json")
    st.dataframe(
        selected[selected.market == market].drop(
            columns=["point_selection_mae", "phase_n"]
        ),
        hide_index=True,
    )
    st.caption(
        "Methods are chosen on earlier-season weeks 15–18, never on the displayed evaluation season. 2026 is monitoring, not the untouched final test."
    )
with tabs[3]:
    status = json.loads((path / "betting_status.json").read_text())
    st.write(status)
    st.info(
        "No authentic historical prop odds are bundled. There is no historical betting ROI, profit or verified win-rate claim. A forecast accuracy improvement is not evidence of a tradable edge."
    )
with tabs[4]:
    st.subheader("Manual probability economics — hypothetical, not a recommendation")
    win = st.number_input("Win probability", 0.0, 1.0, 0.5, 0.01)
    push = st.number_input("Push probability", 0.0, 1.0, 0.0, 0.01)
    odds = st.number_input("Illustrative decimal odds", 1.01, 100.0, 1.91, 0.01)
    try:
        st.write(economics(win, push, odds))
    except ValueError as e:
        st.error(str(e))
    st.caption(
        "No stake is sent to production. Kelly assumes correct stationary probabilities and executable prices; neither is established here."
    )
with tabs[5]:
    st.json(
        {
            k: v
            for k, v in manifest.items()
            if k not in ["files", "runtime", "source_hashes"]
        }
    )
    st.json(json.loads((path / "protocol.json").read_text()))
    st.caption(
        "Current stat snapshots may contain later corrections. No historical injury/roster publication snapshots exist. Closing lines and unverified matchup fields are excluded. Saved folds allow Stage 1C to use exactly the same population and protocol."
    )
