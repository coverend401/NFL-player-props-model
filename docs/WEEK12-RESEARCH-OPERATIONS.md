> Operational update, 27 November: the owner has authorised standing, validated research-only forecast publication. The earlier per-release activation procedure below is retained as historical evidence; use [ROUTINE-OPERATIONS.md](ROUTINE-OPERATIONS.md) for the current cutover, safeguards and single owner checklist.

# Week 12 research operation and owner handoff

Status: serving candidates prepared; **not selected or activated**. Production/main, original nine models, certified forecast artifacts, authentication, Supabase and bookmaker quota are unchanged. No genuine quote has been supplied or frozen in this task. No profitability, sportsbook win-rate or ticket-success claim is made.

## Candidates and dates

The original `weekly-week12-schemafix-20261124` remains immutable: 846 rows (651 complete, 195 roof scenarios), 16 fixtures, 24 model-only Top Picks and 24 model-only Top 2 rows. Its whole-slate activation deadline passed at midnight UK on 26 November. The selection command rejects it before touching private storage.

Friday's existing `weekly_learning.cli prepare` produced `weekly-week12-remaining-20261127`, with original contract `prospective_frozen_model_inference_v2`, exact replay and all nine frozen model hashes verified:

- **604 rows: 457 complete + 147 roof scenarios.**
- **12 remaining fixtures: nine complete and three roof-only.**
- **18 certified model-only Top Picks and 18 Top 2 rows.** These are forecast-only outputs, not quoted betting selections.
- Complete: DEN–PIT, NO–CIN, NYJ–MIA, ATL–MIN, TEN–JAX, NE–LAC, SEA–SF, LV–CLE, CAR–TB.
- Roof-only, excluded from pricing and selections: BAL–HOU, NYG–IND, WAS–ARI.
- GB–LA, CHI–DET and KC–BUF remain available from the original archive as historical pre-kickoff forecasts. PHI–DAL is historical roof-only. Top 2 displays these separately, so all twelve originally complete fixture histories remain visible without making already-started games actionable.
- First remaining kickoff is **Friday 27 November, 20:00 UK**, so activation must pass the unchanged whole-candidate **19:00 UK T−60 deadline**. If missed, use the existing prepare pipeline with a unique ID to generate another future-only candidate. Never override the cutoff.

The Friday refresh reads completed player statistics only through Week 11. Current-week schedule reads project metadata columns only. Initial downloads are quarantined. The existing admission process then persists only Week 11-or-earlier outcomes and future fixture/personnel metadata, recording both download and scoped-file hashes. Protected Week 12 outcomes are not materialised or published. No Week 12 result was used in fitting, evaluation or forecasting. No models were retrained.

## Serving admission

Profiles:

- `research_runtime_profiles/week12-certifi-20261120-v1`: original full Week 12 archive.
- `research_runtime_profiles/week12-remaining-certifi-20261120-v1`: fresh remaining-fixture candidate.

The original operational validator is unchanged. `scripts/generate_weekly_serving.py` makes a deterministic runtime-only derivative. Every non-runtime eligibility, data timing, finality, source hash, model hash, fixture identity and replay guard remains present. The full original training dependency set is verified separately from the full Cloud serving dependency set; only the already approved certifi 2026.10.23→2026.11.20 substitution is permitted. Python remains 3.14 and PyArrow remains 24.0.0.

Each profile compares exact inference replay, a deterministic selection-frame signature and actual-line pricing queries between the real original and Cloud environments. Certification queries are synthetic numerical checks, **not bookmaker prices**. The previous Week 11 serving certificate is legitimately renewed for the UI/recording code changes; its 522/12/20 forecasts/rankings and numerical signature are unchanged. Git commit `0696250` preserves the complete prior working deployment as rollback.

The selection layer reuses existing frozen research point models, probability laws, market gates and ranking rules. No threshold-sprint method or failed game-script challenger is activated. Updated player states come only from admitted pregame data. New selection build times are recorded separately from baseline prediction times; none is backdated. Roof scenarios are excluded.

## Required private repository setup

The managed Codex GitHub identity returned `Resource not accessible by integration (createRepository)`. No repository was created, and the quota repository was not reused.

1. Visit https://github.com/new. Owner **coverend401**; repository **nfl-props-research-selections**; visibility **Private**. Add a README if desired. Stay on the free plan.
2. GitHub profile → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
3. Resource owner **coverend401**; choose **Only select repositories → nfl-props-research-selections**. Set **Repository permissions → Contents: Read and write**. Metadata remains Read. Do not grant access to the quota or model repository. Choose an expiry and retain the token securely.
4. Open https://nfl-props-research.streamlit.app → **Manage app → Settings → Secrets**. Preserve all existing secrets and add:

   ```toml
   NFL_SELECTION_GITHUB_REPOSITORY = "coverend401/nfl-props-research-selections"
   NFL_SELECTION_GITHUB_TOKEN = "YOUR_NEW_TOKEN"
   ```

5. Add the same two variables to the current Codex environment and Save/apply for a direct PAT-only storage test. Never paste the token into chat or commit it.
6. For later operational selection settlement through GitHub Actions, add the same two values in the **model repository → Settings → Secrets and variables → Actions**. This configures research access only; it does not activate a schedule or change production.

Direct bounded health test once configured:

```sh
python -m selection_learning.probe
```

It validates exact private-repository identity, uses the explicit token with no managed-credential substitution, performs one SHA-conditioned write to a separate healthcheck file, and verifies two read-backs. It creates **zero selection records** and never accesses quota files. Conflicts, errors, secret echoes, unexpected size or failed read-back stop without retry. Actual persistence remains unverified until the owner configures the repository/token and the live probe passes.

## Explicit activation — separate approval required

No active weekly serving or operational selection pointer has been written. After green final CI, successful live private storage verification and explicit owner approval, run in the exact Cloud environment:

```sh
python -m scripts.select_weekly_serving \
  --profile week12-remaining-certifi-20261120-v1 \
  --approved-release weekly-week12-remaining-20261127 \
  --expected-certificate CERTIFICATE_SHA256_FROM_REVIEW \
  --approval-reference OWNER_APPROVAL_REFERENCE
```

The generic workflow select action is blocked to prevent an operational-only pointer being published without coordinated serving admission. The helper re-admits the candidate, checks the certificate, tests private persistence, rechecks the deadline, records approval and previous pointers, and prepares coordinated operational/serving pointers. Only a normal research-branch commit/push should publish those pointers together. Never merge into main, force a push, or commit a partial pointer update. Serving rejects inconsistent pointers. An activated release remains subject to each fixture's T−60 cutoff.

Rollback: revert the later activation commit to restore both pointers together. Keep frozen forecasts, private selection/settlement history and source receipts. The existing Week 11 serving route is retained when no weekly pointer is selected. To undo this integration entirely, revert its research commit back to the preserved `0696250` behavior; no production setting or database rollback is involved.

## Owner's authenticated iPhone check

The existing research app URL and password remain unchanged. It must deploy repository `coverend401/NFL-player-props-model`, branch **sportsgameodds-free-feasibility**, entrypoint **odds_value_research.py**, Python **3.14**. Do not change the production app.

1. Open the research app in Safari and log in normally. Expand **Authenticated deployment diagnostics** and verify the checkout commit equals the reviewed PR head. Do not share secrets.
2. Before activation, expand **Certified Week 12 candidate — review before activation**; choose **Remaining Week 12 fixtures — refreshed 27 November**; turn on **Preview Week 12 (not selected; freezing disabled)**.
3. Confirm release ID `weekly-week12-remaining-20261127`, 457 complete inputs, nine complete fixtures and three roof-only fixtures. Preview must clearly state that it is not selected and freezing is disabled.
4. Open **Top 2 by Game**. Check all remaining fixtures plus **Earlier Week 12 fixtures — historical pre-kickoff research only**. Historical games cannot take new quoted selections. All four original roof-only fixtures remain visibly separate from actionable propositions.
5. Open **Player Intelligence** for original/enhanced projections and the manual actual-line calculator. Missing prices must stay missing. Research intervals are outcome ranges, not probability confidence intervals.
6. After explicit activation and successful private setup, use **Top Picks → Load private frozen selections**. Enter a genuine bookmaker quote or import CSV. Check line-specific probability, break-even price, estimated EV, expiry, sample evidence and uncertainty. Unsupported probability bands/markets and integer-line push cases do not qualify.
7. Click **Freeze quoted research decisions**, confirm verified private persistence, then reload the workspace. Reopening in another authenticated session and loading the journal must recover the same immutable records. This is the required real persistence evidence, not a unit-test substitute.
8. Choose only desired eligible legs in **Accumulator Candidate Pool**. No ticket is forced; dependence is explained. No joint probability, fair odds or parlay EV is claimed without a validated joint model.
9. Open **Weekly Learning** for the last completed Week 11 audit. Its archived readiness snapshot is separate from the release ID displayed above. No Week 12 settlement may occur until the authorised cutoff/finality receipt exists.

Bulk CSV requires these exact columns:

```csv
game_id,player_id,market,side,line,decimal_odds,bookmaker,quoted_at,settlement_rule,source
```

Use canonical market/player/game IDs from the versioned identity export in `docs/week12-operations/forecast-identities.csv`. Keep at most 100 genuine quoted rows per import and at most 64 KiB. Supply original quote timestamps with timezone; prices must be no more than 30 minutes old and observed after the selection build. The only supported settlement rule is `offensive_participation_full_refund_push`; verify the bookmaker actually uses it. Do not fill missing prices with examples. Invalid bulk imports reject atomically.

Qualified quoted selections use existing probability-band and workload evidence. High hit probability and estimated positive EV are separate concepts; WATCH remains research, not a validated betting recommendation. Quote reloads retain a stable identity, so the same observed quote is not counted twice. Original records are never rewritten. New decisions are ranked against the current full pool rather than being called Top 2 merely because they arrived in a separate batch. Reports retain decision-event scope and may include genuine replacements; they are not a single forced ticket per game.

## Settlement and limits

Week 11 enhanced audit: **440 of 522 scored**, with 82 explicitly unscored; original complete-baseline audit: **484 of 568 scored**. Missing results were not turned into zeros. Reports are immutable under `weekly_learning_state/cycles/week11-operational-20261124-queryfix` and `weekly_learning_state/enhanced_settlements/week11-20261124`.

Week 12 captures are frozen for both candidate versions. `selection_learning.cli --latest` only reconciles a successfully admitted operational cycle; it cannot retrieve results or bypass finality/time gates. The future Week 12 gate is after the whole captured slate completes and its authorised Tuesday cutoff, subject to finality. The private journal records original lines/prices/probabilities, original decisions, fixed paper stakes, outcomes, Brier/log loss and hypothetical paper returns separately from actual ROI. Actual ROI remains unavailable. No bankroll or Supabase access exists in this path.

The research workflow verifies frozen benchmark hashes instead of fitting new experimental methods while development is paused. Existing capture, results reconciliation and private settlement paths remain available. Recurring jobs/default-branch registration remain unactivated and require separate approval.

Private journal cap is 900,000 bytes. It fails closed rather than deleting history or purchasing capacity. Archive/repartitioning would require review if the cap is approached.

## Cost and verification boundaries

No paid services, trials, upgrades, accounts, providers, bookmaker calls or new hosting. Existing free GitHub/Streamlit infrastructure only. GitHub private content calls respect service failures/rate limits and have no retries; no additional paid artifact storage or collectors. SportsGameOdds quota and credentials were untouched. Model accuracy/profitability was not re-claimed from hypothetical threshold tests.

Authenticated local entrypoint tests and mobile checks are distinct from hosted evidence. The environment's enforced allowlist lacks **nfl-props-research.streamlit.app** (it contains the production domain and share.streamlit.io). Direct hosted requests fail with ProxyError. The owner must Save/apply that exact hostname and verify through their authenticated session. No hosted success or private live persistence is claimed before those checks actually pass.

## Local validation evidence

`docs/week12-operations/validation.json` records both full local regression runs (548 tests each), the final focused recording/runtime tests, and the phone-browser results. The focused checks cover the capture corrections added after the full suites began. The actual local authenticated Streamlit entrypoint was exercised through all workspaces. Mobile checks at 375/390/430px measured at least 8.8:1 navigation contrast, no horizontal overflow, 12 model-only Top Picks and 24 Top 2 cards (18 current, six historical). Private live persistence and authenticated hosted verification remain blocked; this evidence must not be described as a completed production deployment.
