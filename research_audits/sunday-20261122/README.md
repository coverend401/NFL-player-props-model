# Sunday integrity reconciliation — PASS WITH AVAILABILITY WARNINGS

Supersedes the blanket FAIL in `ba2ab4f`. That original audit remains recoverable
at that commit. No forecast, ranking, model, model timestamp, production setting,
bookmaker price or quota record has changed.

## Evidence accepted

The owner independently verified and supplied these official findings in this
task on 22 November 2026. The assistant did not fetch the blocked official pages.
The exact attribution, source URLs and dates are recorded in
`official_evidence.json` and bound to the updated integrity report.

- Kenneth Walker III is a KC running back. Official Chiefs biography and 2026
  transactions confirm his March signing; both agree with the audited KC rows.
- Jalen Nailor is a LV receiver. The official Week 11 depth chart dated
  17 November agrees with the audited LV rows.
- The owner supplied official NFL schedule verification: Sunday 22 November is
  Week 11. This resolves the schedule question alongside the existing zero
  disagreements between the stored and refreshed schedule feed.

All **522 forecasts / 182 players / ten represented Sunday fixtures** passed
player-ID/name, roster team, fixture, opponent, kickoff, eligibility timing and
opponent-feature routing checks. Zero mapping errors were found or corrected.
Other players retain reconciled active-roster-feed support; this is not a claim
of independent official transaction research on all 182 players.

## Availability is a separate decision

All players have **injury and game-day inactive status unverified**. No blanket
injury clearance is granted. `availability.json` records the default warning and
only documented material player-specific issues. There are currently **zero
such documented issues**, meaning zero individual availability suppressions;
that does not prove no injuries exist. Unknown news alone is not a material
issue and no longer blocks the entire slate. Cards carry an availability warning.
Documented material issues remove the player's rows before ranking and manual
comparison, with a visible reason. Malformed evidence still fails closed.

**Available:** 522 eligible research forecast rows, twelve Enhanced Top Picks,
and twenty Top 2 entries across ten games, subject to each fixture's T−60 cutoff.
**Withheld:** TEN–DAL's fifty unresolved roof-scenario rows; no Top Picks or
bookmaker pricing from those scenarios. The Monday fixture is outside the Sunday
selection bundle. Started/past-cutoff fixtures remain excluded automatically.
These remain model-only research selections, with no verified bookmaker value.
Manual actual-line/price entry is restored with the existing probability guards.

## Enhanced Top Picks (unchanged ranking)

| Rank | Player | Fixture | Market | Projection |
|---|---|---|---|---:|
| 1 | Justin Jefferson | MIN vs SF | receptions | 5.2 |
| 2 | George Kittle | SF vs MIN | receiving yards | 61.1 |
| 3 | Tetairoa McMillan | CAR vs BAL | receptions | 4.2 |
| 4 | Trey McBride | ARI vs KC | receptions | 6.1 |
| 5 | Rome Odunze | CHI vs NO | receiving yards | 49.3 |
| 6 | Amon-Ra St. Brown | DET vs TB | receptions | 6.0 |
| 7 | Xavier Worthy | KC vs ARI | receptions | 3.5 |
| 8 | Sam LaPorta | DET vs TB | receptions | 3.3 |
| 9 | Jahmyr Gibbs | DET vs TB | rushing yards | 78.6 |
| 10 | Colston Loveland | CHI vs NO | receptions | 3.9 |
| 11 | Kenneth Walker III | KC vs ARI | carries | 17.6 |
| 12 | Dallas Goedert | PHI vs PIT | receptions | 3.9 |

## Top 2 by Game (unchanged ranking)

| Game | First candidate | Second candidate |
|---|---|---|
| 2026_11_MIN_SF | Justin Jefferson: 5.2 receptions | George Kittle: 61.1 receiving yards |
| 2026_11_BAL_CAR | Tetairoa McMillan: 4.2 receptions | Zay Flowers: 4.5 receptions |
| 2026_11_ARI_KC | Trey McBride: 6.1 receptions | Xavier Worthy: 3.5 receptions |
| 2026_11_NO_CHI | Rome Odunze: 49.3 receiving yards | Colston Loveland: 3.9 receptions |
| 2026_11_TB_DET | Amon-Ra St. Brown: 6.0 receptions | Sam LaPorta: 3.3 receptions |
| 2026_11_PIT_PHI | Dallas Goedert: 3.9 receptions | Dontayvion Wicks: 3.0 receptions |
| 2026_11_MIA_BUF | Ollie Gordon II: 13.6 carries | James Cook: 80.4 rushing yards |
| 2026_11_JAX_NYG | Isaiah Likely: 4.1 receptions | Malik Nabers: 70.6 receiving yards |
| 2026_11_NYJ_LAC | Tre Harris: 2.7 receptions | Garrett Wilson: 4.9 receptions |
| 2026_11_LV_DEN | Brock Bowers: 57.4 receiving yards | Jalen Nailor: 2.0 receptions |

## Admission safeguards and verification

The audit still binds every required forecast, selection, roster, eligibility,
feature-state and evidence file. Wrong release, changed files, expired audit,
internal mapping errors or schedule disagreement still block selection views.
The review expires at 00:20 UTC on 23 November, the final Sunday fixture's T−60
boundary; individual earlier cutoffs apply before then.

Focused tests exercise the real authenticated Streamlit entrypoint with the live
admission gate, restored cards and manual calculator, plus missing-audit rejection,
unknown-versus-material availability and invalid player/fixture associations.
Archived component tests remain separate from actual admission tests. Hosted
verification must not be inferred from local tests or a successful branch push.

No SportsGameOdds requests, paid services, model refits, outcome settlement,
production changes or main-branch merge are part of this correction.

Local validation for this correction: twenty focused integrity/enhanced-selection
tests passed on Python 3.14, plus two official-claim/missing-audit checks. On
Python 3.12, eight tests passed with two intentional frozen-3.14 entrypoint skips.
The real authenticated 390px browser render showed twelve Top Picks, twenty
Top 2 cards, correct Walker KC and Nailor LV labels, the availability warning,
no page exception and no horizontal overflow. No provider collection was initiated.
Manual price entry was exercised through the real Streamlit entrypoint.
