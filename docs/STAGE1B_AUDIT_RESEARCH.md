# Stage 1B audit and research

Production baseline: verified Stage 1A release `stage1a-20261113-py314-arrow24-r2`,
main merge `34c69fad0295040b886d818a0ed48fb3cc65c9c5`. This lab neither imports the
production app nor changes its source, models, pointer, dependencies or ledger.

## Verified findings in the current code

- `scripts/train_all_markets.py` uses a last-complete-season split, compares Ridge
  and gradient boosting on that season and chooses the winner. That season is
  **validation**, not an untouched test. Its calibration summary also evaluates
  threshold events at a player's historical mean, not an actual bookmaker line.
- The final normal residual scale is standard deviation of fitted residuals after
  refitting on all eligible observations. It is not an out-of-sample predictive
  uncertainty estimate. Bias, heteroskedasticity, skew and tail dependence are not
  represented. Whether this materially harms a market must be measured.
- `pricing.py` uses `1-normal.cdf(line)` for Overs and its complement for Unders.
  Integer lines have no push probability in this calculation. Over/under fair
  prices and Kelly need win/loss/push partitions instead.
- `betting_engine.py` confidence and bet-score weights, injury factors and fixed
  market-error constants are hand-set heuristics, not calibrated win probabilities
  or statistical confidence levels. A calibration score of 0.7 in an empty bucket
  means unknown in that code, not evidence of reliability. Selected-bet ledger
  calibration cannot establish calibration across all eligible forecasts.
- Existing expanding `*_season_avg` fields actually span career history across
  seasons. They are retained for compatibility; the lab calls this a career mean.
- Stage 1A corrected same-game eligibility and lag alignment. Its participation
  panel retains observed zero-stat games and unknown box scores separately.
  The evaluation preserves those distinctions, not positive attempts/targets.
- Historical game context includes closing game lines without capture timestamps.
  A closing total known just before kickoff need not have been known one hour
  before kickoff. It is excluded, together with roof, opponent-strength, NGS,
  retrospective depth charts and injury fields, from this strict-feature benchmark.
- `performance.max_drawdown` can miss a first-bet loss because its curve omits the
  initial zero balance. The isolated Stage 1B accountant starts at bankroll and
  reserves simultaneous stakes; production accounting is not modified here.
- No timestamped bookmaker player-prop archive or genuine historical prop-price
  backtest exists in the repository. The personal ledger is not queried.

## Market-specific distributions

| Market | Relevant support/problem | Implemented comparisons |
|---|---|---|
| Passing yards | Whole yards; skew, injuries and changing workload; signed support retained | Normal OOS; empirical and scaled residual CDF; nonzero hurdle; quantile CDF |
| Passing attempts | Nonnegative count; variable opportunity/variance | Above plus Poisson regression mean and NB2 held-out dispersion |
| Completions | Count jointly constrained by attempts | Count comparisons; actual same-game attempts NEVER supplied as binomial trials |
| RB rushing yards | Heavy right tail, true zeros, occasional negative yards | Signed empirical/hurdle/quantile versus normal |
| RB rushing attempts | Nonnegative overdispersed count and role mixture | Poisson/NB2/hurdle/empirical/quantile |
| QB rushing yards | Zero-heavy; kneeldown negatives; scrambling tail | Signed hurdle/empirical/quantile; never log-transform away negatives |
| QB rushing attempts | Zero-heavy count; role heterogeneity | Count comparisons and learned zero probability |
| Receiving yards | Compound opportunity/efficiency, zeros and occasional negatives | Signed empirical/hurdle/quantile versus normal |
| Receptions | Nonnegative count with target/role uncertainty | Count comparisons and hurdle |

The hurdle model learns zero probability from pregame features in the training
period and nonzero outcome CDFs in prediction-mean bins on a later held-out period.
It is not a zero-inflated Poisson fit: a hurdle models the total zero mass directly.
NB2 overdispersion is estimated on held-out observations, not fitted residuals.
Quantile models use .1/.5/.9 quantiles, monotone rearrangement and explicitly
approximate bounded linear tails; tail accuracy must not be presumed. Empirical
methods also have limited observed tail support. Poisson imposes mean=variance;
negative binomial relaxes that but may still miss role mixtures.

Gamma, lognormal and Tweedie/compound opportunity models merit later experiments,
but none universally supports the negative yardage present here. A binomial
completions or receptions model would require forecasting its trials, not reading
actual same-game attempts/targets. That joint opportunity task is not smuggled into
this probability benchmark as a supposedly known covariate.

The point engine is common to both probability versions: career mean, Ridge and
Stage 1A's 200-tree boosting recipe compete on an earlier season, then the chosen
engine is refitted strictly before distribution fitting. Count point predictions
are constrained to >=0. Both versions use the SAME point prediction/population.
The legacy normal-rule benchmark therefore isolates probability changes. It is
**not** a claim to have reconstructed historical production Stage 1A predictions:
the final production pickles contain later outcomes and unverified closing context.

## Proper scores and calibration

Brier score and binary log loss are computed at three preregistered **hypothetical**
half-lines based only on the player's career mean (.5x, 1x, 1.5x, floored + .5).
They are pricing probes, not reconstructed market lines or prices. Each player-game
has total weight one even when its three thresholds coincide. Calibration uses a
later disjoint period, and method selection a still later disjoint period.

Identity, nonnegative-slope logistic/sigmoid and isotonic calibration are compared.
Calibration transforms the predictive CDF monotonically, so integer-line push mass,
strict unders and strict overs remain coherent. The legacy comparator is scored
only at half-lines, where its original normal formula is reproduced exactly.
Calibrated probe probabilities need not transfer to actual offered market lines.

Report MAE/RMSE/bias, zeros, sample sizes, naive career-mean accuracy, quantile
pinball scores, 90% interval width/coverage, proper scores, probability-band
reliability and selected method by market/year/cohort. Main score uncertainty and
paired differences use a seeded four-week moving-block bootstrap. This handles
within-week dependence and some serial persistence, not arbitrary long-run player
or multi-season dependence. Wilson bands in the reliability table are explicitly
**descriptive**, not independent-observation or individual-probability intervals.
Multiple methods/markets and small QB selection cohorts still create selection
risk. All retrospective periods are development/monitoring, not a final claim.

## Available odds and settlement evidence

The NFL snapshot contains player/game outcomes and game-context lines, not prop
quotes, both-side prices, booking availability or historical rule documents.
Public nflverse data does not supply the required prop-price provenance here.
This does not establish that no free archive exists anywhere.

The Odds API's official Python samples include `historical_event_odds.py` and
`historical_odds.py`, with a historical date, sport, event, region, markets and API
key. Historical additional-market access, coverage, pricing and entitlement must
be verified with a licensed account. No account, API key, purchased dataset or
provider historical payload is available to this lab. Its main API guide was
network-blocked here, so advertised coverage dates are not treated as verified.
Other licensed vendors (e.g. SportsDataIO/Sportradar) are research options, not
assumed accessible datasets. Unverified scraped lines/odds and today's prices are
not substitutes for historical executable quotes.

The importer requires identity, bookmaker, market, side, line, decimal price,
quote/publication/decision/kickoff times, a reviewed settlement rule, a credential-free
provider URL, original archive bytes and a hash-bound reviewed extraction. Hashes
prove integrity, not independent historical authenticity: the owner must review
provider identity, licence and extraction against original responses. Synthetic
unit-test fixtures only test software; they NEVER populate betting results.

The historical policy chooses the most recent sufficiently fresh available quote,
then the earliest eligible decision per player-market-game, never the best
retrospective price. Its line must exactly match a timestamped model forecast;
no interpolation from synthetic probes. Actual quoted prices already include
bookmaker margin. Two-sided margin removal is a separate diagnostic, conditional
on no push; it is not an extra fee subtracted from returns. Exchange commission,
quarter-line settlements, parlays and arbitrary book-specific rules are unsupported.

Only an explicitly documented positive-offensive-participation action rule is
implemented. No offensive snaps is NOT proof of a void. Unknown action or missing
outcomes block realised-return reporting rather than becoming exclusions or losses.
Push/verified void refund stakes; open stakes reserve cash and returns become
available only at recorded settlement availability. Currency is generic stake units.

## Sources consulted

- [Arrow issue and Cloud constraint](STAGE1A_ARROW24_CORRECTION.md): retain the
  already validated Python 3.14 / Arrow 24 environment.
- [scikit-learn calibration guide](https://scikit-learn.org/stable/modules/calibration.html),
  also retrieved from the official GitHub source: disjoint calibration, sigmoid,
  isotonic and reliability diagrams.
- [scikit-learn quantile regression example](https://scikit-learn.org/stable/auto_examples/ensemble/plot_gradient_boosting_quantile.html):
  pinball loss and conditional interval coverage.
- [SciPy probability distributions](https://docs.scipy.org/doc/scipy/reference/stats.html):
  count support/CDFs and negative-binomial parameterisation.
- Gneiting & Raftery (2007), *Strictly Proper Scoring Rules, Prediction, and
  Estimation*, JASA, DOI [10.1198/016214506000001437](https://doi.org/10.1198/016214506000001437).
- Dawid (1984), *Statistical Theory: The Prequential Approach*, JRSS A,
  DOI [10.2307/2981683](https://doi.org/10.2307/2981683).
- Kelly (1956), *A New Interpretation of Information Rate*, Bell System Technical
  Journal, DOI [10.1002/j.1538-7305.1956.tb03809.x](https://doi.org/10.1002/j.1538-7305.1956.tb03809.x).
- [The Odds API official Python samples](https://github.com/the-odds-api/samples-python):
  historical-event endpoint availability verified from source; account entitlement
  and historical prop coverage not verified.

References motivate the protocol; they do not establish this model's calibration
or profitability. Those require measured out-of-sample evidence and executable odds.
