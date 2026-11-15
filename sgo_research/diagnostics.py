"""Allowlisted diagnostics: never render exception text, URLs, payloads or secrets."""

from .contracts import Unavailable


class CollectionBlocked(Unavailable):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


MESSAGES = {
    "CONFIG_REPOSITORY": "SGO_QUOTA_REPOSITORY must be a root-level string naming the existing separate private quota repository.",
    "CONFIG_STORE": "No approved durable quota store is configured. Add SGO_QUOTA_REPOSITORY and its narrowly scoped token to this research app. Do not approve ephemeral disk as persistent.",
    "CONFIG_TOKEN": "SGO_GITHUB_QUOTA_TOKEN is missing. Add it as a root-level research-app secret; no provider request was made.",
    "CONFIG_CAP": "SGO_OBJECT_CAP must be an integer from 1 to 2000. Correct the research secret; do not raise the free ceiling.",
    "GITHUB_READ_401": "GitHub rejected quota authentication (HTTP 401). Check that the quota token is current and correctly entered in this research app.",
    "GITHUB_WRITE_401": "GitHub rejected the quota write credentials (HTTP 401). Check the quota token; do not reset the counter.",
    "GITHUB_READ_403": "GitHub denied quota read access (HTTP 403). Check token permissions, repository approval and GitHub rate limits.",
    "GITHUB_WRITE_403": "GitHub denied the atomic quota write (HTTP 403). The token needs Contents read/write on the private quota repository; GitHub rate limits may also apply.",
    "GITHUB_READ_404": "GitHub could not read the private quota repository or quota.json (HTTP 404). Check the repository name and token's selected-repository access. Do not create a replacement counter.",
    "GITHUB_WRITE_404": "GitHub could not access the quota write endpoint (HTTP 404). Check the token's private-repository access; do not reset state.",
    "GITHUB_HTTP": "GitHub returned an unexpected status. Collection stopped without exposing its response. Review private quota access before retrying.",
    "GITHUB_NETWORK": "The research host could not complete a GitHub quota request. No automatic retry; check host connectivity.",
    "RATE": "The conservative six-HTTP-calls/minute limit was reached. Wait at least 60 seconds before a manual retry; do not reset counters.",
    "HALTED": "The durable collector is halted pending manual review. Do not clear the halt or reset quota. Report this diagnostic for investigation.",
    "UNVERIFIED": "The private counter's conditional-update verification is missing. Collection is blocked; do not bypass or recreate the counter.",
    "STATE": "Private quota state is missing or invalid. Collection stopped; preserve quota.json and investigate without resetting it.",
    "PRIVATE": "Quota storage is not verified as a separate private repository. Collection is blocked.",
    "CONFLICT": "Atomic quota updates repeatedly conflicted. No associated provider request was made. Wait before a manual retry.",
    "BUDGET": "The conservative lifetime/monthly allowance or safety headroom is exhausted. Collection stopped; no paid fallback or counter reset.",
    "TERMS": 'SGO_PRIVATE_CACHE_TERMS_ACK must be the root-level string "1" in the research app before collection.',
    "BOOKS": "Select at least one supported free bookmaker before collection.",
    "KEY": "SPORTSGAMEODDS_API_KEY is missing or malformed in the research app. No provider request was made.",
    "WINDOW": "The requested fixture window is invalid or no longer upcoming. Reselect a T−60 eligible fixture; the cutoff is not relaxed.",
    "PROVIDER_AUTH": "SportsGameOdds returned HTTP 401/403. The collector is halted: verify the free key and entitlement before manual review.",
    "PROVIDER_RATE": "SportsGameOdds returned HTTP 429. The collector is halted; do not retry or reset it without review.",
    "PROVIDER_NETWORK": "The research host could not complete the SportsGameOdds request. No automatic retry; a reservation may already have been recorded.",
    "UNSAFE": "Provider response exceeded the size/content safety guard. The collector is halted. Preserve quota state and report this code.",
    "ACCOUNT": "The provider did not establish an active Amateur account with usable limits. Collection stopped; verify the free account without upgrading.",
    "SCHEMA": "The provider response failed schema, pregame or timestamp validation. No quotes were accepted. Preserve safeguards and report this code.",
    "UNKNOWN": "An unclassified collection failure occurred. No automatic retry. Report this code and collection stage; do not share secrets or raw responses.",
}

EXACT = {
    "No private durable quota store configured. A verified private GitHub lifetime counter or approved persistent private volume is required.": "CONFIG_STORE",
    "Conservative six-request/minute limit reached": "RATE",
    "Collector halted; manual review required": "HALTED",
    "Collector halted": "HALTED",
    "Research collector halted; manual review required": "HALTED",
    "Private conditional-update verification required": "UNVERIFIED",
    "Private quota state invalid/missing; no automatic reset": "STATE",
    "Quota repository must be private": "PRIVATE",
    "A separate private research quota repository is required": "PRIVATE",
    "Private quota write conflict; no odds request": "CONFLICT",
    "Conservative lifetime/free monthly budget reached; no reset": "BUDGET",
    "Account interval allowance insufficient": "BUDGET",
    "Private research data-use/cache terms not acknowledged": "TERMS",
    "Bookmaker not on documented Amateur whitelist": "BOOKS",
    "Research API key missing/invalid; no request made": "KEY",
    "Only a bounded upcoming NFL window is allowed": "WINDOW",
    "Provider HTTP 401; no retry or paid fallback": "PROVIDER_AUTH",
    "Provider HTTP 403; no retry or paid fallback": "PROVIDER_AUTH",
    "Provider HTTP 429; no retry or paid fallback": "PROVIDER_RATE",
    "Provider network request failed; no retries": "PROVIDER_NETWORK",
    "Unsafe response size/content discarded": "UNSAFE",
    "Private quota service unavailable; no odds request": "GITHUB_NETWORK",
    "Active Amateur tier is not confirmed; no paid or trial fallback": "ACCOUNT",
    "Invalid account usage schema": "ACCOUNT",
    "Exact monthly usage/reset unavailable; collection stopped": "ACCOUNT",
    "Response includes non-pregame NFL event; discarded": "SCHEMA",
    "Unexpected result payload; discarded without analysis": "SCHEMA",
    "Response exceeded reserved event-object limit": "SCHEMA",
    "Invalid provider JSON": "SCHEMA",
    "Unexpected provider envelope": "SCHEMA",
}


def safe_diagnostic(error):
    code = (
        error.code
        if isinstance(error, CollectionBlocked)
        else EXACT.get(str(error), "UNKNOWN")
    )
    if code not in MESSAGES:
        code = "UNKNOWN"
    return code, MESSAGES[code]
