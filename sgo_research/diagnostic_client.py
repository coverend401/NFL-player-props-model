"""Operator-only bounded diagnostic. Does not recover halts or expose credentials."""

from datetime import timedelta
from urllib.parse import urlencode

from .contracts import STAT_MARKETS, Unavailable, team_key, utc
from .event_client import EventClient


class DiagnosticClient(EventClient):
    """One discovery + one price response, <=3 HTTP calls and <=2 objects.

    One verified account observation can be reused within 30 seconds in this
    same foreground sequence. Each event is still separately reserved through
    the unchanged atomic ledger/headroom checks. No additional account request,
    retry, pagination, automatic recovery or UI polling is provided.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.provider_calls = 0
        self.requested_objects = 0
        self.discovery_used = False
        self.prices_used = False
        self.discovered = {}
        self.account_observation = None
        self.account_key = None
        original = self.get

        def bounded_get(*args, **kwargs):
            if (
                args
                and args[0].endswith("/events")
                and self.account_observation is not None
            ):
                age = self.clock() - self.account_observation[1]
                if not timedelta(0) <= age <= timedelta(seconds=30):
                    raise Unavailable(
                        "Diagnostic account observation expired before HTTP; reservation retained"
                    )
            if self.provider_calls >= 3:
                raise Unavailable("Diagnostic HTTP budget exhausted; no request")
            self.provider_calls += 1
            return original(*args, **kwargs)

        self.get = bounded_get

    def _request(self, path, params=None):
        if path not in ["/account/usage", "/events"]:
            raise Unavailable("Diagnostic endpoint not permitted")
        state, _ = self.store._read()
        if state.get("halt") or state.get("conditional_updates_verified") is not True:
            raise Unavailable("Collector halted or conditional updates unverified")
        if path == "/account/usage" and self.account_observation is not None:
            age = self.clock() - self.account_observation[1]
            if (
                not timedelta(0) <= age <= timedelta(seconds=30)
                or self.key != self.account_key
            ):
                raise Unavailable(
                    "Diagnostic account observation expired or credential changed; no retry"
                )
            return self.account_observation
        result = super()._request(path, params)
        if path == "/account/usage":
            self.account_observation = result
            self.account_key = self.key
        return result

    def _fetch(self, params, *, purpose, expected=None):
        if params.get("limit") != 1 or params.get("cursor"):
            raise Unavailable("Diagnostic requires one event and no pagination")
        params = dict(params)
        if purpose == "prices":
            players = params.get("playerID", "").split(",")
            if len(players) != 1 or not players[0]:
                raise Unavailable(
                    "One verified provider player ID required; no broad fallback"
                )
            params["oddID"] = ",".join(
                f"{stat}-{players[0]}-game-ou-over" for stat in STAT_MARKETS
            )
            if len(urlencode(params)) > 4096:
                raise Unavailable(
                    "Diagnostic filters exceed URL guard; filters retained, no request"
                )
        if self.requested_objects >= 2:
            raise Unavailable("Diagnostic object bound exhausted")
        self.requested_objects += 1
        return super()._fetch(params, purpose=purpose, expected=expected)

    def discover(self, after, before, books, cursor=None, *, limit=1):
        if self.discovery_used or cursor is not None or limit != 1:
            raise Unavailable(
                "One single-event diagnostic discovery only; no retry or pagination"
            )
        self.discovery_used = True
        snapshot = super().discover(after, before, books, limit=1)
        self.discovered = {
            event["eventID"]: event for event in snapshot.get("events", [])
        }
        return snapshot

    def prices(self, specs, books, player_ids=()):
        if self.prices_used or len(specs) != 1 or not self.discovery_used:
            raise Unavailable("One discovered event price diagnostic only")
        self.prices_used = True
        spec = specs[0]
        event = self.discovered.get(spec.get("eventID"))
        if not event:
            raise Unavailable("No verified discovery event; no price request")
        away, home = spec["game_id"].split("_")[-2:]
        try:
            actual = [
                team_key(event["teams"][side]["names"]["short"])
                for side in ["away", "home"]
            ]
            if (
                actual != [away, home]
                or abs(
                    (
                        utc(event["status"]["startsAt"]) - utc(spec["kickoff"])
                    ).total_seconds()
                )
                > 60
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise Unavailable(
                "Discovery fixture identity/kickoff mismatch; no request"
            ) from None
        if len(player_ids) != 1 or player_ids[0] not in event.get("players", {}):
            raise Unavailable(
                "Discovery did not verify the requested player ID; no request"
            )
        return super().prices(specs, books, player_ids)
