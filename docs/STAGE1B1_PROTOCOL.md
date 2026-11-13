# Stage 1B.1 research protocol

Status: research only. No production probabilities, data, app, settings or database
changes. The accepted Stage 1B package, dashboard and experiment are frozen.
Stage 1B.1 is a separate package and archive namespace. Python 3.14 / Arrow 24
and the exact existing dependency lock remain unchanged.

## Frozen experiment and information boundaries

`stage1b1/protocol.json` is committed before the full experiment. All nine markets
and all five outer years (2022–26) use the SAME input snapshot and scored player-game
IDs as the accepted Stage 1B benchmark. Zero outcomes remain outcomes; absent
observations do not become zeros. The final period (2026 week 11 onward, conservative
boundary 2026-11-19T00:00Z, plus all future seasons) is excluded by the original
Parquet predicates before outcomes are materialised. There is no unseal switch.

For outer year Y:

1. Point candidates train before Y−2, select on Y−2, refit before Y−1.
2. Distribution fitting: Y−1 weeks 1–6; calibration: weeks 7–10.
3. Probability/interval method selection: weeks 11–18, at least eight observed weeks
   for probability and point superiority gates.
4. Outer evaluation: Y only, after all fitted/selection label availability times.

All historical inputs must precede a one-hour-before-kickoff decision. Label
availability must strictly precede the next phase. Model timestamps represent
information cutoffs, not falsely claimed historical training execution. All fitting
is retrospective now. Annual rolling origin remains a limitation compared with a
prospective weekly-retraining experiment. Historical publication/roster snapshots
are still unavailable, so historical evaluation is not a fully authenticated replay.

Earlier Stage 1B distribution/calibration objects must NOT select new methods on
weeks 11–18 (their own calibration used weeks 10–14). They are retained only as
outer-year comparators, or used unchanged in the six markets whose probabilities
are not being redeveloped. New probability candidates in the three passing markets
use only the new, disjoint windows. Eight weeks reduce the prior four-week bootstrap
degeneracy but still provide weak selection evidence for QBs. Moving four-week
bootstrap bands are exploratory, conditional on fitted models and selection decisions,
not multiplicity-adjusted or full pipeline confidence intervals.

2022–25 have already informed this follow-up design, and 2026 weeks 1–10 were
previously reported. All are development/monitoring results, not final acceptance
proof. There will be one frozen reported full experiment, with unfavourable results
retained. No tuning based on final-period labels is permitted.

## Point accuracy

Passing yards compare career mean (incumbent), last three, three fixed lag blends,
and StandardScaler + Ridge(alpha=100). Prior validation must show at least 2% MAE
gain over career mean and a paired week-block upper difference below zero before
switching. Otherwise retain the naive mean. This is a conservative fallback,
not a claim to beat naive forecasts. The other eight point estimators are unchanged.

## Probabilities

Only passing yards, attempts and completions are redeveloped. Candidates are an
integer-support normal reference, out-of-sample normal, scaled empirical residuals,
dense conditional quantiles (.05/.25/.5/.75/.95, rearranged), and NB2 counts.

Every new candidate contains a fixed 15% Student-t(df=5) residual tail anchor,
with scale/bias learned in the distribution window. This is an explicit modelling
assumption to avoid bounded-quantile/empirical tail certainty; it is not a promise
of correct extreme-tail probabilities. Count support is censored at zero; signed
yardage is preserved. NB2 dispersion is moment-estimated on held-out labels and
shrunk toward .25 with prior strength 100.

Completion NB2 uses a forecast of attempts and a regularised binomial completion
rate learned from historical (attempts, completions). NB2 thinning marginalises the
unknown number of trials, rather than supplying actual future attempts. The NB2
latent-heterogeneity/thinning assumptions may miss injury/role mixtures. We do not
claim every independently predicted completion marginal is jointly constrained by
the separate passing-attempt probability candidate or point projection.

Identity and penalised positive-slope sigmoid calibration are fit on weeks 7–10.
The sigmoid objective includes the final tail mixture. No unrestricted isotonic
alternative is reselected in these small QB samples. The normal reference is an
eligible default; an alternative needs at least .005 validation log-loss gain,
no Brier regression, and a paired bootstrap upper log-loss difference below zero.
These are historical validation gates, not checks against observed outer-year scores.
All CDFs retain coherent Over/Under/push mass. Half-line probes remain hypothetical
career-mean thresholds, never bookmaker prices or realised betting evidence.

The Stage 1B comparator used the same safe features but different probability
selection. Passing-yard probability comparisons also reflect the point-policy change;
they do not isolate calibration. Six other markets retain their old probabilities
exactly, including known limitations, while interval experiments run separately.

## Predictive intervals

Train .05/.95 conditional quantiles before Y−1. Fit a nonnegative conformal expansion
on weeks 7–10 using rank ceil((n+1)*.9), with outward integer rounding. Select CQR
versus a held-out normal-residual 90% interval on weeks 11–18 by interval score,
requiring at least 1% score gain and selection coverage >=85% for CQR. Otherwise
retain the held-out normal interval. Report width AND coverage AND proper interval
score; narrow but under-covering intervals are not automatically better.

These independently estimated predictive sets need not equal the 5th/95th quantiles
of the selected pricing CDF. They are not individual-probability confidence bounds,
edge guarantees or automatic staking inputs. Conformal coverage needs exchangeability;
season/role changes and selection break that premise. No finite-sample coverage
guarantee is claimed for these temporal selected intervals.

## Reproducibility

The runner requires committed source/protocol, validates the original benchmark,
records exact source/input/runtime/payload hashes, fits 45 versioned bundles,
compares the identical population and outcomes, and refuses reuse of experiment IDs.
The new validator checks models, row counts, timestamps, the sealed period, all
payloads and exact source/runtime consistency. Genuine quotes remain zero and
betting profit null until independently verified odds are available.

Run with the validated 3.14 interpreter, BLAS/OpenMP threads set to 1:

```sh
python -m stage1b1.runner --id improvements-20261113-v1
python -m stage1b1.artifacts experiments/stage1b1/improvements-20261113-v1
python -m stage1b.cli experiments/stage1b/baseline-20261113-v5
python -m unittest discover -s tests -v
```

## Research references checked

- Romano, Patterson & Candès (2019), *Conformalized Quantile Regression*,
  [paper](https://arxiv.org/abs/1905.03222),
  [official authors' implementation](https://github.com/yromano/cqr).
  The official README was retrieved; it identifies distribution-free predictive
  intervals and links the paper. Exchangeability, not a temporal guarantee, is the
  relevant condition; nonnegative expansion is a conservative variant.
- [scikit-learn quantile-regression example](https://github.com/scikit-learn/scikit-learn/blob/main/examples/ensemble/plot_gradient_boosting_quantile.py),
  retrieved from official source: pinball-loss training, interval coverage and
  quantile estimation. No new dependencies added.
- [SciPy negative-binomial parameterisation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.nbinom.html).
  NB2 as Poisson–Gamma mixing plus independent binomial thinning yields mean
  E[A]*p with unchanged dispersion; code tests label validity and predictive inputs.
- Proper scoring/temporal validation references and original provider investigation
  remain in `STAGE1B_AUDIT_RESEARCH.md`. These methods are hypotheses to evaluate,
  not evidence of real betting value.
