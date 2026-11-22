# Frozen Sunday slate visibility correction

At 17:00 UTC on 22 November the shared presentation path applied the live
T−60 filter to the entire enhanced data frame. The game renderer independently
skipped the same fixtures. Thus six 18:00 fixtures disappeared while four later
fixtures remained. No forecasts were lost and no additional roster exclusion
caused the loss. There was no enhanced historical-view toggle.

Reconciliation at 17:09 UTC (all figures from the existing immutable bundle):

| Game | Frozen rows | Frozen global Top Picks | Top 2 | Live pricing rows |
| --- | ---: | ---: | ---: | ---: |
| ARI–KC | 45 | 3 | 2 | 0 |
| BAL–CAR | 60 | 1 | 2 | 0 |
| JAX–NYG | 48 | 0 | 2 | 0 |
| MIA–BUF | 57 | 0 | 2 | 0 |
| NO–CHI | 58 | 2 | 2 | 0 |
| TB–DET | 43 | 3 | 2 | 0 |
| LV–DEN | 47 | 0 | 2 | 47 |
| MIN–SF | 54 | 2 | 2 | 54 |
| NYJ–LAC | 58 | 0 | 2 | 58 |
| PIT–PHI | 52 | 1 | 2 | 52 |
| Total | 522 | 12 | 20 | 211 |

For the first six games, all rows were excluded from the previous screen solely
by T−60. The fix keeps their frozen research selections visible with explicit
cutoff-closed labels, changing to historical-only labels at kickoff. The other
four games remain subject to their own T−60 deadlines. Manual pricing always
uses the unchanged eligible_rows cutoff and never the historical display frame.

TEN–DAL has no admitted enhanced rows: its 50 certified roof scenarios remain
excluded and its Sunday game heading explains the exclusion. CIN–WAS is a Monday
fixture outside the Sunday enhanced bundle, unchanged. Material availability
exclusions and the full player/fixture audit remain enforced; unknown injury
status is never presented as clearance.

Only UI display and tests changed. The serving compatibility certificate was
renewed through scripts.certify_cloud_runtime after exact numerical replay,
because it binds UI source hashes. Original release manifests, all forecast
artifacts, ranking rules, model hashes, probabilities and training timestamps
remain unchanged. No provider requests or quota changes are required.
