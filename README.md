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

`CHANNEL_ID` (opsional) = channel publik, mis. `@sahamku_id`. Laporan pre/after-market ikut diposting
ke channel (tanpa watchlist). Bot harus dijadikan **admin channel** dengan izin *Post messages*.

## Jalankan 24 jam dengan Docker

```bash
docker compose up -d --build     # build + jalankan di background, auto-restart
docker compose logs -f           # lihat log
docker compose down              # hentikan
```

- DB dan chart disimpan di `./data/` (volume). Jika `data/sahamku.db` belum ada, entrypoint
  menjalankan backfill 3 tahun otomatis saat start pertama.
- Setelah mengubah `.env`: `docker compose up -d` (recreate). Setelah mengubah kode:
  `docker compose up -d --build`.
- Agar bot hidup setelah laptop/PC restart: aktifkan **Docker Desktop → Settings → General →
  Start Docker Desktop when you sign in**. Bot tetap butuh mesin ini menyala; untuk 24/7 penuh,
  jalankan compose yang sama di VPS.
- Jangan jalankan `python -m sahamku.bot.main` lokal bersamaan dengan container — Telegram hanya
  mengizinkan satu long-polling per bot.

## Deploy ke VPS (Ubuntu 22.04/24.04)

```bash
ssh root@IP_VPS
curl -fsSL https://raw.githubusercontent.com/habiibullahm/sahamku/main/scripts/vps_setup.sh -o setup.sh
bash setup.sh          # update, user deploy, ufw, fail2ban, swap, Docker, clone ke /opt/sahamku
nano /opt/sahamku/.env # isi token & key
cd /opt/sahamku && docker compose up -d --build
```

Update kode di VPS (repo private): `bash scripts/deploy.sh`. Runbook lengkap: [docs/VPS.md](docs/VPS.md).
Bawa DB dari laptop (opsional): `scp data/sahamku.db deploy@IP_VPS:/opt/sahamku/data/` sebelum `up`.

## Deploy ke Railway

1. New Project → Deploy from GitHub repo → pilih repo ini (Dockerfile & `railway.json` terdeteksi).
2. Variables: `TELEGRAM_BOT_TOKEN`, `ADMIN_CHAT_ID`, `LLM_PROVIDER=groq`, `GROQ_API_KEY`,
   `GROQ_MODEL=openai/gpt-oss-120b`, `DB_PATH=/data/sahamku.db`, `CHARTS_DIR=/data/charts`,
   `TZ=Asia/Jakarta`.
3. Settings → Volumes → Add Volume, mount path **`/data`** (wajib, agar DB bertahan antar deploy).
4. Tidak perlu public domain/port (worker, bukan web). `numReplicas` harus 1 — Telegram hanya
   mengizinkan satu long-polling per bot.
5. Deploy pertama menjalankan backfill 3 tahun otomatis (±1–2 menit), lalu bot polling.
6. Matikan instance lain (`docker compose down` di laptop) agar tidak konflik `getUpdates`.

## Command

| Command | Fungsi |
|---|---|
| `/scan` | Laporan after-market dari data terakhir |
| `/stock BBCA` | Snapshot harga, indikator, rating, sinyal + chart 60 hari |
| `/watch BBCA` / `/unwatch BBCA` / `/watchlist` | Watchlist per chat; ikut dilaporkan di pre/after-market |
| `/ask kenapa BBCA turun?` | Tanya AI dengan konteks harga, indikator, sinyal, S/R, berita; ingat percakapan 2 jam (`/ask clear`) |
| `/ihsg` | Snapshot IHSG + chart + support/resistance |
| `/news [KODE]` | Berita pasar/emiten dengan sentimen (🟢🔴⚪) |
| `/screener rsi<35 above200` | Filter saham (rating, rsi, chg, vol, squeeze, breakout, golden, …) |
| `/compare BBCA BBRI BMRI` | Return 1W/1M/3M, RSI, posisi vs SMA + chart normalisasi |
| `/sector` | Rata-rata % per sektor, jumlah bullish/bearish, terbaik/terburuk |
| `/alert BBCA > 6500` / `/alerts` / `/unalert ID` | Alert level harga/RSI, dicek tiap 15 menit (delayed) & setelah close |
| `/settings` | Pilih laporan yang diterima (pre-market, tengah hari, after-market, mingguan, alert) |
| `/stop` / `/resume` | Matikan/aktifkan semua laporan otomatis |
| `/admin`, `/admin broadcast <pesan>`, `/admin pro\|free <chat_id>` | Statistik, broadcast, tier user (hanya `ADMIN_CHAT_ID`) |

## Jadwal (WIB, hari bursa; libur di `sahamku/universe.py`)

| Jam | Job |
|---|---|
| 07:30 · 07:45 | Ingest aset global · ingest & analisis berita (Wall Street, Asia, minyak, emas, USD/IDR, UST10Y) |
| 09:00–16:00 tiap 15 mnt | Snapshot intraday (delayed) + cek alert |
| 12:15 (Jumat 11:45) | Ringkasan tengah hari (bot & channel) |
| 08:15 | Kirim laporan pre-market (sentimen global, level S/R IHSG, sinyal kemarin, watchlist) |
| 16:10 · 16:30 | Berita · ingest EOD LQ45+IHSG → validasi → indikator → sinyal. Retry tiap 15 menit s/d 18:00 jika belum lengkap |
| 17:00 | Kirim laporan after-market (IHSG, top movers, sinyal bullish/bearish, squeeze, watchlist) |
| Sabtu 09:00 · 09:15 | Rekap mingguan (user & channel) · backtest ke admin |

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

## Tier

| | Free | Pro (`/admin pro <chat_id>`) |
|---|---|---|
| Watchlist | 5 | 30 |
| Alert aktif | 3 | 20 |
| `/ask` per hari | 10 | 50 |

Pembayaran belum diintegrasikan; tier diberikan manual oleh admin.

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
- Daftar LQ45/IDX80 & libur bursa perlu diperbarui manual (rebalancing Feb/Agu; SK libur tahunan BEI).
  Universe dipilih lewat `UNIVERSE=lq45|idx80`; ticker baru di-backfill otomatis saat bot start.
- `.env`, `*.db`, dan `charts/` tidak di-commit.
