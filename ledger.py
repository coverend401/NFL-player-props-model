"""
Permanent betting ledger.

Original bet details (line, odds, model numbers, model version...) are LOCKED at
insert time: the update path only ever touches result / closing / notes fields,
and a hash of the locked fields lets you verify nothing was altered later.

Backends:
  - SupabaseBackend : real persistence (needs SUPABASE_URL / SUPABASE_KEY in Streamlit secrets)
  - SQLiteBackend   : local file, used for testing. On Streamlit Cloud this file is WIPED on every
                      reboot, so it is only a stand-in - the app shows a warning when it is active.
"""
import hashlib
import json
import math
import sqlite3
import uuid
from datetime import datetime, timezone

import pandas as pd

LOCKED_FIELDS = [
    "created_at", "bet_type", "paper", "game", "game_key", "team", "position", "player", "market",
    "direction", "bookmaker", "line", "odds_decimal", "model_prob", "implied_prob", "ev_pct",
    "confidence", "bet_score", "recommended_stake", "actual_stake", "model_version",
    "parlay_odds_decimal", "combined_model_prob", "parlay_score", "legs_original",
]
MUTABLE_FIELDS = ["status", "result", "return_amount", "profit", "closing_line", "closing_odds_decimal",
                  "clv_pct", "line_moved_favourably", "settled_at", "notes", "legs_json"]
ALL_COLUMNS = ["bet_id", "original_hash"] + LOCKED_FIELDS + MUTABLE_FIELDS


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean(o):
    """Plain-Python, JSON-safe values only (numpy scalars -> python, NaN/inf -> None) so Supabase never chokes."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if hasattr(o, "item") and not isinstance(o, (str, bytes)):
        try:
            o = o.item()
        except Exception:
            pass
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    return o


def _canon(k, v):
    """Make a value hash-stable across backends (SQLite returns 1/0 for booleans, Postgres may return ints for floats)."""
    if k == "paper":
        return bool(v)
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return round(float(v), 6)
    if isinstance(v, (list, dict)):
        return json.loads(json.dumps(v, default=str, sort_keys=True))
    return v


def original_hash(row: dict) -> str:
    payload = {k: _canon(k, row.get(k)) for k in LOCKED_FIELDS}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


# --------------------------------------------------------------------------
class SQLiteBackend:
    name = "local-sqlite (temporary)"
    persistent = False
    JSON_COLS = ["legs_original", "legs_json"]

    def __init__(self, path=":memory:"):
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        cols = ", ".join(f'"{c}"' for c in ALL_COLUMNS)
        self.con.execute(f'CREATE TABLE IF NOT EXISTS bets ({cols}, PRIMARY KEY (bet_id))')
        self.con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        self.con.commit()

    def insert(self, row):
        row = {k: (json.dumps(v, default=str) if k in self.JSON_COLS and v is not None else v) for k, v in row.items()}
        cols = list(row)
        self.con.execute(f'INSERT INTO bets ({",".join(chr(34)+c+chr(34) for c in cols)}) '
                         f'VALUES ({",".join("?"*len(cols))})', [row[c] for c in cols])
        self.con.commit()

    def fetch_all(self):
        rows = [dict(r) for r in self.con.execute("SELECT * FROM bets ORDER BY created_at DESC")]
        for r in rows:
            for c in self.JSON_COLS:
                if r.get(c):
                    r[c] = json.loads(r[c])
        return rows

    def update(self, bet_id, fields):
        fields = {k: (json.dumps(v, default=str) if k in self.JSON_COLS and v is not None else v) for k, v in fields.items()}
        sets = ", ".join(f'"{k}" = ?' for k in fields)
        self.con.execute(f"UPDATE bets SET {sets} WHERE bet_id = ?", list(fields.values()) + [bet_id])
        self.con.commit()

    def get_setting(self, key, default=None):
        r = self.con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return json.loads(r["value"]) if r else default

    def set_setting(self, key, value):
        self.con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, json.dumps(value)))
        self.con.commit()


class SupabaseBackend:
    name = "Supabase (permanent)"
    persistent = True

    def __init__(self, url, key):
        from supabase import create_client
        self.client = create_client(url, key)

    def insert(self, row):
        self.client.table("bets").insert(row).execute()

    def fetch_all(self):
        return self.client.table("bets").select("*").order("created_at", desc=True).execute().data

    def update(self, bet_id, fields):
        self.client.table("bets").update(fields).eq("bet_id", bet_id).execute()

    def get_setting(self, key, default=None):
        r = self.client.table("settings").select("value").eq("key", key).execute().data
        return json.loads(r[0]["value"]) if r else default

    def set_setting(self, key, value):
        self.client.table("settings").upsert({"key": key, "value": json.dumps(value)}).execute()


# --------------------------------------------------------------------------
class Ledger:
    def __init__(self, backend):
        self.b = backend

    # ---- recording ------------------------------------------------------
    def record_single(self, *, paper, game, game_key, team, position, player, market, direction, bookmaker,
                      line, odds_decimal, model_prob, ev_pct, confidence, bet_score, recommended_stake,
                      actual_stake, model_version, notes=""):
        row = dict(bet_id=str(uuid.uuid4()), created_at=_now(), bet_type="single", paper=bool(paper), game=game,
                   game_key=game_key, team=team, position=position, player=player, market=market,
                   direction=direction, bookmaker=bookmaker, line=line, odds_decimal=odds_decimal,
                   model_prob=model_prob, implied_prob=1 / odds_decimal, ev_pct=ev_pct, confidence=confidence,
                   bet_score=bet_score, recommended_stake=recommended_stake, actual_stake=actual_stake,
                   model_version=model_version, parlay_odds_decimal=None, combined_model_prob=None,
                   parlay_score=None, legs_original=None, status="open", result=None, return_amount=None,
                   profit=None, closing_line=None, closing_odds_decimal=None, clv_pct=None,
                   line_moved_favourably=None, settled_at=None, notes=notes, legs_json=None)
        row = _clean(row)
        row["original_hash"] = original_hash(row)
        self.b.insert(row)
        return row["bet_id"]

    def record_parlay(self, *, paper, legs, bet_type, bookmaker, parlay_odds_decimal, combined_model_prob,
                      ev_pct, confidence, parlay_score, recommended_stake, actual_stake, model_version, notes=""):
        legs = [{**l, "result": None, "closing_line": None, "closing_odds_decimal": None} for l in legs]
        original = [{k: l.get(k) for k in ("leg_id", "player", "team", "position", "market", "side", "line",
                                            "odds", "model_prob", "game_key", "confidence")} for l in legs]
        row = dict(bet_id=str(uuid.uuid4()), created_at=_now(), bet_type=bet_type, paper=bool(paper),
                   game=" + ".join(sorted({str(l.get("game_key")) for l in legs})),
                   game_key=None, team=None, position=None,
                   player=" + ".join(l["player"] for l in legs), market=" + ".join(l["market"] for l in legs),
                   direction=" + ".join(l["side"] for l in legs), bookmaker=bookmaker,
                   line=None, odds_decimal=None, model_prob=combined_model_prob,
                   implied_prob=1 / parlay_odds_decimal, ev_pct=ev_pct, confidence=confidence, bet_score=None,
                   recommended_stake=recommended_stake, actual_stake=actual_stake, model_version=model_version,
                   parlay_odds_decimal=parlay_odds_decimal, combined_model_prob=combined_model_prob,
                   parlay_score=parlay_score, legs_original=original, status="open", result=None,
                   return_amount=None, profit=None, closing_line=None, closing_odds_decimal=None, clv_pct=None,
                   line_moved_favourably=None, settled_at=None, notes=notes, legs_json=legs)
        row = _clean(row)
        row["original_hash"] = original_hash(row)
        self.b.insert(row)
        return row["bet_id"]

    # ---- reading --------------------------------------------------------
    def dataframe(self) -> pd.DataFrame:
        rows = self.b.fetch_all()
        if not rows:
            return pd.DataFrame(columns=ALL_COLUMNS)
        df = pd.DataFrame(rows)
        for c in ALL_COLUMNS:
            if c not in df:
                df[c] = None
        for c in ("paper",):
            df[c] = df[c].astype(bool)
        return df

    def _get(self, bet_id):
        for r in self.b.fetch_all():
            if r["bet_id"] == bet_id:
                return r
        raise KeyError(bet_id)

    def verify_integrity(self) -> list:
        """Bet IDs whose locked fields no longer match the hash taken at insert time."""
        return [r["bet_id"] for r in self.b.fetch_all() if original_hash(r) != r.get("original_hash")]

    # ---- closing line / CLV --------------------------------------------
    @staticmethod
    def _clv(orig_odds, close_odds):
        """Price-based CLV: positive means you got a better price than the close."""
        return (orig_odds / close_odds - 1) * 100

    @staticmethod
    def _line_favourable(direction, orig_line, close_line):
        if orig_line is None or close_line is None or orig_line == close_line:
            return None
        return bool(close_line > orig_line) if str(direction).lower().startswith("over") else bool(close_line < orig_line)

    def set_closing_single(self, bet_id, closing_line, closing_odds_decimal):
        r = self._get(bet_id)
        self.b.update(bet_id, _clean({
            "closing_line": closing_line, "closing_odds_decimal": closing_odds_decimal,
            "clv_pct": self._clv(r["odds_decimal"], closing_odds_decimal),
            "line_moved_favourably": self._line_favourable(r["direction"], r["line"], closing_line)}))

    def set_closing_leg(self, bet_id, leg_index, closing_line, closing_odds_decimal):
        r = self._get(bet_id)
        legs = r["legs_json"]
        legs[leg_index]["closing_line"] = closing_line
        legs[leg_index]["closing_odds_decimal"] = closing_odds_decimal
        fields = {"legs_json": legs}
        if all(l.get("closing_odds_decimal") for l in legs):
            factor = 1.0
            for l in legs:
                factor *= l["odds"] / l["closing_odds_decimal"]
            fields["clv_pct"] = (factor - 1) * 100
        self.b.update(bet_id, _clean(fields))

    # ---- settlement -----------------------------------------------------
    def settle_single(self, bet_id, result):
        assert result in ("win", "loss", "push", "void")
        r = self._get(bet_id)
        stake = float(r["actual_stake"] or 0)
        ret = {"win": stake * r["odds_decimal"], "loss": 0.0, "push": stake, "void": stake}[result]
        self.b.update(bet_id, _clean({"status": "settled", "result": result, "return_amount": round(ret, 2),
                               "profit": round(ret - stake, 2), "settled_at": _now()}))

    def settle_parlay(self, bet_id, leg_results: list):
        """Push/void legs drop out of the price (treated as 1.00); any losing leg loses the bet."""
        r = self._get(bet_id)
        legs = r["legs_json"]
        for l, res in zip(legs, leg_results):
            l["result"] = res
        stake = float(r["actual_stake"] or 0)
        if any(x == "loss" for x in leg_results):
            result, ret = "loss", 0.0
        elif all(x in ("push", "void") for x in leg_results):
            result, ret = "void", stake
        else:
            price = 1.0
            for l, x in zip(legs, leg_results):
                if x == "win":
                    price *= l["odds"]
            result, ret = "win", stake * price
        self.b.update(bet_id, _clean({"legs_json": legs, "status": "settled", "result": result,
                               "return_amount": round(ret, 2), "profit": round(ret - stake, 2),
                               "settled_at": _now()}))

    def add_note(self, bet_id, note):
        self.b.update(bet_id, _clean({"notes": note}))

    def realised_live_pl(self) -> float:
        df = self.dataframe()
        if df.empty:
            return 0.0
        d = df[(~df["paper"]) & (df["status"] == "settled")]
        return float(pd.to_numeric(d["profit"], errors="coerce").fillna(0).sum())

    # ---- settings -------------------------------------------------------
    def get_setting(self, key, default=None):
        return self.b.get_setting(key, default)

    def set_setting(self, key, value):
        self.b.set_setting(key, value)
