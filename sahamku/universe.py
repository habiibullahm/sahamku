"""Daftar ticker & kalender bursa."""

from __future__ import annotations

from datetime import date

IHSG = "^JKSE"

# LQ45 (perlu update tiap rebalancing Feb/Agu — cek pengumuman BEI)
LQ45 = [
    "ACES", "ADRO", "AKRA", "AMMN", "AMRT", "ANTM", "ARTO", "ASII", "BBCA", "BBNI",
    "BBRI", "BBTN", "BMRI", "BRIS", "BRPT", "BUKA", "CPIN", "CTRA", "ESSA", "EXCL",
    "GOTO", "ICBP", "INCO", "INDF", "INKP", "ISAT", "ITMG", "JSMR", "KLBF", "MAPI",
    "MBMA", "MDKA", "MEDC", "MTEL", "PGAS", "PGEO", "PTBA", "SIDO", "SMGR", "SMRA",
    "TLKM", "TOWR", "UNTR", "UNVR", "MAPA",
]


def to_yf(code: str) -> str:
    """BBCA -> BBCA.JK ; indeks (^...) dibiarkan."""
    return code if code.startswith("^") else f"{code.upper()}.JK"


def from_yf(ticker: str) -> str:
    return ticker[:-3] if ticker.endswith(".JK") else ticker


def is_known_code(code: str) -> bool:
    return code.upper() in LQ45


STOCK_TICKERS = [to_yf(c) for c in LQ45]
ALL_EOD_TICKERS = [IHSG, *STOCK_TICKERS]

# Aset global untuk analisis pre-market
GLOBAL_TICKERS: dict[str, str] = {
    "^DJI": "Dow Jones",
    "^GSPC": "S&P 500",
    "^IXIC": "Nasdaq",
    "ES=F": "S&P Futures",
    "^N225": "Nikkei 225",
    "^HSI": "Hang Seng",
    "^KS11": "KOSPI",
    "CL=F": "Minyak WTI",
    "GC=F": "Emas",
    "IDR=X": "USD/IDR",
    "^TNX": "UST 10Y",
}

# Libur bursa IDX 2026 (termasuk cuti bersama). Verifikasi dengan SK BEI & update tiap tahun.
IDX_HOLIDAYS: set[date] = {
    date(2026, 1, 1),
    date(2026, 1, 16),
    date(2026, 2, 17),
    date(2026, 3, 19),
    date(2026, 3, 20),
    date(2026, 3, 23),
    date(2026, 3, 24),
    date(2026, 4, 3),
    date(2026, 5, 1),
    date(2026, 5, 14),
    date(2026, 5, 27),
    date(2026, 6, 1),
    date(2026, 6, 16),
    date(2026, 8, 17),
    date(2026, 8, 25),
    date(2026, 12, 24),
    date(2026, 12, 25),
    date(2026, 12, 31),
}


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in IDX_HOLIDAYS
