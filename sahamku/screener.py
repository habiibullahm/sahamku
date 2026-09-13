"""/screener — filter cepat universe berdasarkan indikator, sinyal, dan rating hari ini."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

import pandas as pd

from sahamku import db
from sahamku.pipeline import load_joined
from sahamku.universe import from_yf, scan_tickers, universe_label

MAX_ROWS = 20

# nama filter → deskripsi (dipakai di /screener tanpa argumen)
HELP = """<b>/screener</b> — filter universe aktif (data close terakhir)

Contoh:
  /screener rating=bullish
  /screener rsi&lt;35 above200
  /screener vol&gt;2x chg&gt;2
  /screener squeeze
  /screener oversold

Filter yang tersedia:
  rating=bullish|bearish|netral
  rsi&lt;N  rsi&gt;N        RSI14
  chg&gt;N  chg&lt;N        % perubahan hari ini
  vol&gt;Nx              volume vs rata-rata 20 hari
  above200 / below200   posisi vs SMA200
  squeeze               Bollinger squeeze
  oversold / overbought RSI cross 30/70 hari ini
  breakout / breakdown  tembus high/low 20 hari + volume
  golden / death        golden / death cross hari ini
  macd_up / macd_down   MACD cross hari ini
Gabungkan beberapa filter dengan spasi (AND)."""

_KV = re.compile(r"^(rating)=(bullish|bearish|netral)$", re.I)
_CMP = re.compile(r"^(rsi|chg|vol)\s*(>=|<=|>|<)\s*(-?[\d.]+)x?$", re.I)
_FLAGS = {
    "above200": "above_sma200", "below200": "below_sma200", "squeeze": "bb_squeeze",
    "oversold": "rsi_oversold", "overbought": "rsi_overbought",
    "breakout": "breakout_high", "breakdown": "breakdown_low",
    "golden": "golden_cross", "death": "death_cross",
    "macd_up": "macd_bull_cross", "macd_down": "macd_bear_cross",
}


@dataclass
class Query:
    rating: str | None = None
    cmp: list[tuple[str, str, float]] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.rating or self.cmp or self.flags)


def parse(args: str) -> Query:
    q = Query()
    for tok in (args or "").split():
        t = tok.lower()
        if m := _KV.match(t):
            q.rating = m.group(2)
        elif m := _CMP.match(t):
            q.cmp.append((m.group(1), m.group(2), float(m.group(3))))
        elif t in _FLAGS:
            q.flags.append(_FLAGS[t])
        else:
            q.errors.append(tok)
    return q


# ---------- snapshot universe (cache per tanggal) ----------

_cache: dict[str, pd.DataFrame] = {}


def snapshot(conn: sqlite3.Connection) -> pd.DataFrame:
    """Satu baris per saham: close, chg, rsi, vol_x, rating, score, rules(set)."""
    date_str = db.latest_date(conn)
    if not date_str:
        return pd.DataFrame()
    cache_key = f"{date_str}:{universe_label(conn)}"
    if cache_key in _cache:
        return _cache[cache_key]
    rows = []
    for t in scan_tickers(conn, date_str):
        j = load_joined(conn, t, limit=2)
        if j.empty or j.index[-1].strftime("%Y-%m-%d") != date_str:
            continue
        last = j.iloc[-1]
        prev_close = float(j["close"].iloc[-2]) if len(j) > 1 else None
        rating = db.rating_for(conn, t, date_str)
        rules = {r["rule"] for r in db.signals_for(conn, t, date_str)}
        rows.append({
            "code": from_yf(t),
            "close": float(last["close"]),
            "chg": (float(last["close"]) / prev_close - 1) * 100 if prev_close else None,
            "rsi": None if pd.isna(last["rsi14"]) else float(last["rsi14"]),
            "vol_x": (float(last["volume"]) / float(last["vol_avg20"])
                      if last["vol_avg20"] and not pd.isna(last["vol_avg20"]) else None),
            "rating": rating["rating"] if rating else "netral",
            "score": int(rating["score"]) if rating else 0,
            "rules": rules,
        })
    df = pd.DataFrame(rows)
    _cache.clear()
    _cache[cache_key] = df
    return df


def run(conn: sqlite3.Connection, q: Query) -> tuple[str, pd.DataFrame]:
    """Return (tanggal, hasil terurut)."""
    df = snapshot(conn)
    if df.empty:
        return "", df
    mask = pd.Series(True, index=df.index)
    if q.rating:
        mask &= df["rating"] == q.rating
    for field_, op, val in q.cmp:
        col = {"rsi": "rsi", "chg": "chg", "vol": "vol_x"}[field_]
        s = df[col]
        m = {">": s > val, "<": s < val, ">=": s >= val, "<=": s <= val}[op]
        mask &= m.fillna(False)
    for rule in q.flags:
        mask &= df["rules"].apply(lambda rs, rule=rule: rule in rs)
    out = df[mask].sort_values(["score", "chg"], ascending=[False, False])
    return db.latest_date(conn), out


def describe(q: Query) -> str:
    parts = []
    if q.rating:
        parts.append(f"rating={q.rating}")
    parts += [f"{f}{op}{v:g}{'x' if f == 'vol' else ''}" for f, op, v in q.cmp]
    inv = {v: k for k, v in _FLAGS.items()}
    parts += [inv[r] for r in q.flags]
    return " ".join(parts)


def invalidate() -> None:
    _cache.clear()
