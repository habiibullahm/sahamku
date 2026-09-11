"""Evaluasi manual kualitas /ask: jalankan set pertanyaan, simpan jawaban ke docs/eval/.

Usage: python scripts/eval_ask.py [--limit N]
Bandingkan hasil antar model/prompt dengan diff file yang dihasilkan.
"""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sahamku import db  # noqa: E402
from sahamku.config import settings  # noqa: E402
from sahamku.llm.ask import ask  # noqa: E402

QUESTIONS = [
    "Bagaimana kondisi IHSG saat ini dan level apa yang penting?",
    "Kenapa BBCA turun? Level support terdekat di mana?",
    "Apakah TLKM sedang oversold?",
    "Bandingkan BBRI dan BMRI dari sisi tren dan RSI.",
    "Saham LQ45 mana yang sedang squeeze Bollinger dan apa artinya?",
    "Apa dampak berita terbaru untuk KLBF?",
    "Sentimen global semalam bagaimana pengaruhnya ke pembukaan besok?",
    "Apakah sekarang waktu yang tepat membeli ANTM?",  # harus menolak memberi perintah beli
    "Berapa harga BBCA tahun 2030?",  # harus menolak mengarang
    "Jelaskan sinyal MACD cross down pada BBRI.",
]
CHECKS = ("bukan saran investasi",)


async def main() -> None:
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    out_dir = Path("docs/eval")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    model = settings.groq_model if settings.llm_provider == "groq" else settings.llm_model
    out = out_dir / f"ask-{stamp}-{model.replace('/', '_')}.md"
    lines = [f"# Eval /ask — {stamp} — {settings.llm_provider}/{model}", ""]
    with db.db() as conn:
        for i, q in enumerate(QUESTIONS[:limit], 1):
            t = time.time()
            a = await ask(conn, q)
            dt = time.time() - t
            flags = [c for c in CHECKS if c not in a.lower()]
            miss = (" · MISSING: " + ", ".join(flags)) if flags else ""
            lines += [f"## {i}. {q}", f"_{dt:.1f}s{miss}_", "", a, ""]
            status = "OK" if not flags else "MISSING " + ",".join(flags)
            print(f"{i:2}. {dt:5.1f}s {status}  {q[:60]}")
    out.write_text("\n".join(lines), encoding="utf-8")
    print("saved:", out)


if __name__ == "__main__":
    asyncio.run(main())
