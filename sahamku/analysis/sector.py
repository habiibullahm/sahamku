"""/sector — ringkasan per sektor: rata-rata % hari ini, bullish/bearish, terbaik/terburuk."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from sahamku import screener

# Pemetaan sektor (IDX-IC, disederhanakan). Best-effort; ticker tanpa pemetaan → "Lainnya".
SECTORS: dict[str, list[str]] = {
    "Perbankan": ["BBCA", "BBRI", "BMRI", "BBNI", "BBTN", "BRIS", "ARTO", "BTPS", "BFIN", "PNLF"],
    "Telko & Infra": ["TLKM", "ISAT", "EXCL", "TOWR", "MTEL", "JSMR", "PTPP", "SSIA"],
    "Energi": ["ADRO", "PTBA", "ITMG", "MEDC", "PGAS", "AKRA", "HRUM", "ELSA", "ENRG",
               "ADMR", "AADI", "DSSA", "CUAN", "PGEO", "BREN"],
    "Tambang & Logam": ["ANTM", "MDKA", "INCO", "AMMN", "MBMA", "NCKL", "TINS", "BRMS"],
    "Konsumer": ["ICBP", "INDF", "UNVR", "MYOR", "CPIN", "JPFA", "SIDO", "KLBF", "GGRM",
                 "CMRY", "AMRT", "ACES", "MAPI", "MAPA", "ERAA", "HEAL", "MIKA"],
    "Properti": ["CTRA", "SMRA", "BSDE", "PWON", "PANI"],
    "Industri & Material": ["ASII", "UNTR", "SMGR", "INTP", "BRPT", "TPIA", "ESSA", "INKP",
                            "TKIM", "AVIA"],
    "Teknologi & Media": ["GOTO", "BUKA", "MNCN", "SCMA", "SRTG"],
    "Agri": ["AALI", "LSIP"],
}


@dataclass
class SectorRow:
    name: str
    n: int
    avg_chg: float
    bullish: int
    bearish: int
    best: tuple[str, float] | None
    worst: tuple[str, float] | None
    members: list[str] = field(default_factory=list)


def build(conn: sqlite3.Connection) -> tuple[str, list[SectorRow]]:
    df = screener.snapshot(conn)
    if df.empty:
        return "", []
    by = {r.code: r for r in df.itertuples()}
    mapped = {c for codes in SECTORS.values() for c in codes}
    sectors = dict(SECTORS)
    rest = [c for c in by if c not in mapped]
    if rest:
        sectors["Lainnya"] = rest
    out: list[SectorRow] = []
    for name, codes in sectors.items():
        rows = [by[c] for c in codes
                if c in by and by[c].chg is not None and by[c].chg == by[c].chg]
        if not rows:
            continue
        chgs = sorted(((r.code, float(r.chg)) for r in rows), key=lambda x: x[1])
        out.append(SectorRow(
            name=name, n=len(rows),
            avg_chg=sum(c for _, c in chgs) / len(chgs),
            bullish=sum(1 for r in rows if r.rating == "bullish"),
            bearish=sum(1 for r in rows if r.rating == "bearish"),
            best=chgs[-1], worst=chgs[0], members=[r.code for r in rows],
        ))
    out.sort(key=lambda s: s.avg_chg, reverse=True)
    from sahamku import db
    return db.latest_date(conn) or "", out


def sector_of(code: str) -> str | None:
    for name, codes in SECTORS.items():
        if code in codes:
            return name
    return None
