"""Alert level harga/RSI, dicek setelah data EOD & indikator selesai dihitung."""

from __future__ import annotations

import operator
import re
import sqlite3
from dataclasses import dataclass

from sahamku import db
from sahamku.pipeline import load_joined
from sahamku.universe import is_known_code, to_yf

MAX_ALERTS_PER_CHAT = 10
OPS = {">": operator.gt, "<": operator.lt, ">=": operator.ge, "<=": operator.le}
METRICS = {"close": "harga", "rsi": "RSI"}

# /alert BBCA > 6500  |  /alert BBCA rsi < 30  |  /alert BBCA close >= 6.500
_RE = re.compile(
    r"^\s*(?P<code>[A-Za-z]{4})\s+(?:(?P<metric>close|rsi)\s+)?(?P<op>>=|<=|>|<)\s*"
    r"(?P<value>[\d.,]+)\s*$", re.I)


@dataclass(frozen=True)
class AlertSpec:
    code: str
    metric: str
    op: str
    value: float

    def label(self) -> str:
        v = f"{self.value:,.0f}" if self.metric == "close" else f"{self.value:g}"
        return f"{self.code} {METRICS[self.metric]} {self.op} {v}"


def parse(args: str) -> AlertSpec | str:
    """Return AlertSpec atau pesan error (str)."""
    m = _RE.match(args or "")
    if not m:
        return ("Format: /alert KODE > HARGA  atau  /alert KODE rsi < 30\n"
                "Contoh: /alert BBCA > 6500 · /alert TLKM <= 2500 · /alert BBRI rsi < 30")
    code = m.group("code").upper()
    if not is_known_code(code):
        return f"{code} tidak ada di universe LQ45."
    metric = (m.group("metric") or "close").lower()
    raw = m.group("value").replace(".", "").replace(",", ".") if metric == "close" \
        else m.group("value").replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        return "Angka tidak valid."
    if metric == "rsi" and not 0 < value < 100:
        return "RSI harus antara 0 dan 100."
    if metric == "close" and value <= 0:
        return "Harga harus lebih dari 0."
    return AlertSpec(code, metric, m.group("op"), value)


@dataclass
class Triggered:
    alert_id: int
    chat_id: int
    spec: AlertSpec
    actual: float
    date: str


def check_all(conn: sqlite3.Connection) -> list[Triggered]:
    """Evaluasi semua alert aktif terhadap bar terakhir. Tandai yang kena (one-shot)."""
    rows = db.alerts_active(conn)
    if not rows:
        return []
    cache: dict[str, tuple[str, float, float | None]] = {}
    out: list[Triggered] = []
    for r in rows:
        code = r["code"]
        if code not in cache:
            j = load_joined(conn, to_yf(code), limit=1)
            if j.empty:
                continue
            last = j.iloc[-1]
            rsi = None if last["rsi14"] != last["rsi14"] else float(last["rsi14"])
            cache[code] = (j.index[-1].strftime("%Y-%m-%d"), float(last["close"]), rsi)
        date_str, close, rsi = cache[code]
        actual = close if r["metric"] == "close" else rsi
        if actual is None:
            continue
        if OPS[r["op"]](actual, r["value"]):
            db.alert_mark_triggered(conn, r["id"])
            out.append(Triggered(
                r["id"], r["chat_id"],
                AlertSpec(code, r["metric"], r["op"], float(r["value"])), actual, date_str))
    return out
