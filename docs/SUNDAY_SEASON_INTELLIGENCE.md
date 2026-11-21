# Sunday 22 November 2026 — player intelligence research

**Research only. No model, probability, slate or betting recommendation has been promoted. No profitability claim.**

## Evidence and data corrections

55,782 matched player-market observations / 1,237 games / 7,622 genuine zeros. 2022–24 annual-origin development; 2025 method selection; 6,856 observations in previously inspected 2026 Weeks1–10 diagnostics. All fits use earlier available outcomes, with the inherited36-hour historical publication proxy. The final period remains sealed.Each2026 replay fit uses only pre-season outcomes; pregame histories update each game. The weights were actually fitted on21November, not historically before the season. The fit_before/model_fit_before fields denote training-outcome availability cutoffs, not actual file creation timestamps; actual build timestamps are recorded separately. This is annual rolling-origin replay, not weekly re-estimation.

The original research PBP/player snapshot contained only one Week10 game. The certified20November features provide the remainder. Some refreshed2026 stored legacy history counts reset despite2019–25 raw history being present. The research copy now rebuilds entering-game features with the unchanged shared calculators, preserving cross-season history and matching all compared populations. Older observed data may fill a missing refresh field only when canonical player/game/team identity agrees; no observed box records required this recovery. No missing outcome becomes zero. OAK/LV and other existing C0 aliases use the established canonical mapping. Neither source file nor any certified forecast was edited. A preliminary incomplete-history comparison was discarded before inspecting error metrics.

Five preregistered point families: recent workload shrinkage; player-only ridge; role/share/efficiency ridge; opponent/team ridge; robust nonlinear context tree. Same-backbone ridge ablations isolate feature-family effects. Tree gains combine backbone and feature effects and cannot establish that matchup variables caused improvement. Grouped permutation diagnostics are within2026week/position, exploratory and affected by feature correlation. No current teammate participation list is inferred from actual participants. Historical active-roster, injury, route and defensive personnel publication evidence remains unavailable.

## Fixed selection and inspected2026 results

| Market |2026 n| Baseline MAE | Research MAE | Gain |2025 point gate|
|---|---:|---:|---:|---:|---|
|completions|311|5.649|5.398|+4.44%|True|
|passing_attempts|311|8.065|8.065|+0.00%|False|
|passing_yards|311|67.004|67.004|+0.00%|False|
|qb_rushing_attempts|311|1.765|1.765|+0.00%|False|
|qb_rushing_yards|311|11.242|11.242|+0.00%|False|
|receiving_yards|2010|19.333|18.639|+3.59%|True|
|receptions|2014|1.437|1.405|+2.22%|True|
|rushing_attempts|639|3.888|3.782|+2.74%|True|
|rushing_yards|638|21.773|20.752|+4.69%|True|

The point gate requires≥2% selection MAE gain, paired week-block uncertainty and Holm correction across45 comparisons. Five markets pass those retrospective point gates. Passing yards, attempts and both QB rushing point markets retain baseline estimates; the better-looking2026 QB-carry alternative was not selected retrospectively. No independent final evidence or automatic promotion is claimed. Raw failed candidates remain visible only as experimental comparisons.

## Probability evidence

The research CDF uses shrinking conditional empirical nonzero errors, an explicit observed zero atom, and integer support (negative yardage allowed; negative counts excluded). It is fitted on annual out-of-sample residuals from strictly earlier seasons. Count/yardage distributions are not assumed normal. Zero mass is conditional on established participation, not an invented probability of inactivity. Injury, no-play and bookmaker void conditions still require source/settlement evidence. Sunday point models are refitted using permitted completed history; their newer weights have not themselves received fresh independent testing. Sunday CDFs remain fitted on2022–25 OOF data, not2026 diagnostics.

| Market |2026 normal log loss| Research log loss| Normal Brier| Research Brier|2025 probability gate|
|---|---:|---:|---:|---:|---|
|completions|0.6494|0.6422|0.2287|0.2217|True|
|passing_attempts|0.6403|0.6334|0.2243|0.2214|False|
|passing_yards|0.6571|0.6569|0.2323|0.2323|False|
|qb_rushing_attempts|0.6379|0.6290|0.2233|0.2193|False|
|qb_rushing_yards|0.6232|0.5726|0.2162|0.1969|True|
|receiving_yards|0.6149|0.5657|0.2122|0.1955|True|
|receptions|0.6179|0.5926|0.2140|0.2062|True|
|rushing_attempts|0.6295|0.6025|0.2191|0.2091|True|
|rushing_yards|0.6242|0.5839|0.2167|0.2014|True|

Primary probability scores use three predeclared illustrative half-lines around the champion projection, never historical bookmaker quotes. Six markets meet the2025 probability rule (≥2% log-loss reduction without Brier deterioration); passing yards/attempts and QB carries do not. Only that retrospective rule is reported, not full promotion. Probability uncertainty, bands, both sides and positions are saved separately; repeated lines are not treated as independent games. Receiving-yard2025 ECE is1.20 percentage points, best among these research markets. The shortlist therefore concentrates on receiving yards; cross-market Brier alone must not be interpreted as proof of betting quality.

2026 90% interval coverage remains conservative for low count markets (receptions about95.8%, QB carries95.5%). Passing-yard intervals widen to restore coverage; a narrower interval is not automatically better. Integer-line diagnostics evaluate actual pushes and three-way probabilities separately; they do not validate any real bookmaker rule or price. Conditional refund-push fair odds are(1−P(push))/P(win). Experimental EV at a user-supplied decimal quote isP(win)×(odds−1)−P(loss). No integer-line selection or real-money recommendation is automated.

## Sunday research shortlist

522 eligible forecasts /10Sunday fixtures /20Top2 entries. TEN–DAL unresolved roof scenarios are excluded; the Monday-night fixture is not relabelled Sunday. The original618-row release,568complete forecasts,50roof scenarios and22baseline Top Picks are untouched. Eligibility uses the dated20November certificate, not live injury news. These new build timestamps do not pretend the source evidence was refreshed today. All opportunities stop being current atT−60.

| Player |Market| Original | Candidate | Hypothetical line | Research over probability |
|---|---|---:|---:|---:|---:|
|Justin Jefferson|receiving_yards|71.5|64.3|71.5|45.0%|
|Darius Cooper|receiving_yards|28.1|22.1|28.5|40.0%|
|Makai Lemon|receiving_yards|46.2|34.7|46.5|36.5%|
|Jordan Addison|receiving_yards|46.4|43.9|46.5|48.3%|
|Germie Bernard|receiving_yards|36.4|38.3|36.5|52.1%|
|Devaughn Vele|receiving_yards|32.6|33.6|32.5|51.2%|
|Rome Odunze|receiving_yards|54.0|49.3|54.5|46.0%|
|DK Metcalf|receiving_yards|49.4|53.4|49.5|56.3%|
|Chuba Hubbard|receiving_yards|22.1|22.9|22.5|44.7%|
|Colston Loveland|receiving_yards|52.7|47.4|52.5|42.1%|
|George Kittle|receiving_yards|60.3|61.1|60.5|48.3%|
|Sam LaPorta|receiving_yards|45.2|37.1|45.5|40.2%|

**The lines above are illustrative, not available bookmaker lines. These are player-prop research priorities, not Over/Under bets or positive-EV claims.** The empirical distribution is asymmetric, so its median/over probability need not agree with a regression point forecast; the latter is not claimed to be the CDF mean. Unpassed probability families are displayed as explicitly experimental, not selected methods.

## Access and safeguards

Existing research app → Game Intelligence → Sunday player-workload and probability research. Expand the supplied-line calculator to enter a real quote; prices start empty. Integer EV requires owner-confirmed full-stake refund rules. All output is experimental and isolated from production pricing/ledger/recommendations. Original nine model hashes and baseline projections are checked unchanged. The historical model and Sunday model numerical replay tolerance is absolute1e−10, relative zero; file/source/model hashes and original baseline copies remain exact.

No SportsGameOdds calls, quota edits, credentials, production/main changes, new services, billing or schedules. Existing free runtime/dependencies only. No historical sportsbook ROI is calculable from these inputs.
