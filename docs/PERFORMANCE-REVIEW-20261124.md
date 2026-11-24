# Initial performance review — 24 November 2026

Immutable study: `weekly_learning_state/performance_research/studies/0d41c795f1eb3b4ec9d50cc6`. Python 3.14.10.

55,782 historical observations, nine markets. Methods selected on 2025 only. 2026 Weeks 1–10 are previously inspected diagnostics, not a fresh final test. No original models were retrained. Historical comparisons use chronological reconstructions of the method families; November-trained frozen models are never applied retrospectively to earlier games.

## Point forecasts — inspected 2026 diagnostics

| Market | n | Reconstructed Stage 1A MAE | Current research MAE | 2025-selected challenger | Challenger MAE | Gain vs current research |
|---|---:|---:|---:|---|---:|---:|
| completions | 311 | 5.649 | 5.398 | context_tree | 5.398 | +0.00% |
| passing_attempts | 311 | 8.065 | 8.065 | context_tree | 7.933 | +1.64% |
| passing_yards | 311 | 67.004 | 67.004 | context_tree | 67.123 | -0.18% |
| qb_rushing_attempts | 311 | 1.765 | 1.765 | baseline | 1.765 | +0.00% |
| qb_rushing_yards | 311 | 11.242 | 11.242 | context_tree | 10.950 | +2.60% |
| receiving_yards | 2010 | 19.333 | 18.639 | context_tree | 18.639 | +0.00% |
| receptions | 2014 | 1.437 | 1.405 | context_tree | 1.405 | +0.00% |
| rushing_attempts | 639 | 3.888 | 3.782 | context_tree | 3.782 | +0.00% |
| rushing_yards | 638 | 21.773 | 20.752 | context_tree | 20.752 | +0.00% |

The five current research improvements shown against Stage 1A were already implemented; they are not new gains from this task. No fixed recent-form or workload/efficiency weighting won the registered 2025 method selection. Passing attempts (+1.64%) and QB rushing yards (+2.60%) have uncertain diagnostic advantages; their paired intervals include zero. Passing yards regresses 0.18%. No new point method passes the full evidence requirement or is activated.

## Probability comparison

| Market | Champion log loss | Current research log loss | 2025-selected method | Diagnostic log loss |
|---|---:|---:|---|---:|
| completions | 0.64943 | Unavailable | research_empirical | 0.64220 |
| passing_attempts | 0.64086 | 0.64086 | champion_normal | 0.64086 |
| passing_yards | 0.65805 | 0.65805 | champion_normal | 0.65805 |
| qb_rushing_attempts | 0.63791 | 0.63791 | champion_normal | 0.63791 |
| qb_rushing_yards | 0.64453 | 0.61195 | baseline_empirical_shrunk_isotonic | 0.61503 |
| receiving_yards | 0.63817 | 0.61655 | research_empirical | 0.61655 |
| receptions | 0.63174 | 0.62045 | research_empirical | 0.62045 |
| rushing_attempts | 0.63773 | 0.62131 | research_empirical | 0.62131 |
| rushing_yards | 0.63817 | 0.61410 | research_empirical | 0.61410 |

The newly selected shrunk-isotonic QB-rushing-yards alternative improves over the normal champion, but is **0.50% worse than the empirical method already used by the research engine**. It is rejected as a replacement. Other chosen probability methods are retained existing methods, not new improvements. Completion pricing remains unavailable in the current research engine; its point improvement is not a validated pricing upgrade.

## Predictive findings and data limitations

- Adding role/workload features to the same ridge backbone improves descriptive 2026 MAE in all nine markets, by 0.20%–2.21%. Adding team/opponent context to that role backbone improves only the three passing markets (0.07%–0.46%) and regresses the other six. This is not evidence that any particular defence causes an individual result.
- The nonlinear context-tree comparison changes both the model backbone and its use of context; its improvement cannot be attributed to matchup features alone.
- Player-history length, position and pregame playing-time changes are separately reported in 116 cohort rows. Small cohorts do not become selectively deployed segments.
- Archived receiving inputs omit career target volume. Workload comparisons use only available last-three/last-five target means and shrunk efficiency; missing inputs retain the champion and are counted.
- The legacy frozen-slate column career_avg is actually the first model input, currently season average. Prospective tests use a separately named season/recent experiment and do not misrepresent it as the historical true-career experiment.
- This is a confirmed-participation/stat-observation cohort, not a complete historical bookmaker opportunity universe. Missing players, uncertain availability and void rules prevent unconditional betting-success claims.
- Timing checks pass for reconstructed features/model fits. Original publication timing for inherited market-context inputs and historical roster evidence remains incompletely verified.
- Genuine bookmaker quotes, alternate-line availability, combined ticket prices and settlement records are not available in this study. Price-matched hit rates, realised ROI and complete accumulator performance are therefore not estimated.

## Action taken

Added strictly predecision captures of three fixed season/recent workload challengers to the existing weekly pipeline. Post-cutoff evaluation requires the existing operational finality receipt and matching model/game identities. Genuine zero outcomes remain zero; missing outcomes remain unscored. No accepted change, automatic promotion, schedule activation or production change occurs. The protocol, source hashes and runtime are recorded; cached reruns are replay, not new validation.

The next commercial evidence must come from frozen genuine quotes and offered ticket prices. Top Picks will be compared at equal odds bands/counts and Top 2 ticket strategies at equal ticket sizes/prices and paper budgets. Neither higher MAE accuracy nor a high illustrative-line hit rate can substitute for that test.
