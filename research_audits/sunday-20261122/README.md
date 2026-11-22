# Sunday player–team–fixture audit: FAIL — selections withheld

Audited checkpoint: `8ae23460a0332377d1a65b919e4d7d2143038877`.
Completed 22 November 2026, before the Sunday slate. This is an integrity
review, not a modelling experiment or a certification of betting performance.

## Population and findings

- **522/522 forecasts**, 182 distinct players, nine markets, ten represented
  fixtures audited. The separately labelled TEN–DAL roof scenarios remain
  excluded; Sunday has eleven scheduled fixtures including that game.
- **Zero detected internal association errors.** Every forecast's player ID,
  active-roster team, game, opponent, and kickoff agrees with the refreshed
  nflverse roster and schedule feeds. All twelve rows of the bundle's fixture
  index agree with that refreshed schedule, including the Monday fixture.
- Zero eligibility-record/team mismatches or eligibility timestamps later than
  prediction. Zero feature-state player/team/opponent mismatches.
- Every displayed player name matches the refreshed roster's name or documented
  first/football-name variant for the same GSIS identifier; no name/ID conflicts.
- Recomputed opponent pass attempts/carries allowed from the opponent's last
  eight available games and the corresponding opposing offensive team totals.
  All 522 rows agree with their feature state and displayed explanation inputs.
  Only permitted history through 2026 Week 10 was used; no Week 11 outcomes
  were inspected. This verifies numerical routing, not football causality.
- The original twelve Top Picks and twenty Top 2 entries are subsets of the
  audited population. Their presence in these files is **not selection approval**.
- **No verified mapping errors corrected and no forecasts regenerated.**
  Reassigning teams using an older season's roster would introduce unsupported
  changes. Certified and experimental forecast files remain byte-for-byte intact.

## The two questioned players

| Player | GSIS ID | Original roster evidence | Refreshed roster evidence | Independent transaction confirmation |
|---|---|---|---|---|
| Kenneth Walker III | 00-0038134 | KC, ACT, 2026 week 11 | KC, ACT, 2026 week 11 | Not verified |
| Jalen Nailor | 00-0037291 | LV, ACT, 2026 week 11 | LV, ACT, 2026 week 11 | Not verified |

These are **not display-only substitutions or detected fixture join errors**:
the assignments originate in the roster feed. Neither refreshed feed agreement
nor an old team remembered from prior seasons proves a current transaction.
No independent official evidence was accessible to classify these as valid
current assignments versus a shared upstream-data error.

## Why the overall result is FAIL

The available downloads are aggregated nflverse feeds. Official NFL schedule,
team roster/transaction pages and ESPN requests were rejected by the configured
network proxy. Exact tested hosts were `www.nfl.com`, `www.chiefs.com`,
`www.raiders.com` and `site.api.espn.com`. The research app host
`nfl-props-research.streamlit.app` is also blocked in this execution environment.
No alternative network route or authentication bypass was used.

Consequently authoritative schedule and current roster/transaction verification
remain incomplete for the entire population. Injury and game-day inactive
status remain **unverified for all 182 players**; an `ACT` roster entry is not
confirmation of availability. We do not infer inactivity from missing news or
claim that game-day inactive lists already exist before publication.

**Final Sunday Top Picks: withheld. Final Top 2 for every fixture: withheld.**
There are zero selections admitted for use. This does not assert that every
forecast is wrong; it means the requested independent evidence gate is unmet.

## Safeguard and tests

The research entrypoint now checks an independent audit before rendering any
selection, player/game intelligence, parlay or pricing workspace. A missing,
failed, expired, wrong-release or hash-mismatched audit fails closed. Admission
also requires explicit schedule, transaction, availability and opponent checks,
zero internal errors, and bindings for every required forecast and identity
file. There is no fallback to older recommendation cards. Historical Model
Performance and Weekly Learning remain accessible with the warning displayed.

`tests/test_selection_integrity.py` rejects wrong teams/opponents, missing or
ambiguous rosters, inactive roster statuses, ambiguous fixtures and wrong week
IDs. It also exercises the **real authenticated Streamlit entrypoint** without
mocking this gate and checks that every selection/pricing workspace renders no
cards or price inputs and makes no provider requests. Archived presentation
tests explicitly mock admission to retain component-rendering coverage; those
tests do not constitute live integrity approval.

Local validation: 17 enhanced-selection/integrity checks passed, followed by
34 focused integration, release-contract, presentation and startup checks.
The final integrity plus provider-adapter run passed all 49 tests on Python 3.14.
On Python 3.12, seven integrity tests passed and the real frozen Python 3.14
entrypoint test was intentionally skipped; no runtime guard was weakened.
Chromium at 390px authenticated against the
real local entrypoint and displayed the FAIL gate, zero recommendation cards,
zero price inputs, zero page exceptions and no horizontal overflow. This is
**local validation**, not verification of the password-protected hosted service.

## Evidence and replay

- `forecasts.csv`: one audit result per forecast, including unresolved evidence.
- `refreshed_roster.csv`: relevant player IDs/team/status only, no credentials.
- `refreshed_schedule.csv`: fixture identity/time fields only, no game outcomes.
- `integrity.json`: counts, source URLs, raw-source hashes, and file bindings.

The raw download hashes identify the exact files read; the report creation time
is not claimed to be their publication time. To repeat with separately retrieved
feed files (no network activity is performed by this audit script):

```sh
python -m scripts.audit_sunday_integrity --roster /path/roster.parquet --schedule /path/games.csv
```

The script deliberately cannot grant official verification based on these feeds
alone. Unblocking requires independent dated official schedule/roster/transaction
and availability evidence, review against the forecast cutoff, correction and
replay if an actual error is established, and a fresh complete integrity review.
Allowing the official hosts above is the immediate environment action needed.

Production, main, the original nine model files, certified releases, credentials,
bookmaker quota and outcome seal are unchanged. No services or API credits were
purchased or consumed.
