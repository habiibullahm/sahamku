"""Format laporan menjadi teks Telegram (parse_mode HTML)."""

from __future__ import annotations

from datetime import date
from html import escape

from sahamku.analysis.aftermarket import AfterMarketReport, Mover, TickerSignals
from sahamku.analysis.compare import Row as CompareRow
from sahamku.analysis.growth import GrowthCandidate
from sahamku.analysis.midday import MiddayReport
from sahamku.analysis.premarket import PreMarketReport
from sahamku.analysis.sector import SectorRow
from sahamku.analysis.weekly import WeeklyReport
from sahamku.config import DISCLAIMER, settings
from sahamku.news import SENT_EMOJI, Headline
from sahamku.screener import MAX_ROWS, Query, describe
from sahamku.signals.scoring import RATING_EMOJI

TELEGRAM_MAX = 4096


def cta_line() -> str:
    return f"🤖 Detail saham, chart &amp; tanya AI → @{settings.bot_username}"


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


def _headline_line(h: Headline) -> str:
    tick = f" <code>{'/'.join(h.tickers)}</code>" if h.tickers else ""
    return (f"  {SENT_EMOJI.get(h.sentiment, '⚪')}{tick} "
            f"<a href=\"{escape(h.link, quote=True)}\">{escape(h.title)}</a> — {escape(h.source)}")


def news_list(code: str | None, items: list[Headline], hours: int) -> str:
    title = f"📰 <b>Berita {code}</b>" if code else "📰 <b>Berita pasar</b>"
    if not items:
        return f"{title}\nBelum ada berita {hours} jam terakhir."
    return "\n".join([f"{title} ({hours} jam terakhir)", *(_headline_line(h) for h in items)])


def screener_result(date: str, q: Query, rows) -> str:
    head = f"🔎 <b>Screener</b> <code>{escape(describe(q))}</code> — {date}"
    if rows.empty:
        return f"{head}\nTidak ada saham yang cocok."
    more = f" (ditampilkan {MAX_ROWS})" if len(rows) > MAX_ROWS else ""
    lines = [head, f"{len(rows)} saham{more}"]
    for r in rows.head(MAX_ROWS).itertuples():
        rsi = f"RSI {r.rsi:.0f}" if r.rsi is not None and r.rsi == r.rsi else "RSI n/a"
        volx = (f" · vol {r.vol_x:.1f}x"
                if r.vol_x and r.vol_x == r.vol_x and r.vol_x >= 1.5 else "")
        lines.append(f"  {RATING_EMOJI[r.rating]} <code>{r.code}</code> {num(r.close)} "
                     f"{pct(r.chg)} · {rsi} ({r.score:+d}){volx}")
    lines += ["", "Detail: /stock KODE", f"<i>{DISCLAIMER}</i>"]
    return _clip("\n".join(lines))


PREF_LABELS = {
    "premarket": "🌅 Pre-market 08:15", "midday": "🕛 Tengah hari 12:15",
    "aftermarket": "📊 After-market 17:00", "weekly": "🗓 Rekap mingguan",
    "alerts": "🔔 Alert level",
}


def midday(r: MiddayReport, cta: bool = False) -> str:
    parts = [
        f"🕛 <b>Sahamku — Tengah Hari {r.date}</b> <i>(data delayed, {r.ts} WIB)</i>",
        "",
        f"<b>IHSG</b> {num(r.ihsg_last, 2)}  {pct(r.ihsg_pct)} · "
        f"range {num(r.ihsg_low, 0)}–{num(r.ihsg_high, 0)}",
        f"▲{r.advancers} ▼{r.decliners}",
        "",
        "🚀 <b>Top Gainers Sesi 1</b>",
        *(_mover_line(m) for m in r.gainers),
        "",
        "📉 <b>Top Losers Sesi 1</b>",
        *(_mover_line(m) for m in r.losers),
    ]
    if r.watchlist:
        parts += ["", "👀 <b>Watchlist</b>"]
        for code, m in r.watchlist.items():
            parts.append(f"  <code>{code}</code> {num(m.close)} {pct(m.pct)}" if m
                         else f"  <code>{code}</code> — belum ada data")
    if cta:
        parts += ["", cta_line()]
    parts += ["", f"<i>{DISCLAIMER}</i>"]
    return _clip("\n".join(parts))


def compare(rows: list[CompareRow]) -> str:
    def yn(v: bool | None) -> str:
        return "—" if v is None else ("✅" if v else "❌")

    lines = ["⚖️ <b>Perbandingan</b>", ""]
    for r in rows:
        rets = " · ".join(f"{k} {pct(v)}" for k, v in r.ret.items())
        lines += [
            f"{RATING_EMOJI[r.rating]} <b>{r.code}</b> {num(r.close)} ({r.score:+d})",
            f"  {rets}",
            f"  RSI {num(r.rsi, 0)} · >SMA50 {yn(r.above_sma50)} · >SMA200 {yn(r.above_sma200)}",
        ]
    lines += ["", f"<i>{DISCLAIMER}</i>"]
    return _clip("\n".join(lines))


def sector(date: str, rows: list[SectorRow]) -> str:
    lines = [f"🏭 <b>Sektor</b> — {date}", ""]
    for s in rows:
        best = f"{s.best[0]} {s.best[1]:+.1f}%" if s.best else "—"
        worst = f"{s.worst[0]} {s.worst[1]:+.1f}%" if s.worst else "—"
        lines.append(f"<b>{escape(s.name)}</b> {pct(s.avg_chg)} · {s.n} saham · "
                     f"🟢{s.bullish} 🔴{s.bearish}")
        lines.append(f"  ↑ {best} · ↓ {worst}")
    lines += ["", "Detail: /screener atau /stock KODE", f"<i>{DISCLAIMER}</i>"]
    return _clip("\n".join(lines))


def settings_text(prefs: dict[str, bool], subscribed: bool) -> str:
    lines = ["⚙️ <b>Pengaturan laporan</b>", ""]
    if not subscribed:
        lines.append("🔕 Semua laporan otomatis nonaktif (/resume untuk mengaktifkan).")
        lines.append("")
    for k, label in PREF_LABELS.items():
        lines.append(f"{'✅' if prefs[k] else '⬜'} {label}")
    lines += ["", "Ketuk tombol untuk mengubah. Kuota /ask dan watchlist diatur terpisah."]
    return "\n".join(lines)


def admin_stats_text(st: dict, jobs) -> str:
    lines = [
        "🛠 <b>Admin — statistik</b>",
        f"User {st['users']} · subscribed {st['subscribed']} · "
        f"punya watchlist {st['with_watchlist']} ({st['watch_rows']} entri)",
        f"Alert aktif {st['alerts_active']} · /ask hari ini {st['ask_today']}",
        f"Berita {st['news_total']} (belum dianalisis {st['news_pending']})",
        f"OHLCV s/d {st['ohlcv_date']} · {st['tickers']} ticker",
        "",
        "<b>Job terakhir</b>",
    ]
    for j in jobs:
        icon = "✅" if j["status"] == "ok" else "⏳" if j["status"] == "running" else "❌"
        when = (j["started_at"] or "")[5:16].replace("T", " ")
        lines.append(f"  {icon} {when} <code>{escape(j['job'])}</code> "
                     f"{escape((j['detail'] or '')[:60])}")
    return _clip("\n".join(lines))


def _narrative_block(text: str | None) -> list[str]:
    return ["", f"💬 <i>{escape(text)}</i>"] if text else []


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


def _growth_line(g: GrowthCandidate, detailed: bool = False) -> str:
    why = ", ".join(escape(x) for x in g.explanations) or "skor teknikal"
    risk = escape(g.risk_flags[0]) if g.risk_flags else "tanpa flag utama"
    if detailed:
        rel = f"{g.rel_60:+.1f}%" if g.rel_60 is not None else "n/a"
        value = (f"Rp{g.median_value_20 / 1e9:.1f} miliar" if g.median_value_20 is not None
                 else "n/a")
        return (f"  <b>{g.code}</b> {g.total:.1f} · L{g.liquidity:.0f} M{g.momentum:.0f} "
                f"T{g.trend:.0f} B{g.breakout:.0f} AR{g.accumulation_risk:.0f}\n"
                f"    rel60 {rel} · median20 {value} · {why} · risiko: {risk}")
    return f"  <b>{g.code}</b> {g.total:.1f} — {why} · risiko: {risk}"


def aftermarket(r: AfterMarketReport, cta: bool = False,
                narrative: str | None = None) -> str:
    volume_line = f" · Vol {vol(r.ihsg_volume)}" if r.ihsg_volume and r.ihsg_volume > 0 else ""
    signal_preview = []
    if r.bullish:
        signal_preview.append(_signal_block(r.bullish[:1]))
    if r.bearish:
        signal_preview.append(_signal_block(r.bearish[:1]))
    parts = [
        f"📊 <b>Sahamku — After Market {r.date}</b>",
        "",
        "🇮🇩 <b>Market Overview</b>",
        f"IHSG {num(r.ihsg_close, 2)} {pct(r.ihsg_pct)}{volume_line}",
        f"RSI {num(r.ihsg_rsi, 1)} · {escape(r.ihsg_trend)}",
        f"S {num(r.support)} · R {num(r.resistance)}",
        f"Breadth {escape(r.universe)} ({r.eligible_count} saham): "
        f"▲{r.advancers} ▼{r.decliners} •{r.unchanged}",
        f"Cakupan data {r.coverage_pct:.0f}%" + ("" if r.data_complete else " ⚠️ parsial"),
        *_narrative_block(narrative),
        "",
        "⚡ <b>Liquid Momentum</b> (kekuatan relatif, bukan sinyal beli)",
        *([_growth_line(g) for g in r.liquid_momentum] or ["  —"]),
        "",
        "🌱 <b>Potential Growth</b> (skor teknikal 0–100)",
        *([_growth_line(g) for g in r.growth_candidates]
          or ["  Belum ada yang lolos skor minimum"]),
        "",
        "🚀 <b>Top Gainers</b>", *(_mover_line(m) for m in r.gainers[:3]),
        "📉 <b>Top Losers</b>", *(_mover_line(m) for m in r.losers[:3]),
        "",
        f"<b>Sinyal teknikal</b>: 🟢{len(r.bullish)} bullish · 🔴{len(r.bearish)} bearish",
        *signal_preview,
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
        shown = ", ".join(r.missing[:5])
        more = f" +{len(r.missing) - 5}" if len(r.missing) > 5 else ""
        parts += ["", f"⚠️ Data belum lengkap: {shown}{more}"]
    if r.watch_tomorrow:
        parts += ["", "👁 <b>Watch Tomorrow</b>",
                  *(f"  • {escape(x)}" for x in r.watch_tomorrow)]
    if cta:
        parts += ["", cta_line()]
    parts += ["", f"<i>{DISCLAIMER}</i>"]
    return _clip("\n".join(parts))


def growth_report(date_str: str, items: list[GrowthCandidate], universe: str) -> str:
    minimum = settings.potential_growth_min_score
    lines = [f"🌱 <b>Potential Growth — {date_str}</b>",
             f"Universe: {escape(universe)} · skor minimum {minimum:.0f}",
             "Skor: L likuiditas · M momentum · T tren · B breakout · AR akumulasi/risiko", ""]
    lines += [_growth_line(g, detailed=True) for g in items] or ["Belum ada saham yang lolos."]
    lines += ["", "Skor adalah hasil penyaringan teknikal, bukan prediksi multibagger.",
              f"<i>{DISCLAIMER}</i>"]
    return _clip("\n".join(lines))


def premarket(r: PreMarketReport, cta: bool = False,
              narrative: str | None = None) -> str:
    monday = date.fromisoformat(r.date).weekday() == 0
    close_label = "Penutupan Jumat" if monday else "Penutupan terakhir"
    parts = [
        f"🌅 <b>Sahamku — Pre-Market {r.date}</b>",
        "",
        f"Sentimen pembukaan: <b>{r.sentiment_label}</b> (skor {r.sentiment_score:+d})",
        *([" · ".join(f"{escape(k)}: {escape(v)}" for k, v in r.sentiment_components.items())]
          if r.sentiment_components else []),
        *_narrative_block(narrative),
        "",
        "🌍 <b>Global semalam</b>",
        *(f"  {escape(name)}: {num(c, 2)} {pct(p)}"
          + (f" · {escape(r.global_dates[name])}" if name in r.global_dates else "")
          for name, c, p in r.global_rows),
        "",
        "🇮🇩 <b>IHSG</b>",
        f"  {close_label} {num(r.ihsg_close, 2)} {pct(r.ihsg_pct)}"
        + (f" · data {r.ihsg_source_date}" if r.ihsg_source_date else ""),
        f"  Support {num(r.support, 0)} · Resistance {num(r.resistance, 0)} (20 hari)",
        *([f"  S/R swing {escape(r.sr_swing)}"] if r.sr_swing else []),
        f"  RSI {num(r.ihsg_rsi, 1)} · {escape(r.ihsg_trend)}",
    ]
    if r.notes:
        parts += ["", "📝 <b>Catatan</b>", *(f"  • {escape(n)}" for n in r.notes)]
    if r.bullish_yesterday:
        parts += ["", "🟢 <b>Bullish dari scan kemarin</b>: " + ", ".join(r.bullish_yesterday)]
    if r.bearish_yesterday:
        parts += ["🔴 <b>Bearish dari scan kemarin</b>: " + ", ".join(r.bearish_yesterday)]
    if r.headlines:
        parts += ["", "📰 <b>Berita</b>", *(_headline_line(h) for h in r.headlines)]
    if r.news_sentiment:
        items = sorted(r.news_sentiment.items(), key=lambda kv: -(kv[1][0] + kv[1][1]))[:8]
        parts += ["  Sentimen emiten: " + " · ".join(
            f"{c} 🟢{p}🔴{n}" for c, (p, n) in items)]
    if r.watchlist:
        parts += ["", "👀 <b>Watchlist</b>"]
        for code, info in r.watchlist.items():
            parts.append(f"  <code>{code}</code> {escape(info)}")
    if cta:
        parts += ["", cta_line()]
    parts += ["", f"<i>{DISCLAIMER}</i>"]
    return _clip("\n".join(parts))


def weekly(r: WeeklyReport, cta: bool = False, narrative: str | None = None) -> str:
    def rate(v: float | None, n: int) -> str:
        return "—" if v is None else f"{v:.0f}% ({n} sinyal)"

    parts = [
        f"🗓 <b>Sahamku — Rekap Minggu {r.week_start} s/d {r.week_end}</b>",
        "",
        f"<b>IHSG</b> {num(r.ihsg_end, 2)}  {pct(r.ihsg_pct)} dalam {r.days} hari bursa",
        f"Range minggu ini {num(r.ihsg_low, 0)} – {num(r.ihsg_high, 0)}",
        *_narrative_block(narrative),
        "",
        "🚀 <b>Top Gainers Mingguan</b>",
        *(_mover_line(m) for m in r.gainers),
        "",
        "📉 <b>Top Losers Mingguan</b>",
        *(_mover_line(m) for m in r.losers),
        "",
        "🎯 <b>Akurasi Sinyal Minggu Ini</b> (return s/d close Jumat)",
        f"  🟢 Bullish tepat: {rate(r.bull_hit_rate, len(r.bull_hits))}",
        f"  🔴 Bearish tepat: {rate(r.bear_hit_rate, len(r.bear_hits))}",
        f"  Total sinyal: {r.n_bullish} bullish · {r.n_bearish} bearish",
    ]
    if cta:
        parts += ["", cta_line()]
    parts += ["", f"<i>{DISCLAIMER}</i>"]
    return _clip("\n".join(parts))


def ihsg_snapshot(date: str, close: float, pct_: float | None, volume: float,
                  ind: dict[str, float | None], support: float, resistance: float,
                  trend: str, sr: str | None = None) -> str:
    lines = [
        f"🇮🇩 <b>IHSG</b> — {date}",
        f"Close {num(close, 2)}  {pct(pct_)}"
        + (f" · Vol {vol(volume)}" if volume and volume > 0 else ""),
        "",
        f"<b>Support</b> {num(support)} · <b>Resistance</b> {num(resistance)} (20 hari)",
        *([f"<b>S/R swing</b> {escape(sr)}"] if sr else []),
        f"Tren: {escape(trend)}",
        "",
        "<b>Indikator</b>",
        f"  SMA20 {num(ind.get('sma20'))} · SMA50 {num(ind.get('sma50'))} · "
        f"SMA200 {num(ind.get('sma200'))}",
        f"  RSI14 {num(ind.get('rsi14'), 1)} · MACD {num(ind.get('macd'), 1)} "
        f"(sig {num(ind.get('macd_signal'), 1)})",
        "",
        f"<i>{DISCLAIMER}</i>",
    ]
    return _clip("\n".join(lines))


def alert_triggered(code: str, label: str, actual: float, metric: str, date: str) -> str:
    val = f"{actual:,.0f}" if metric == "close" else f"{actual:.1f}"
    return (f"🔔 <b>Alert {code}</b> ({date})\n{escape(label)} — sekarang <b>{val}</b>\n"
            f"Lihat detail: /stock {code}")


def stock_snapshot(code: str, date: str, close: float, pct_: float | None, volume: float,
                   ind: dict[str, float | None], rating_: str | None, score: int | None,
                   rules: list[str], headlines: list[Headline] | None = None,
                   sr: str | None = None) -> str:
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
    if sr:
        lines += [f"  <b>S/R swing</b> {escape(sr)}"]
    if rating_:
        lines += ["", f"<b>Rating</b> {RATING_EMOJI[rating_]} {rating_} ({score:+d})"]
    if rules:
        lines += ["<b>Sinyal aktif</b>", *(f"  • {escape(r)}" for r in rules)]
    if headlines:
        lines += ["", "📰 <b>Berita terkait</b>", *(_headline_line(h) for h in headlines)]
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
