# Sahamku

Bot Telegram (`@sahamku_id_bot`) untuk daily scan saham IHSG (LQ45): laporan **pre-market** dan
**after-market** otomatis, sinyal teknikal rule-based, chart, watchlist, dan `/ask` berbasis Claude.

> ⚠️ Bukan saran investasi. Semua sinyal bersifat analitis dari data historis.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"
copy .env.example .env          # lalu isi TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, ADMIN_CHAT_ID
python scripts/backfill.py      # tarik 3 tahun histori + hitung indikator & sinyal (±1 menit)
python -m sahamku.bot.main      # jalankan bot (long polling + scheduler)
```

`ADMIN_CHAT_ID` = chat_id Telegram Anda (kirim `/start` ke bot, lihat log, atau pakai @userinfobot).

## Command

| Command | Fungsi |
|---|---|
| `/scan` | Laporan after-market dari data terakhir |
| `/stock BBCA` | Snapshot harga, indikator, rating, sinyal + chart 60 hari |
| `/watch BBCA` / `/unwatch BBCA` / `/watchlist` | Watchlist per chat; ikut dilaporkan di pre/after-market |
| `/ask kenapa BBCA turun?` | Tanya Claude dengan konteks harga, indikator, sinyal, dan sentimen global |

## Jadwal (WIB, hari bursa; libur di `sahamku/universe.py`)

| Jam | Job |
|---|---|
| 07:30 | Ingest aset global (Wall Street, Asia, minyak, emas, USD/IDR, UST10Y) |
| 08:15 | Kirim laporan pre-market (sentimen global, level S/R IHSG, sinyal kemarin, watchlist) |
| 16:30 | Ingest EOD LQ45+IHSG → validasi → indikator → sinyal. Retry tiap 15 menit s/d 18:00 jika belum lengkap |
| 17:00 | Kirim laporan after-market (IHSG, top movers, sinyal bullish/bearish, squeeze, watchlist) |
| Sabtu 09:00 | Backtest mingguan → ringkasan ke admin |

Untuk uji cepat, set `SCHEDULE_OVERRIDE_AFTERMARKET=HH:MM` / `SCHEDULE_OVERRIDE_PREMARKET=HH:MM`
di `.env` (ingest EOD otomatis dijalankan 2 menit sebelum jam kirim).

## Job manual

```bash
python scripts/run_job.py eod          # ingest 10 hari terakhir + validasi
python scripts/run_job.py global
python scripts/run_job.py compute      # hitung ulang indikator & sinyal
python scripts/run_job.py aftermarket  # print laporan
python scripts/run_job.py premarket
python scripts/run_job.py chart BBCA
python -m sahamku.backtest.run         # tabel win rate per rule
```

## Sinyal

Rule di `sahamku/signals/rules.py`, bobot di `scoring.py`, threshold di `config.py`:
golden/death cross (SMA50/200), RSI oversold/overbought cross, breakout/breakdown 20D + volume
≥1.5× rata-rata, MACD cross, Bollinger squeeze (informasi), posisi vs SMA200.
Skor ≥ +2 → bullish, ≤ −2 → bearish.

### Hasil backtest awal (LQ45, 3 tahun s/d 2026-09-11, tanpa biaya transaksi)

| Rule | Arah | n | Win 10D | Avg 10D |
|---|---|---|---|---|
| RSI overbought | bear | 366 | 58.7% | +1.25% |
| Death cross | bear | 90 | 53.3% | +1.16% |
| RSI oversold | bull | 465 | 53.3% | +1.41% |
| MACD cross down | bear | 1334 | 50.5% | +0.09% |
| Breakdown low 20D + vol | bear | 738 | 44.7% | −0.69% |
| Breakout high 20D + vol | bull | 772 | 42.6% | −0.31% |
| MACD cross up | bull | 1330 | 41.2% | −0.65% |
| Golden cross | bull | 77 | 37.7% | −1.40% |

Return dihitung searah sinyal. Periode ini IHSG cenderung turun, sehingga rule mean-reversion
(RSI) lebih baik daripada momentum. Gunakan tabel ini untuk menyesuaikan bobot/threshold.

## Struktur

```
sahamku/
  config.py        env & threshold          universe.py   LQ45, ticker global, libur bursa
  db.py            SQLite                   pipeline.py   OHLCV → indikator → sinyal → rating
  ingestion/       eod.py, global_.py       indicators/   technical.py
  signals/         rules.py, scoring.py     analysis/     premarket.py, aftermarket.py
  report/          format.py, chart.py      llm/          ask.py (Claude)
  bot/             main.py, handlers.py, scheduler.py
  backtest/        run.py
scripts/           backfill.py, run_job.py
tests/
```

## Catatan

- Data dari Yahoo Finance (gratis, EOD). Bisa telat/gap — `validate_eod` + retry menanganinya; laporan
  parsial diberi tanda ticker yang hilang.
- Daftar LQ45 & libur bursa perlu diperbarui manual (rebalancing Feb/Agu; SK libur tahunan BEI).
- `.env`, `*.db`, dan `charts/` tidak di-commit.
