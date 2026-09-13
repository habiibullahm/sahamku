"""Daftar ticker & kalender bursa."""

from __future__ import annotations

import sqlite3
from datetime import date

from sahamku.config import settings

IHSG = "^JKSE"

# LQ45 (perlu update tiap rebalancing Feb/Agu — cek pengumuman BEI)
LQ45 = [
    "ACES", "ADRO", "AKRA", "AMMN", "AMRT", "ANTM", "ARTO", "ASII", "BBCA", "BBNI",
    "BBRI", "BBTN", "BMRI", "BRIS", "BRPT", "BUKA", "CPIN", "CTRA", "ESSA", "EXCL",
    "GOTO", "ICBP", "INCO", "INDF", "INKP", "ISAT", "ITMG", "JSMR", "KLBF", "MAPI",
    "MBMA", "MDKA", "MEDC", "MTEL", "PGAS", "PGEO", "PTBA", "SIDO", "SMGR", "SMRA",
    "TLKM", "TOWR", "UNTR", "UNVR", "MAPA",
]

# Tambahan konstituen IDX80 di luar LQ45 (best-effort; verifikasi dengan pengumuman BEI)
IDX80_EXTRA = [
    "AADI", "AALI", "ADMR", "AVIA", "BFIN", "BREN", "BRMS", "BSDE", "BTPS", "CMRY",
    "CUAN", "DSSA", "ELSA", "ENRG", "ERAA", "GGRM", "HEAL", "HRUM", "INTP", "JPFA",
    "LSIP", "MIKA", "MNCN", "MYOR", "NCKL", "PANI", "PNLF", "PTPP", "PWON", "SCMA",
    "SRTG", "SSIA", "TINS", "TKIM", "TPIA",
]

# Compatibility fallback for callers without a DB connection. Liquid mode falls back to IDX80
# until a broad securities master has been imported.
IDX80 = LQ45 + IDX80_EXTRA
STOCKS: list[str] = LQ45 if settings.universe.lower() == "lq45" else IDX80


# Alias nama perusahaan (lowercase-insensitive) untuk deteksi berita
NAME_ALIASES: dict[str, list[str]] = {
    "ACES": ["Ace Hardware", "Aspirasi Hidup"], "ADRO": ["Adaro", "Alamtri"],
    "AKRA": ["AKR Corporindo"], "AMMN": ["Amman Mineral"], "AMRT": ["Alfamart", "Sumber Alfaria"],
    "ANTM": ["Antam", "Aneka Tambang"], "ARTO": ["Bank Jago"], "ASII": ["Astra International"],
    "BBCA": ["BCA", "Bank Central Asia"], "BBNI": ["BNI", "Bank Negara Indonesia"],
    "BBRI": ["BRI", "Bank Rakyat Indonesia"], "BBTN": ["BTN", "Bank Tabungan Negara"],
    "BMRI": ["Bank Mandiri"], "BRIS": ["BSI", "Bank Syariah Indonesia"],
    "BRPT": ["Barito Pacific"], "BUKA": ["Bukalapak"], "CPIN": ["Charoen Pokphand"],
    "CTRA": ["Ciputra"], "ESSA": ["Essa Industries", "Surya Esa"], "EXCL": ["XL Axiata", "XLSmart"],
    "GOTO": ["GoTo", "Gojek", "Tokopedia"], "ICBP": ["Indofood CBP"], "INCO": ["Vale Indonesia"],
    "INDF": ["Indofood Sukses"], "INKP": ["Indah Kiat"], "ISAT": ["Indosat"],
    "ITMG": ["Indo Tambangraya"], "JSMR": ["Jasa Marga"], "KLBF": ["Kalbe Farma"],
    "MAPI": ["Mitra Adiperkasa"], "MAPA": ["MAP Aktif"], "MBMA": ["Merdeka Battery"],
    "MDKA": ["Merdeka Copper"], "MEDC": ["Medco Energi"], "MTEL": ["Mitratel", "Dayamitra"],
    "PGAS": ["PGN", "Perusahaan Gas Negara"], "PGEO": ["Pertamina Geothermal"],
    "PTBA": ["Bukit Asam"], "SIDO": ["Sido Muncul"], "SMGR": ["Semen Indonesia"],
    "SMRA": ["Summarecon"], "TLKM": ["Telkom Indonesia", "Telkom"], "TOWR": ["Sarana Menara"],
    "UNTR": ["United Tractors"], "UNVR": ["Unilever Indonesia"],
    "AALI": ["Astra Agro"], "BSDE": ["Bumi Serpong", "BSD"], "BTPS": ["BTPN Syariah"],
    "CMRY": ["Cimory"], "ELSA": ["Elnusa"], "ERAA": ["Erajaya"], "GGRM": ["Gudang Garam"],
    "HRUM": ["Harum Energy"], "INTP": ["Indocement"], "JPFA": ["Japfa"], "MIKA": ["Mitra Keluarga"],
    "MNCN": ["MNC"], "MYOR": ["Mayora"], "NCKL": ["Trimegah Bangun", "Harita Nickel"],
    "PANI": ["Pantai Indah Kapuk", "PIK 2"], "PTPP": ["PT PP", "PP Persero"], "PWON": ["Pakuwon"],
    "SCMA": ["Surya Citra"], "SRTG": ["Saratoga"], "TINS": ["Timah"], "TKIM": ["Tjiwi Kimia"],
    "TPIA": ["Chandra Asri"], "BREN": ["Barito Renewables"], "CUAN": ["Petrindo"],
    "DSSA": ["Dian Swastatika"], "AVIA": ["Avian"], "BFIN": ["BFI Finance"], "HEAL": ["Hermina"],
    "LSIP": ["London Sumatra"], "PNLF": ["Panin Financial"], "SSIA": ["Surya Semesta"],
    "ADMR": ["Adaro Minerals"], "AADI": ["Adaro Andalan"], "BRMS": ["Bumi Resources Minerals"],
}


def to_yf(code: str) -> str:
    """BBCA -> BBCA.JK ; indeks (^...) dibiarkan."""
    return code if code.startswith("^") else f"{code.upper()}.JK"


def from_yf(ticker: str) -> str:
    return ticker[:-3] if ticker.endswith(".JK") else ticker


def active_codes(conn: sqlite3.Connection | None = None) -> list[str]:
    """Return codes for configured universe; liquid uses the imported securities master."""
    mode = settings.universe.lower()
    if mode == "lq45":
        return list(LQ45)
    if mode == "idx80":
        return list(IDX80)
    if conn is not None:
        rows = conn.execute(
            "SELECT code FROM securities WHERE lower(status)='active' "
            "AND lower(instrument_type) IN ('stock','common stock','saham') ORDER BY code"
        ).fetchall()
        if rows:
            return [r["code"] for r in rows]
    return list(IDX80)


def active_tickers(conn: sqlite3.Connection | None = None) -> list[str]:
    return [to_yf(c) for c in active_codes(conn)]


def scan_tickers(conn: sqlite3.Connection, date_str: str | None = None) -> list[str]:
    """Eligible liquid tickers after scoring, or the selected static universe."""
    if settings.universe.lower() == "liquid" and date_str:
        rows = conn.execute(
            "SELECT ticker FROM universe_eligibility WHERE date=? AND eligible=1 ORDER BY ticker",
            (date_str,),
        ).fetchall()
        if rows or conn.execute(
            "SELECT 1 FROM universe_eligibility WHERE date=? LIMIT 1", (date_str,)
        ).fetchone():
            return [r["ticker"] for r in rows]
    return active_tickers(conn)


def universe_label(conn: sqlite3.Connection | None = None) -> str:
    mode = settings.universe.lower()
    if mode == "lq45":
        return "LQ45"
    if mode == "idx80":
        return "IDX80"
    if conn is not None and conn.execute(
        "SELECT 1 FROM securities WHERE lower(status)='active' "
        "AND lower(instrument_type) IN ('stock','common stock','saham') LIMIT 1"
    ).fetchone():
        return "universe liquid"
    return "IDX80 (fallback; master IDX belum diimpor)"


def is_known_code(code: str, conn: sqlite3.Connection | None = None) -> bool:
    return code.upper() in active_codes(conn)


STOCK_TICKERS = [to_yf(c) for c in STOCKS]
ALL_EOD_TICKERS = [IHSG, *STOCK_TICKERS]


def all_eod_tickers(conn: sqlite3.Connection | None = None) -> list[str]:
    return [IHSG, *active_tickers(conn)]

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
