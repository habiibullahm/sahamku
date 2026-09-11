"""Format laporan menjadi teks Telegram (parse_mode HTML)."""

from __future__ import annotations

from html import escape

from sahamku.analysis.aftermarket import AfterMarketReport, Mover, TickerSignals
from sahamku.analysis.premarket import PreMarketReport
from sahamku.config import DISCLAIMER
from sahamku.signals.scoring import RATING_EMOJI

TELEGRAM_MAX = 4096


def pct(v: float | None) -> str:
    if v is None:
        return "n/a"
    arrow = "▲" if v > 0 else "▼" if v < 0 else "•"
    return f"{arrow} {v:+.2f}%"


def num(v: float | None, dec: int = 0) -> str:
    if v is None:
        return "n/a"
    return f"{v:,.{dec}f}"


def vol(v: float | None) -> str:
    if v is None:
        return "n/a"
    if v >= 1e9:
        return f"{v / 1e9:.2f}M"
    if v >= 1e6:
        return f"{v / 1e6:.1f}jt"
    return f"{v:,.0f}"


def _mover_line(m: Mover) -> str:
    return f"  <code>{m.code}</code> {num(m.close)}  {pct(m.pct)}"


def _signal_block(items: list[TickerSignals], limit: int = 10) -> str:
    if not items:
        return "  —"
    lines = []
    for s in items[:limit]:
        rules = "; ".join(escape(r) for r in s.rules) or "tren"
        lines.append(f"  {RATING_EMOJI[s.rating]} <b>{s.code}</b> ({s.score:+d}) — {rules}")
    if len(items) > limit:
        lines.append(f"  … +{len(items) - limit} lainnya")
    return "\n".join(lines)


def aftermarket(r: AfterMarketReport) -> str:
    parts = [
        f"📊 <b>Sahamku — After Market {r.date}</b>",
        "",
        f"<b>IHSG</b> {num(r.ihsg_close, 2)}  {pct(r.ihsg_pct)}",
        f"Vol {vol(r.ihsg_volume)} · ▲{r.advancers} ▼{r.decliners} •{r.unchanged} (LQ45)",
        "",
        "🚀 <b>Top Gainers</b>",
        *(_mover_line(m) for m in r.gainers),
        "",
        "📉 <b>Top Losers</b>",
        *(_mover_line(m) for m in r.losers),
        "",
        f"🟢 <b>Sinyal Bullish</b> ({len(r.bullish)})",
        _signal_block(r.bullish),
        "",
        f"🔴 <b>Sinyal Bearish</b> ({len(r.bearish)})",
        _signal_block(r.bearish),
    ]
    if r.squeeze:
        parts += ["", "🎯 <b>Bollinger Squeeze</b>: " + ", ".join(r.squeeze)]
    if r.watchlist:
        parts += ["", "👀 <b>Watchlist</b>"]
        for code, (m, s) in r.watchlist.items():
            if m is None:
                parts.append(f"  <code>{code}</code> — data tidak ada")
                continue
            rt = f" {RATING_EMOJI[s.rating]} {s.rating} ({s.score:+d})" if s else ""
            parts.append(f"  <code>{code}</code> {num(m.close)} {pct(m.pct)}{rt}")
    if r.missing:
        parts += ["", "⚠️ Data belum lengkap untuk: " + ", ".join(r.missing)]
    parts += ["", f"<i>{DISCLAIMER}</i>"]
    return _clip("\n".join(parts))


def premarket(r: PreMarketReport) -> str:
    parts = [
        f"🌅 <b>Sahamku — Pre-Market {r.date}</b>",
        "",
        f"Sentimen pembukaan: <b>{r.sentiment_label}</b> (skor {r.sentiment_score:+d})",
        "",
        "🌍 <b>Global semalam</b>",
        *(f"  {escape(name)}: {num(c, 2)} {pct(p)}" for name, c, p in r.global_rows),
        "",
        "🇮🇩 <b>IHSG</b>",
        f"  Close kemarin {num(r.ihsg_close, 2)} {pct(r.ihsg_pct)}",
        f"  Support {num(r.support, 0)} · Resistance {num(r.resistance, 0)}",
        f"  RSI {num(r.ihsg_rsi, 1)} · {escape(r.ihsg_trend)}",
    ]
    if r.notes:
        parts += ["", "📝 <b>Catatan</b>", *(f"  • {escape(n)}" for n in r.notes)]
    if r.bullish_yesterday:
        parts += ["", "🟢 <b>Bullish dari scan kemarin</b>: " + ", ".join(r.bullish_yesterday)]
    if r.bearish_yesterday:
        parts += ["🔴 <b>Bearish dari scan kemarin</b>: " + ", ".join(r.bearish_yesterday)]
    if r.watchlist:
        parts += ["", "👀 <b>Watchlist</b>"]
        for code, info in r.watchlist.items():
            parts.append(f"  <code>{code}</code> {escape(info)}")
    parts += ["", f"<i>{DISCLAIMER}</i>"]
    return _clip("\n".join(parts))


def stock_snapshot(code: str, date: str, close: float, pct_: float | None, volume: float,
                   ind: dict[str, float | None], rating_: str | None, score: int | None,
                   rules: list[str]) -> str:
    lines = [
        f"📈 <b>{code}</b> — {date}",
        f"Close {num(close)}  {pct(pct_)} · Vol {vol(volume)}",
        "",
        "<b>Indikator</b>",
        f"  SMA20 {num(ind.get('sma20'))} · SMA50 {num(ind.get('sma50'))} · "
        f"SMA200 {num(ind.get('sma200'))}",
        f"  RSI14 {num(ind.get('rsi14'), 1)} · MACD {num(ind.get('macd'), 1)} "
        f"(sig {num(ind.get('macd_signal'), 1)})",
        f"  BB {num(ind.get('bb_lower'))} – {num(ind.get('bb_upper'))} · "
        f"ATR {num(ind.get('atr14'), 1)}",
    ]
    if rating_:
        lines += ["", f"<b>Rating</b> {RATING_EMOJI[rating_]} {rating_} ({score:+d})"]
    if rules:
        lines += ["<b>Sinyal aktif</b>", *(f"  • {escape(r)}" for r in rules)]
    lines += ["", f"<i>{DISCLAIMER}</i>"]
    return _clip("\n".join(lines))


def _clip(text: str, limit: int = TELEGRAM_MAX) -> str:
    """Potong di batas baris supaya tag HTML tidak terbelah (tiap baris self-contained)."""
    if len(text) <= limit:
        return text
    suffix = "\n…(terpotong)"
    cut = text.rfind("\n", 0, limit - len(suffix))
    if cut <= 0:
        cut = limit - len(suffix)
    return text[:cut] + suffix


def clip_plain(text: str, limit: int = TELEGRAM_MAX) -> str:
    """Untuk teks tanpa HTML (jawaban LLM)."""
    suffix = "\n…(terpotong)"
    return text if len(text) <= limit else text[: limit - len(suffix)] + suffix
