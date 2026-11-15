# Sunday 15 November 2026 research preview

**Current research release: r8.** See [the r8 coverage incident, collection bounds, cache rules and recovery requirements](R8-COVERAGE.md). The existing hosted app and PR #8 branch are retained; older deployment and UK-only notes below describe earlier checkpoints. The legacy quota halt is preserved pending separately approved review; r8 does not reset counters or automatically resume collection.

Separate entry point: `odds_value_research.py`, on PR #8's development branch. **Not production, not hosted by this change.** No Stage 1A forecasts, probabilities, models, authentication, settings, Supabase data or bankroll functions are modified. No fitting or sealed-period outcome access. Paid services and scheduled collection remain prohibited.

## Current approved US-benchmark scope

The owner now approves FanDuel, DraftKings and BetMGM as **US market research benchmarks**; UK availability is no longer a prerequisite. Use [the current browser deployment and iPhone guide](DEPLOY-US-BENCHMARK.md), which supersedes the earlier UK-only hosting gate below. The preview entrypoint now offers **Market Intelligence** and **Game-Script Intelligence**, with independent forecasts and no experimental pricing activation. Authenticated three-book early-fixture coverage passed. No app has been hosted by this commit.

## Historical UK-only live-test decision

Private quota persistence and real conditional-write conflict detection passed. The free account consumed 14 of 2,500 objects; 16 are conservatively reserved locally. Across all 12 Sunday fixtures, William Hill and Unibet supplied no usable canonical player-prop prices at capture. A FanDuel control supplied all seven markets, but does not meet UK bookmaker suitability. **Do not deploy as a working UK Odds & Value service.** See VALIDATION.md for the authenticated follow-up. Earlier setup-blocker descriptions below are historical and are superseded by that follow-up. The separate game-script preview is prepared; no hosted URL exists.

## Deadline and access decisions

The approved early fixture kicks off at **14:30 UK**. Existing T−60 safeguards mean its eligible decision window closes at **13:30 UK**, earlier than the requested 14:00 preview target. The main 18:00 UK slate closes at **17:00 UK**. Late use is labelled frozen/descriptive only; the cutoff is not relaxed.

Both the separate **free private GitHub quota repository** and **free password-protected Streamlit research app** have been approved. GitHub creation failed with integration HTTP 403: owner creation of the private repository plus a scoped `SGO_GITHUB_QUOTA_TOKEN` secret is required. Hosting requires an authenticated Streamlit connection or owner create-app step; no shared-browser control tools are currently offered. Neither resource has yet been created or deployed by this implementation. Without durable quota state there is no genuine odds collection; without an approved host there is no iPhone URL. Do not point the existing production app at this entry point or branch.

## Odds and quota safety

The account-only API test confirms active Amateur and 2,500 monthly objects, but provides no reset timestamp. The original local interval-accounting backend still requires that timestamp. The new optional private GitHub backend uses a **stricter lifetime budget with no automatic reset** instead:

- Separate private repository, verified before each transaction; never the production repository. The repository and initial `quota.json` must already exist. Missing/corrupt state is a stop, never a fresh budget.
- Before provider calls, `scripts/initialise_sgo_quota.py --repository OWNER/PRIVATE_REPO --cache-path PRIVATE_PATH --initialise-and-verify` must verify a real stale-SHA rejection and new-client readback. An unverified counter blocks collection. No budget is reset.
- GitHub Contents API's existing-file SHA is required for every write. Conflicts retry only the GitHub transaction, before any corresponding SportsGameOdds request. No provider retries.
- At most 2,000 lifetime reserved event objects, configurable downward, plus at least 200 objects of headroom against the actual monthly allowance. Provider-reported usage **plus all lifetime reservations** is checked, deliberately double-counting.
- Reservations precede requests and are never refunded after failures/empty responses. No automatic monthly/date reset or calendar inference. Provider account usage and the Amateur tier are rechecked before each uncached fetch. Six HTTP calls/minute maximum, including usage checks; actual stricter interval limits also apply.
- The private repository stores only counters, timestamps, random reservation IDs and a halt marker. **No credentials, prices, player IDs, account details or forecasts.** No Actions workflow is needed there, no paid resource, no database. Private quote cache remains local, mode 0600 and pruned on access/write after 24 hours; lifetime counters are not pruned/reset.
- The same counter must be used by every collector for this research key. Do not create/reset a second budget or delete state. If quota or auth fails, stop for manual review.

This is bounded Sunday-trial infrastructure, not a promise of indefinite unattended collection: reaching the lifetime cap stops until a separately reviewed quota policy exists. A private GitHub repository is free under GitHub's free plan; no subscription, Actions runner, LFS or hosting upgrade is requested. Hosted access needs an owner-configured fine-grained token limited to **Contents read/write and metadata read on the private counter repository only**. Local Codex can use existing `gh` authentication if authorised; no token value is read or logged by the CLI transport.

Manual small trial: `python scripts/sgo_research_capture.py --starts-after FUTURE_UTC --starts-before FUTURE_UTC --books williamhill,unibet --limit 1`. Use a future bounded fixture window and an approved counter. No auto-pagination, schedule or historical/live/results endpoint. Before any claimed UK value opportunity: verify the actual book variant and settlement rules. A brand name alone does not suffice. Integer/quarter lines have no EV; stale/missing/ambiguous/single-sided records are excluded from selection. Half-line diagnostic probabilities use the unchanged Stage 1A normal CDF at the **actual per-book line**. No genuine quote is fabricated if coverage is absent.

## Game-script evidence and boundaries

The frozen snapshot covers **12 Sunday fixtures**, including the Sunday-night fixture that falls early Monday UK. It uses source files captured on 14 November, completed-game IDs only and Parquet predicates restricting 2026 regular-season weeks below 11. Week-zero NGS season aggregates are excluded. Each history uses at most four recent completed games (or available QB games), and the eight-hour completion proxy remains labelled. Frozen Stage 1B/1B.1/C1/C2 experiments are not retuned.

Available descriptive evidence:

- PBP team plays/dropbacks, neutral clock-gap pace, scramble counts, hit/sack contact labels and target air yards.
- Weekly PFR QB blitz/pressure exposure; weekly NGS average time to throw. These current-season weekly sources were observed before the upcoming decisions. Original historical publication dates are **not verified**, so they are not approved as historical backtest inputs.
- Current approved-slate QB/player identities and unchanged projections; recent covered box targets by individual RB/WR/TE; observed targets at/behind the line of scrimmage.

Important distinctions:

- Hit-or-sack contact is not total pressure. QB scramble frequency is not a measured pressure-conditioned response or mobility grade. QB pressure exposure is not an isolated offensive-line grade.
- Opposing-QB charted blitz counts divided by PBP dropbacks are explicitly a **cross-source proxy**, with coverage/denominator uncertainty. Defensive-player pressures are not summed, avoiding multiple defenders on the same play.
- At/behind-LOS targets and faster release averages do not prove screens, checkdowns or hot reads. Routes, man/zone shells, personnel/inactive status, exact protection grades, timestamped weather and pressure-conditioned decision splits remain missing.
- Covered box-target fractions are not guaranteed full team shares; known positional incompleteness is not repaired by assuming zeros or exhaustive allocations. Slate inclusion is not confirmation of fitness or starter status.
- Fixed descriptive screens (40 labelled QB dropbacks, 3%/8% observed scramble bands) are transparent heuristics, not fitted/validated pressure effects. Text connects each QB's observed behaviour to conditional rushing/short-target watches and identifies specific shallow-usage teammates. No projection offset, probability uplift, scenario probability or quantified edge is produced.
- Trailing/hurry-up and leading/clock-control are **unweighted conditional scenarios**, not predictions of who leads. Recent scores are historical environment evidence, not a forecast total. All nine market forecasts remain unchanged.

The snapshot is frozen with source URLs, retrieval timestamps and hashes; the preview checks its hash and release identity. After a T−60 deadline it remains a labelled frozen description, not refreshed betting advice. Raw public-source files and all provider quotes stay outside the repository. No settlement or historical paper archive is enabled.

## Exact iPhone instructions (after separate hosting approval)

1. In Streamlit Community Cloud, create a **new free research app**, using `coverend401/NFL-player-props-model`, branch `sportsgameodds-free-feasibility`, entry point `odds_value_research.py`, Python **3.14**. Do not edit/reboot/repoint production. Keep the existing dependency lock, including PyArrow **24.0.0**. Do not buy upgrades.
2. Add secrets privately in the new app's settings, not GitHub/chat: `RESEARCH_PREVIEW_PASSWORD` (a new separate long password), `SPORTSGAMEODDS_API_KEY`, `SGO_QUOTA_REPOSITORY` (`owner/private-counter-repo`), `SGO_GITHUB_QUOTA_TOKEN` (only that private repo's fine-grained Contents read/write permission), `SGO_PRIVATE_CACHE_TERMS_ACK = "1"`. Root-level values should be strings. Optional `SGO_OBJECT_CAP = "2000"` may only be lowered. Do not set a false persistent-volume approval for Streamlit's ephemeral disk. No Supabase or production password is required or used.
3. Use the **new research app's HTTPS URL** in Safari on your iPhone. Enter the separate research password. Missing password configuration locks the preview before forecasts/quotes are shown. This repository change does not create a URL; the owner/approved deployer must supply it after creating the app.
4. Open **Odds & Value**, choose week 10 and William Hill/Unibet, then press **Retrieve** manually. Check the actual line, both side prices, last retrieval and provider update timestamps, matching status and projection. Filter player/market/EV. A missing market or excluded comparison is not a fabricated replacement. Until UK variant/rules are verified, values are diagnostic, not eligible selections. Opening/rerunning a page does not fetch odds automatically.
5. Open **Game Script**, choose NE at DET for the early game (or another fixture), and compare individual QB cards, short-target candidates and unchanged baseline projections. Open missing-data/scenario/source panels. Confirm that the page says no forecast/probability adjustment and distinguishes facts, proxies and hypotheses. Take no conditional text as a numerical edge.
6. Verify production separately still shows `stage1a-20261113-py314-arrow24-r2`, with its existing functionality. The research app has no ledger or bankroll controls. If integrity/configuration/coverage fails, stop and report the message; do not weaken checks, reset counters or enter paid credentials.

Local test only: set the separate research password privately and run `streamlit run odds_value_research.py --server.address 127.0.0.1`. A local cloud-machine URL is not reachable from an iPhone; no tunnel or public hosting is implicitly authorised.
