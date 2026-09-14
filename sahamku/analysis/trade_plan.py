"""Rule-based swing-breakout plans with fixed risk and catalyst context."""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from sahamku import db, levels
from sahamku.config import TZ, settings
from sahamku.pipeline import load_joined
from sahamku.universe import IHSG, from_yf, to_yf

ACTIVE_STATUSES = ("WAITING", "ATTENTION", "CONFIRMED")
STATUS_LABELS = {
    "WAITING": "MENUNGGU",
    "ATTENTION": "PERHATIAN",
    "CONFIRMED": "TERKONFIRMASI",
    "TARGET": "TARGET",
    "STOP": "STOP",
    "EXPIRED": "KEDALUWARSA",
    "CANCELLED": "DIBATALKAN",
    "RISK_BLOCKED": "DITOLAK RISIKO",
}
OFFICIAL_SOURCES = {"idx", "bei", "keterbukaan informasi idx"}
CATALYST_PATTERNS = (
    ("Hasil keuangan", ("laba", "pendapatan", "revenue", "earnings", "margin"), 30),
    ("Kontrak/ekspansi", ("kontrak", "ekspansi", "akuisisi", "proyek baru"), 7),
    ("Corporate action", ("dividen", "buyback", "rights issue", "stock split", "merger"), 30),
    ("Regulasi/sektoral", ("regulasi", "harga komoditas", "suku bunga", "insentif"), 7),
)
DILUTION_WORDS = ("rights issue", "private placement", "waran", "dilusi")
SECTOR_WORDS = {
    "energy": ("energi", "minyak", "gas", "batu bara", "coal"),
    "basic materials": ("material dasar", "nikel", "emas", "timah", "semen", "kimia"),
    "industrials": ("industri", "manufaktur", "alat berat"),
    "consumer cyclicals": ("konsumer siklikal", "ritel", "otomotif", "media"),
    "consumer non-cyclicals": ("konsumer primer", "pangan", "rokok", "perkebunan"),
    "financials": ("keuangan", "perbankan", "bank", "asuransi"),
    "properties & real estate": ("properti", "real estate", "perumahan"),
    "infrastructures": ("infrastruktur", "telekomunikasi", "jalan tol", "menara"),
    "transportation & logistic": ("transportasi", "logistik", "pelayaran", "penerbangan"),
    "technology": ("teknologi", "digital", "data center"),
    "healthcare": ("kesehatan", "rumah sakit", "farmasi"),
}


class PlanError(ValueError):
    """User-facing plan validation error."""


@dataclass(frozen=True)
class Catalyst:
    grade: str
    kind: str | None = None
    source: str | None = None
    title: str | None = None
    link: str | None = None
    published: str | None = None
    risk: str | None = None


@dataclass(frozen=True)
class PlanAlert:
    chat_id: int
    plan_id: int
    code: str
    event: str
    price: float | None
    detail: str


def parse_risk_args(args: str) -> tuple[float, float]:
    parts = (args or "").split()
    if len(parts) not in (1, 2):
        raise PlanError("Format: /risk MODAL [PERSEN] — contoh: /risk 10000000 1")
    try:
        capital = float(parts[0].replace(".", "").replace(",", "."))
        risk_pct = (float(parts[1].replace(",", ".")) if len(parts) == 2
                    else settings.trade_plan_default_risk_pct)
    except ValueError as exc:
        raise PlanError("Modal dan persentase risiko harus berupa angka.") from exc
    if capital < 100_000:
        raise PlanError("Modal minimal Rp100.000.")
    if not 0 < risk_pct <= 5:
        raise PlanError("Risiko per trade harus lebih dari 0% dan maksimal 5%.")
    return capital, risk_pct


def tick_size(reference_price: float) -> int:
    if reference_price < 200:
        return 1
    if reference_price < 500:
        return 2
    if reference_price < 2_000:
        return 5
    if reference_price < 5_000:
        return 10
    return 25


def round_price(value: float, reference_price: float, up: bool) -> float:
    tick = tick_size(reference_price)
    units = math.ceil(value / tick) if up else math.floor(value / tick)
    return float(units * tick)


def catalyst_for(conn: sqlite3.Connection, code: str,
                 now: datetime | None = None) -> Catalyst:
    now = now or datetime.now(TZ)
    cutoff = (now - timedelta(days=30)).isoformat(timespec="minutes")
    rows = conn.execute(
        "SELECT source,title,summary,link,published,sentiment FROM news "
        "WHERE analyzed_at IS NOT NULL AND published>=? "
        "AND (',' || tickers || ',') LIKE ? ORDER BY published DESC",
        (cutoff, f"%,{code.upper()},%"),
    ).fetchall()
    negative = any(int(r["sentiment"] or 0) < 0 for r in rows)
    risk = "ada berita negatif terkait" if negative else None
    for row in rows:
        if int(row["sentiment"] or 0) <= 0:
            continue
        text = f"{row['title']} {row['summary'] or ''}".lower()
        matched = next(
            ((kind, days) for kind, words, days in CATALYST_PATTERNS
             if any(word in text for word in words)),
            None,
        )
        if not matched:
            matched = ("Berita emiten", 7)
        kind, max_days = matched
        try:
            published = datetime.fromisoformat(row["published"])
            if published.tzinfo is None:
                published = published.replace(tzinfo=TZ)
            if now - published > timedelta(days=max_days):
                continue
        except (TypeError, ValueError):
            continue
        source = row["source"]
        official = source.strip().lower() in OFFICIAL_SOURCES
        if any(word in text for word in DILUTION_WORDS):
            risk = "potensi dilusi dari corporate action"
        return Catalyst(
            "A" if official else "B", kind, source, row["title"], row["link"],
            row["published"], risk,
        )
    security = conn.execute(
        "SELECT sector FROM securities WHERE code=?", (code.upper(),)
    ).fetchone()
    sector = security["sector"].strip().lower() if security else ""
    words = next((value for key, value in SECTOR_WORDS.items() if key in sector), ())
    if words:
        market_rows = conn.execute(
            "SELECT source,title,summary,link,published,sentiment FROM news "
            "WHERE analyzed_at IS NOT NULL AND market=1 AND published>=? "
            "ORDER BY published DESC",
            ((now - timedelta(days=7)).isoformat(timespec="minutes"),),
        ).fetchall()
        for row in market_rows:
            text = f"{row['title']} {row['summary'] or ''}".lower()
            if int(row["sentiment"] or 0) > 0 and any(word in text for word in words):
                return Catalyst(
                    "B", "Katalis sektoral", row["source"], row["title"], row["link"],
                    row["published"], risk,
                )
    return Catalyst("C", risk=risk or "tanpa katalis terkonfirmasi")


def market_gate(conn: sqlite3.Connection, date_str: str) -> tuple[bool, str]:
    market = load_joined(conn, IHSG)
    if market.empty or market.index[-1].strftime("%Y-%m-%d") != date_str:
        return False, "data IHSG belum sesuai tanggal laporan"
    last = market.iloc[-1]
    if pd.isna(last.get("sma200")) or float(last["close"]) <= float(last["sma200"]):
        return False, "IHSG belum berada di atas SMA200"
    eligible = set(db.eligible_tickers(conn, date_str))
    closes = db.close_on(conn, date_str)
    rows = closes.loc[closes.index.intersection(eligible)] if eligible else closes.iloc[0:0]
    valid = rows.dropna(subset=["close", "prev_close"])
    if valid.empty:
        return False, "breadth liquid belum tersedia"
    advancers = int((valid["close"] > valid["prev_close"]).sum())
    decliners = int((valid["close"] < valid["prev_close"]).sum())
    return advancers > decliners, f"breadth liquid {advancers} naik : {decliners} turun"


def create(conn: sqlite3.Connection, chat_id: int, code: str,
           now: datetime | None = None) -> sqlite3.Row:
    ticker = to_yf(code)
    existing = db.trade_plan_active_for(conn, chat_id, ticker)
    if existing:
        raise PlanError(f"Plan aktif #{existing['id']} untuk {code} sudah ada.")
    profile = db.trade_risk_get(conn, chat_id)
    if not profile:
        raise PlanError("Atur profil risiko dulu: /risk 10000000 1")
    date_str = db.latest_date(conn, ticker=IHSG)
    if not date_str:
        raise PlanError("Data IHSG belum tersedia.")
    score = conn.execute(
        "SELECT * FROM growth_scores WHERE date=? AND ticker=?", (date_str, ticker)
    ).fetchone()
    eligibility = conn.execute(
        "SELECT eligible,exclusion_reason FROM universe_eligibility WHERE date=? AND ticker=?",
        (date_str, ticker),
    ).fetchone()
    if not eligibility or not eligibility["eligible"]:
        reason = eligibility["exclusion_reason"] if eligibility else "belum dinilai"
        raise PlanError(f"{code} belum lolos universe liquid: {reason}.")
    if not score or float(score["total"]) < settings.potential_growth_min_score:
        actual = float(score["total"]) if score else 0.0
        raise PlanError(
            f"Potential Growth {code} {actual:.1f}, minimum "
            f"{settings.potential_growth_min_score:.0f}."
        )
    frame = load_joined(conn, ticker)
    if len(frame) < 220 or frame.index[-1].strftime("%Y-%m-%d") != date_str:
        raise PlanError("Data teknikal belum cukup atau belum sesuai tanggal laporan.")
    last = frame.iloc[-1]
    required = ("close", "sma50", "sma200", "rsi14", "atr14")
    if any(pd.isna(last[name]) for name in required) or pd.isna(frame["sma50"].iloc[-21]):
        raise PlanError("Indikator teknikal belum lengkap.")
    close = float(last["close"])
    sma50 = float(last["sma50"])
    sma200 = float(last["sma200"])
    rel20 = float(score["rel_20"] or 0)
    rel60 = float(score["rel_60"] or 0)
    technical_failures = []
    if not close > sma50 > sma200:
        technical_failures.append("close > SMA50 > SMA200 belum terpenuhi")
    old_sma50 = float(frame["sma50"].iloc[-21])
    sma50_slope_pct = (sma50 / old_sma50 - 1) * 100
    if sma50_slope_pct <= 0:
        technical_failures.append("kemiringan SMA50 20D belum positif")
    if rel20 <= 0 or rel60 <= 0:
        technical_failures.append("relative strength 20D/60D belum positif")
    prior_high = float(frame.iloc[:-1].tail(20)["high"].max())
    if close < prior_high * 0.95:
        technical_failures.append("harga masih lebih dari 5% di bawah high 20D")
    if technical_failures:
        raise PlanError("Setup TA belum valid: " + "; ".join(technical_failures) + ".")
    gate_ok, gate_detail = market_gate(conn, date_str)
    if not gate_ok:
        raise PlanError("Market gate belum positif: " + gate_detail + ".")

    entry = round_price(
        prior_high * (1 + settings.trade_plan_breakout_buffer_pct / 100), close, True
    )
    atr = float(last["atr14"])
    tick = tick_size(close)
    support = levels.compute(frame).supports
    stop_candidates = [entry - 1.5 * atr]
    if support:
        stop_candidates.append(support[0] - tick)
    stop = round_price(min(stop_candidates), close, False)
    risk_per_share = entry - stop
    stop_pct = risk_per_share / entry * 100
    if stop <= 0 or risk_per_share <= 0 or stop_pct > settings.trade_plan_max_stop_pct:
        raise PlanError(
            f"Jarak stop {stop_pct:.1f}% tidak valid atau melebihi batas "
            f"{settings.trade_plan_max_stop_pct:.0f}%."
        )
    target = round_price(entry + 2 * risk_per_share, close, True)
    capital = float(profile["capital"])
    risk_pct = float(profile["risk_pct"])
    risk_amount = capital * risk_pct / 100
    lots_by_risk = math.floor(risk_amount / risk_per_share / 100)
    lots_by_capital = math.floor(capital / entry / 100)
    lots = min(lots_by_risk, lots_by_capital)
    if lots < 1:
        raise PlanError("Modal/risk budget tidak cukup untuk satu lot pada setup ini.")
    position_value = lots * 100 * entry
    previous_volume = float(frame.iloc[:-1].tail(20)["volume"].mean())
    volume_ratio = float(last["volume"] / previous_volume) if previous_volume > 0 else 0.0
    confirmed = close >= entry and volume_ratio >= settings.breakout_volume_mult
    if close >= entry and not confirmed:
        raise PlanError("Harga menembus trigger, tetapi volume EOD belum mengonfirmasi breakout.")
    if confirmed and (
        db.trade_confirmed_risk_pct(conn, chat_id) + risk_pct
        > settings.trade_plan_max_total_risk_pct
    ):
        raise PlanError("Total risiko plan terkonfirmasi akan melebihi 3% modal.")
    catalyst = catalyst_for(conn, code, now)
    values = {
        "chat_id": chat_id,
        "ticker": ticker,
        "snapshot_date": date_str,
        "status": "CONFIRMED" if confirmed else "WAITING",
        "grade": catalyst.grade,
        "growth_score": float(score["total"]),
        "catalyst_type": catalyst.kind,
        "catalyst_source": catalyst.source,
        "catalyst_title": catalyst.title,
        "catalyst_link": catalyst.link,
        "catalyst_published": catalyst.published,
        "catalyst_risk": catalyst.risk,
        "close": close,
        "sma50": sma50,
        "sma200": sma200,
        "rsi14": float(last["rsi14"]),
        "rel20": rel20,
        "rel60": rel60,
        "atr14": atr,
        "prior_high": prior_high,
        "volume_ratio": volume_ratio,
        "entry": entry,
        "stop": stop,
        "target": target,
        "risk_pct": risk_pct,
        "risk_amount": risk_amount,
        "lots": lots,
        "position_value": position_value,
        "last_evaluated_date": date_str,
        "created_at": (now or datetime.now(TZ)).isoformat(timespec="minutes"),
    }
    values.update({
        "risk_flags": score["risk_flags"],
        "sma50_slope_pct": sma50_slope_pct,
        "swing_support": support[0] if support else None,
    })
    try:
        plan_id = db.trade_plan_add(conn, values)
    except sqlite3.IntegrityError as exc:
        raise PlanError(f"Plan aktif untuk {code} sudah ada.") from exc
    return conn.execute("SELECT * FROM trade_plans WHERE id=?", (plan_id,)).fetchone()


def evaluate_all(conn: sqlite3.Connection, intraday: bool = False,
                 now: datetime | None = None) -> list[PlanAlert]:
    now = now or datetime.now(TZ)
    alerts: list[PlanAlert] = []
    for plan in db.trade_plans_active(conn):
        if intraday:
            alerts.extend(_evaluate_intraday(conn, plan, now))
        else:
            alerts.extend(_evaluate_eod(conn, plan, now))
    return alerts


def _evaluate_intraday(conn: sqlite3.Connection, plan: sqlite3.Row,
                       now: datetime) -> list[PlanAlert]:
    snap = db.intraday_get(conn, plan["ticker"], now.date().isoformat())
    if not snap:
        return []
    high, low, last = float(snap["high"]), float(snap["low"]), float(snap["last"])
    observed = snap["ts"]
    if plan["status"] in ("WAITING", "ATTENTION") and high >= float(plan["entry"]):
        db.trade_plan_update(conn, plan["id"], status="ATTENTION")
        if db.trade_plan_event_add(
            conn, plan["id"], "attention", observed, last, "tunggu konfirmasi close EOD"
        ):
            return [_alert(plan, "attention", last, "Trigger tersentuh; tunggu close EOD.")]
        return []
    if plan["status"] == "CONFIRMED":
        return _close_event(conn, plan, low, high, last, observed)
    return []


def _evaluate_eod(conn: sqlite3.Connection, plan: sqlite3.Row,
                  now: datetime) -> list[PlanAlert]:
    frame = load_joined(conn, plan["ticker"])
    if frame.empty:
        return []
    date_str = frame.index[-1].strftime("%Y-%m-%d")
    if date_str <= plan["last_evaluated_date"]:
        return []
    last = frame.iloc[-1]
    if plan["status"] == "CONFIRMED":
        closed = _close_event(
            conn, plan, float(last["low"]), float(last["high"]), float(last["close"]),
            date_str,
        )
        if closed:
            return closed
        sessions = int(plan["holding_sessions"]) + 1
        if sessions >= settings.trade_plan_holding_sessions:
            return _expire(conn, plan, date_str, float(last["close"]), "holding 20 sesi")
        db.trade_plan_update(
            conn, plan["id"], holding_sessions=sessions, last_evaluated_date=date_str
        )
        return []

    sessions = int(plan["setup_sessions"]) + 1
    previous_volume = float(frame.iloc[:-1].tail(20)["volume"].mean())
    ratio = float(last["volume"] / previous_volume) if previous_volume > 0 else 0.0
    crossed = float(last["close"]) >= float(plan["entry"])
    gate_ok, gate_detail = market_gate(conn, date_str)
    if crossed and ratio >= settings.breakout_volume_mult and gate_ok:
        total_risk = db.trade_confirmed_risk_pct(conn, plan["chat_id"])
        if total_risk + float(plan["risk_pct"]) > settings.trade_plan_max_total_risk_pct:
            return _terminal(
                conn, plan, "RISK_BLOCKED", "risk_blocked", date_str,
                float(last["close"]), "Total risiko terkonfirmasi melebihi 3% modal."
            )
        db.trade_plan_update(
            conn, plan["id"], status="CONFIRMED", setup_sessions=sessions,
            last_evaluated_date=date_str,
        )
        if db.trade_plan_event_add(
            conn, plan["id"], "confirmed", date_str, float(last["close"]), gate_detail
        ):
            return [_alert(
                plan, "confirmed", float(last["close"]),
                f"Breakout terkonfirmasi EOD; {gate_detail}. "
                "Cari entry dekat trigger sesi berikutnya."
            )]
        return []
    if sessions >= settings.trade_plan_setup_sessions:
        return _expire(conn, plan, date_str, float(last["close"]), "setup 5 sesi")
    db.trade_plan_update(
        conn, plan["id"], status="WAITING", setup_sessions=sessions,
        last_evaluated_date=date_str,
    )
    return []


def _close_event(conn: sqlite3.Connection, plan: sqlite3.Row, low: float, high: float,
                 price: float, observed: str) -> list[PlanAlert]:
    if low <= float(plan["stop"]):
        return _terminal(conn, plan, "STOP", "stop", observed, price, "Stop plan tercapai.")
    if high >= float(plan["target"]):
        return _terminal(
            conn, plan, "TARGET", "target", observed, price, "Target 2R tercapai."
        )
    return []


def _expire(conn: sqlite3.Connection, plan: sqlite3.Row, observed: str,
            price: float, reason: str) -> list[PlanAlert]:
    return _terminal(
        conn, plan, "EXPIRED", "expired", observed, price, f"Plan kedaluwarsa ({reason})."
    )


def _terminal(conn: sqlite3.Connection, plan: sqlite3.Row, status: str, event: str,
              observed: str, price: float, detail: str) -> list[PlanAlert]:
    db.trade_plan_update(
        conn, plan["id"], status=status, last_evaluated_date=observed,
        closed_at=datetime.now(TZ).isoformat(timespec="minutes"),
    )
    if db.trade_plan_event_add(conn, plan["id"], event, observed, price, detail):
        return [_alert(plan, event, price, detail)]
    return []


def _alert(plan: sqlite3.Row, event: str, price: float | None, detail: str) -> PlanAlert:
    return PlanAlert(
        int(plan["chat_id"]), int(plan["id"]), from_yf(plan["ticker"]), event, price, detail
    )
