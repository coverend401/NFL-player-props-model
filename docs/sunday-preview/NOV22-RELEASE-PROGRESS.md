# Sunday 22 November release checkpoint

## Phase 1 — essential fixes (local review checkpoint)

Base: PR #8 head `14fcd32`. Recovery: local tag `research-r8-working-20261115` at that commit. Research version prepared: r8.1. No push/deployment at this checkpoint: the connected branch would trigger CI and hosting before phase review.

- Resumed saved readability work; scoped dark-theme CSS covers BaseWeb and React Aria controls, portalled options, selection chips, placeholders, hover/keyboard focus, and collapsed analysis/collection headers. No generated class names or production theme configuration changes.
- Three-sentence player/workload, matchup and prop summaries use existing recorded numbers. Missing carries, targets, coverage and personnel remain explicitly unknown. No unsupported trends, defensive weaknesses, injury claims or positive-value claims for model-only cards. Numerical comparisons are display-only.
- Detailed model analysis retains raw evidence, hypotheses, residual-scale/counterfactual uncertainty, probability/EV limitations, original timestamps and production ranking. Models, calculations, thresholds, collection, quota controls and credentials are unchanged.
- Added a read-only stale-slate warning across research workspaces.

### Current Sunday blocker

The active bundle is `stage1a-20261113-py314-arrow24-r2`, generated 13 November, with Week 10 forecasts for 15–17 November. It has **no Sunday 22 November forecasts**. Local weekly outcomes/features reach Week 9. The saved schedule metadata includes Week 11 / 22 November fixtures, but that is not a current forecast slate or fresh official schedule verification. No outcomes from the sealed period were read.

The old forecast data and manifest were not relabelled, replaced or weakened. A reviewed current-slate refresh is required within the owner's no-retraining, production-isolation and integrity requirements before claiming Sunday readiness. No refresh was attempted in Phase 1.

### Validation

**42 focused tests passed** on Python 3.14. Tests cover copy, missingness, immutable evidence, genuine-line comparisons, stale/current date notices, real authenticated entrypoint rendering and existing r8 collector regressions with mocks. Full regression is deferred to Phase 3. Historical eligible-time UI tests use the actual frozen Stage 1A bundle to inspect cards; they do not claim that old games are current.

Chromium checks at 375/390/430px cover expanded workspace menus, selected/unselected options, keyboard/hover states, multiselect options and selected chips. Lowest measured option-text contrast: 8.15:1. No provider retrieval was clicked.

## Phase 2 — not started

No SportsGameOdds or quota-store requests, no halt clear, and no counter/reservation mutation. The historical 81-object reservation total has not been freshly queried or presented as the account's current usage/remaining balance. Await review before recovery investigation or any single diagnostic probe.

## Phase 3 — not started

No full regression, current-slate release selection, new hosted deployment, hosted verification or main merge. The production app/release, Supabase, authentication, bankroll, frozen benchmarks and sealed final period remain untouched.

## Cost and next action

No new dependency, service, subscription, account, paid resource or scheduled collection. £0 additional operating cost introduced. Codex usage balance is unknown and was not verified. Review Phase 1 and resolve the stale-slate blocker before advancing the controlled release.

## Reviewed follow-up — Week 11 forecast refresh

20 November: current source availability passed, and the nine frozen models executed without retraining. Generation stopped at the live current-team gate: 2 draft rows conflicted with the depth snapshot and 42 lacked confirmed team membership. No valid slate, Top Picks, research pointer or dashboard integration was published. No full tests, deployment, bookmaker calls or quota changes. See [the bounded refresh failure report](NOV22-FORECAST-REFRESH-BLOCKER.md). Await review before any identity reconciliation or rerun.

## Targeted player reconciliation — stopped at publication-contract boundary

20 November: inspected the 44 flags (15 players), reusing saved inputs and one current roster download. Remigio's two stale KC rows resolve to HOU; HOU's Week 11 fixture had already kicked off. Of the other 42 rows, 30 have current-week practice-squad evidence and 12 remain unresolved. Review decisions recommend 32 exclusions; no flagged rows were restored. The 692 unaffected draft rows span 12 fixtures but cannot be published as an ad hoc subset under exact replay/same-build provenance checks. Eight focused tests passed. No new policy, loader, Top Picks, deployment or quota operation. See [reconciliation evidence and stop condition](NOV22-ELIGIBILITY-RECONCILIATION.md).

## Certification attempt — exact negative tests, no contract change

20 November, following `67de79d`: two focused tests exercised the unmodified validator with byte-identical frozen models. A new release identity fails `Mixed or legacy model`; retaining the old ID in a fresh build fails `Future/stale build provenance` because training was on 13 November. Both negative tests passed. Stopped at this gate before source corrections or any new generation. No approved frozen-model lineage/current-roster replay input exists; no contract extension, partial-policy workaround, deployment, full suite, player investigation, source refresh or bookmaker call was made. See [the exact gate and required contract decision](NOV22-CERTIFICATION-GATE.md).

## Approved frozen-model extension — certified local Week 11 candidate

Following `229328f`, implemented only the explicitly authorised research inference contract; original training validation and production source hashes remain unchanged. Candidate `research-week11-frozen-20261120-r2` passed full forecast and Top Picks exact replay with all nine immutable parent models: 618 rows / 12 fixtures (568 complete across 11; TEN–DAL 50 roof scenarios), 22 model-only Top Picks. Explicit source-derived eligibility covers all 572 candidate states; unresolved rows cannot enter prediction and later elevations can supersede practice-squad status. Fifteen focused tests passed, including actual research-entrypoint loading with an opt-in local pointer and no stale Week 10 warning. No default-pointer change, deployment, full suite, odds calls or quota operations. See [certification rules, evidence and review boundary](FROZEN-INFERENCE-WEEK11.md).
