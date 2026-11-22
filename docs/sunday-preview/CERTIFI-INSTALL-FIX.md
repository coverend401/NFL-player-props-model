# Preserve the approved certifi pin through hosted installation

## Confirmed cause and scope

The authenticated hosted diagnostic reported `certifi` **2026.11.20**, while the
approved lock requires **2026.10.23**. The owner confirmed that a later Cloud
setup step upgrades certifi after the initial dependency installation. A pin
passed to one installation command does not constrain a later independent
upgrade. The validator correctly rejected the resulting environment.

The lock was captured for the 13 November release. PyPI dates the two wheels to
23 October and 20 November respectively; the newer release did not exist when
the approved environment was frozen. Certifi supplies CA certificates; this is
not evidence of a changed numerical forecasting model.

Official Community Cloud documentation says `requirements.txt` is attempted with
uv, with pip fallback. The exact later command and working directory have not
been independently observed; the owner's detailed setup-log excerpt is still
needed to establish those facts. No claim is made that the hosted build has
already accepted this correction.

## Fix

`uv.toml` adds `constraint-dependencies = ["certifi==2026.10.23"]`. Unlike an
initial requirements argument, uv's discovered project constraint also applies
to subsequent uv installs/upgrades from this project. This uses a constraint,
not an override: an explicit incompatible request fails resolution rather than
silently changing the approved version.

The production lock, requirements file, production validator, frozen inference
validator, model files, manifests, forecast files and approval metadata are
unchanged. No runtime package metadata is spoofed, package checks skipped, TLS
verification disabled or package installed by the running app.

If Cloud uses pip for the late command, runs outside this repository without
loading its config, or explicitly disables uv configuration, this constraint
cannot control that operation. Admission then remains blocked. Do not call that
a successful deployment; collect the setup command and diagnostic instead.

## Reproduction and regression evidence

Real wheels were downloaded from their PyPI JSON release records and SHA-256
verified before an offline install replay:

| Wheel | SHA-256 |
|---|---|
| certifi-2026.10.23-py3-none-any.whl | e9b54de76e530bb6cf0ccd036787103acb58fd42ba930ea8bf948ddbaa2f61d1 |
| certifi-2026.11.20-py3-none-any.whl | 7422df25243767b9877031a2248cb14d09ddac9beee846f4cef3d5c9191d488f |

The isolated Python 3.14.10 test environment shared the original numerical
packages, with certifi genuinely installed in its own site-packages (not a
metadata-version mock). An unconstrained `uv pip install --upgrade certifi`
installed 2026.11.20 and reproduced the exact hosted rejection through the real
release loader. The same command with repository config discovered installed
2026.10.23. The untouched validator then passed, with **618 base rows**, and
enhanced admission returned **522 forecasts / 12 Top Picks / 20 Top 2 entries**.
There were no other mismatches in this reconstructed environment.

The authenticated real entrypoint and manual calculator passed in that corrected
environment. A real 390px Chromium run showed 12 enhanced cards and 20 game picks,
correct Walker/Nailor assignments, availability warnings, no page errors and no
horizontal overflow. This is local reproduction, not hosted verification.

`tests/test_cloud_dependency_constraints.py` runs fully offline synthetic-wheel
resolution on Python 3.12 and 3.14. It tests the unconstrained upgrade, constraint
discovery, correction, repeat-install stability and rejection of an explicitly
incompatible version. It also checks the constraint matches the original lock
and diagnostics report multiple mismatches together. CI installs uv 0.13.6 only
as a test tool; no application dependency or model environment is changed.

## Owner verification on the existing research app

1. Confirm the research app uses branch `sportsgameodds-free-feasibility`, Python
   3.14 and entrypoint `odds_value_research.py`. Keep all secrets unchanged.
2. After the branch update applies, choose **Manage app → ⋮ → Reboot app → Reboot**
   for the research app only. Streamlit documents reboot as a way to force a fresh
   build for changes to files it does not monitor. Do not just clear its data cache.
3. Inspect setup logs: final certifi must be **2026.10.23**. Do not override a
   failed resolver or reinstall another version manually.
4. Log in and open **Authenticated deployment diagnostics**. Confirm
   `hosted-release-preflight-r2`, the latest Git commit and
   `uv_constraint_present: true`. The certifi installer is shown where metadata
   identifies it; no credentials are displayed.
5. Click **Check approved release loading**. Require **PASS** for
   `research-week11-frozen-20261120-r2`, with 618 base rows. A runtime failure now
   includes **all** `package_mismatches`, not just the first one. Send that safe
   JSON and relevant setup lines if it still fails; do not send secrets.
6. Confirm 12 Enhanced Top Picks, 20 Top 2 selections across ten games and manual
   actual-line/price comparison. Counts naturally reduce after fixture T−60.
   TEN–DAL roof scenarios remain excluded and injury/inactive warnings remain.

Hosted package consistency and authenticated success are not verified until
these checks pass. Original production, Supabase, main and the bookmaker API
remain untouched. No additional service, subscription or cost is introduced.

Sources:
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies
- https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/reboot-your-app
- https://github.com/astral-sh/uv/blob/main/uv.schema.json
- https://pypi.org/pypi/certifi/2026.10.23/json
- https://pypi.org/pypi/certifi/2026.11.20/json
