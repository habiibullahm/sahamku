# PRD — Sahamku Daily

**Versi** 1.1 · **Tanggal** 2026-09-12 · **Pemilik** Muhammad Habiibullah · **Status** Fase 1–4 terimplementasi; dokumen ini adalah baseline untuk iterasi berikutnya

## 1. Ringkasan

Sahamku adalah layanan Telegram yang membantu investor ritel Indonesia memantau saham IHSG setiap hari tanpa harus membuka charting tool. Produk terdiri dari dua permukaan yang saling melengkapi:

- **Channel `@sahamku_daily`** — koran pagi & sore: laporan pre-market (08:15 WIB) dan after-market (17:00 WIB) untuk semua subscriber.
- **Bot `@sahamku_id_bot`** — asisten pribadi: snapshot & chart per saham, watchlist, alert, screener, perbandingan, berita, dan tanya-jawab AI berbasis data.

Semua sinyal bersifat analitis dari data historis dan diberi disclaimer "bukan saran investasi".

**Masalah yang diselesaikan.** Investor ritel harus membuka beberapa aplikasi (sekuritas, TradingView, portal berita) hanya untuk tahu "apa yang terjadi hari ini dan apa yang perlu dilihat besok". Informasi tersebar, tidak ada ringkasan harian yang konsisten, dan analisis teknikal butuh waktu.

**Posisi.** Bukan pengganti aplikasi sekuritas dan bukan pemberi rekomendasi. Sahamku adalah *lapisan ringkasan* harian yang ringan, konsisten, dan bisa ditanya.

## 2. Tujuan & metrik sukses

| Tujuan | Metrik | Target 3 bulan |
|---|---|---|
| Laporan harian andal | Laporan terkirim tepat jadwal di hari bursa | ≥ 98% |
| Dipakai rutin | Subscriber channel aktif (buka ≥ 3 post/minggu) | ≥ 60% subscriber |
| Bot bernilai | Rasio user bot yang punya watchlist | ≥ 50% |
| Sinyal kredibel | Win rate 10D rule yang ditampilkan (backtest mingguan) | ≥ 55% untuk rule aktif |
| Biaya terkendali | Biaya infra + LLM per bulan | ≤ Rp 200 rb (fase 1–2) |

## 3. Pengguna

| Persona | Kebutuhan | Permukaan utama |
|---|---|---|
| **Ritel pasif** — cek pasar sekali sehari, tidak analisis sendiri | Ringkasan pagi/sore yang bisa dibaca 1 menit | Channel |
| **Swing trader ritel** — pegang 5–10 saham, cek level teknikal | Sinyal per saham, watchlist, alert level | Bot |
| **Pembelajar** — ingin paham "kenapa" | Penjelasan sinyal dalam bahasa manusia, `/ask` | Bot |
| **Admin/pemilik** — menjalankan layanan | Observabilitas job, error alert, statistik | Bot (admin) |

## 4. Ruang lingkup

**Termasuk:** saham IHSG (universe aktif **IDX80**, 80 ticker; perluasan ke seluruh papan utama masih terbuka), data EOD dan delayed intraday, indikator teknikal, sinyal rule-based, laporan terjadwal, chart, watchlist, alert, tanya-jawab AI, channel broadcast, panel admin.

**Tidak termasuk (untuk saat ini):** eksekusi order, integrasi sekuritas, data real-time berlisensi, rekomendasi beli/jual personal, analisis fundamental mendalam, web dashboard (dievaluasi setelah ≥ 100 subscriber), pembayaran tier Pro (tier diberikan manual oleh admin), bahasa Inggris.

## 5. Fitur

Legenda status: **Ada** (sudah berjalan di produksi/VPS), **Sebagian** (ada dengan keterbatasan), **Rencana** (belum dibangun). Prioritas: **P0** wajib, **P1** penting, **P2** nice-to-have.

### 5.1 Data & engine

| Fitur | Deskripsi | Status | Prio |
|---|---|---|---|
| Ingestion EOD | OHLCV harian LQ45 + IHSG dari Yahoo Finance, upsert ke SQLite, backfill 3 tahun | Ada | P0 |
| Ingestion global | Wall Street, Asia, US futures, minyak, emas, USD/IDR, UST10Y untuk pre-market | Ada | P0 |
| Validasi & retry | Cek kelengkapan bar hari ini; retry tiap 15 menit s/d 18:00; laporan parsial diberi tanda | Ada | P0 |
| Kalender bursa | Skip Sabtu/Minggu & libur IDX; jadwal Jumat berbeda | Ada (libur hardcoded) | P0 |
| Indikator | SMA 20/50/200, EMA 9/21, RSI14, MACD, Bollinger, ATR14, volume avg 20D | Ada | P0 |
| Rule engine | Golden/death cross, RSI OB/OS, breakout/breakdown 20D + volume, MACD cross, BB squeeze, posisi vs SMA200 | Ada | P0 |
| Scoring & rating | Bobot per rule → skor → bullish/bearish/netral; threshold di config | Ada | P0 |
| Backtest | Win rate & avg return 5/10/20D per rule, 3 tahun, mingguan ke admin | Ada | P1 |
| Universe IDX80 | `UNIVERSE=lq45\|idx80`; 35 ticker tambahan (best-effort, perlu dicocokkan dengan pengumuman BEI); backfill otomatis saat start. Filter likuiditas & seluruh papan utama belum | Sebagian | P1 |
| Auto-update daftar LQ45 & libur | Ambil dari pengumuman BEI (scrape/CSV) alih-alih hardcode | Rencana | P1 |
| Support/resistance otomatis | Swing high/low (pivot ±5 bar, 120D) di-cluster ±1,5% → S1/S2, R1/R2; dipakai `/stock`, `/ihsg`, pre-market, `/ask`. Belum dipakai alert (alert masih level manual) | Ada | P1 |
| Intraday delayed | Snapshot bar parsial tiap 15 menit 09:00–16:00 (Yahoo, delayed) → alert intraday & ringkasan tengah hari | Ada | P2 |
| Data fundamental ringkas | PER, PBV, dividend yield, market cap dari sumber gratis | Rencana | P2 |

### 5.2 Laporan terjadwal (channel + bot)

| Fitur | Deskripsi | Status | Prio |
|---|---|---|---|
| Pre-market 08:15 | Sentimen global (skor & label), pergerakan indeks/komoditas/kurs, level S/R IHSG, tren, catatan sektor, sinyal dari scan kemarin, watchlist (bot saja) | Ada | P0 |
| After-market 17:00 | IHSG close/%/volume, advancers/decliners, top 5 gainers/losers, sinyal bullish/bearish dengan alasan, Bollinger squeeze, watchlist (bot saja) | Ada | P0 |
| Broadcast channel | Versi publik laporan (tanpa watchlist) diposting ke `@sahamku_daily` | Ada | P0 |
| Footer CTA channel | Baris "Detail saham, chart & tanya AI → @sahamku_id_bot" di tiap post channel | Ada | P0 |
| Ringkasan tengah hari 12:15 (Jumat 11:45) | IHSG sesi 1 + range, advancers/decliners, top movers, watchlist; ke bot (pref `midday`) & channel | Ada | P2 |
| Rekap mingguan (Sabtu 09:00) | IHSG seminggu & range, top gainers/losers mingguan, akurasi sinyal (rating vs return ke Jumat); ke user & channel. Rekap per sektor & top rule belum | Sebagian | P1 |
| Chart IHSG di laporan | Candlestick 60D IHSG dilampirkan di after-market (tersedia on-demand via `/ihsg`) | Rencana | P1 |
| Penjelasan AI di laporan | 2–3 kalimat narasi LLM di bawah angka; dibuat sekali per (jenis, tanggal), cache DB, dipakai semua user/channel; gagal → laporan tanpa narasi | Ada | P1 |
| Post "cara pakai" ter-pin | Pesan pinned di channel (`scripts/channel_pin.py`): jadwal, arti rating, rule, link bot, disclaimer | Ada | P0 |

### 5.3 Bot — perintah interaktif

| Perintah | Deskripsi | Status | Prio |
|---|---|---|---|
| `/start`, `/help` | Daftar penerima laporan, menu perintah | Ada | P0 |
| `/scan` | Laporan after-market on-demand dari data terakhir | Ada | P0 |
| `/stock KODE` | Snapshot close/%/vol, indikator, S/R swing, rating, sinyal aktif, 3 berita terkait + chart 60D + tombol Berita/Watch/Tanya AI | Ada | P0 |
| `/watch`, `/unwatch`, `/watchlist` | Watchlist pribadi, ikut di laporan | Ada | P0 |
| `/ask pertanyaan` | Tanya AI dengan konteks IHSG, global, 15 bar, indikator, sinyal, S/R, berita pasar & emiten; memori 2 jam; `/ask clear` | Ada | P0 |
| Fallback perintah tak dikenal | Arahkan ke `/help` | Ada | P1 |
| `/news [KODE]` | Berita pasar 24 jam / emiten 72 jam dengan sentimen dan link | Ada | P1 |
| `/alert KODE > 10000`, `/alerts`, `/unalert ID` | Alert harga (`>`, `<`, `>=`, `<=`) atau `rsi < N`; dicek tiap 15 menit intraday (delayed) & setelah EOD; one-shot. Alert "tembus S/R" otomatis belum | Ada | P1 |
| `/screener` | Filter AND: `rating=`, `rsi`/`chg`/`vol` dengan operator, `above200/below200`, `squeeze`, `oversold/overbought`, `breakout/breakdown`, `golden/death`, `macd_up/down`; cache per tanggal | Ada | P1 |
| `/compare A B C` | 2–4 saham: return 1W/1M/3M, RSI, posisi vs SMA50/200, rating + chart normalisasi 3 bulan | Ada | P2 |
| `/ihsg` | Snapshot indeks + chart + S/R 20 hari & swing + tren | Ada | P1 |
| `/sector` | 9 sektor (pemetaan 80 ticker, best-effort): rata-rata %, jumlah bullish/bearish, terbaik/terburuk | Ada | P2 |
| `/settings` | Toggle inline: pre-market, tengah hari, after-market, mingguan, alert. Jam kirim kustom & bahasa EN belum | Sebagian | P1 |
| `/stop` / `/resume` | Berhenti/lanjut menerima laporan; user yang memblokir bot otomatis di-unsubscribe | Ada | P0 |
| `/backtest RULE` | Tabel win rate satu rule + contoh sinyal terakhir | Rencana | P2 |
| Inline button | Tombol Berita · Watch/Unwatch · Tanya AI di bawah `/stock`; toggle di `/settings` | Ada | P1 |

### 5.4 AI

| Fitur | Deskripsi | Status | Prio |
|---|---|---|---|
| `/ask` berbasis data | Konteks: IHSG, global, 15 bar terakhir, indikator, sinyal; provider Groq (gratis) atau Anthropic | Ada | P0 |
| Deteksi ticker | Kode KAPITAL atau `$kode`; maks 3 saham per pertanyaan | Ada | P0 |
| Guardrail | Tidak memberi perintah beli/jual; disclaimer; tidak mengarang angka (prompt) | Ada | P0 |
| Rate limit `/ask` | Kuota per chat/hari: Free 10, Pro 50, admin bebas; sisa kuota ditampilkan | Ada | P0 |
| Memori percakapan singkat | 3 giliran / 2 jam per chat; pertanyaan lanjutan tanpa kode memakai kode giliran sebelumnya | Ada | P1 |
| Narasi sinyal per saham | LLM menulis 1 kalimat "kenapa" untuk tiap sinyal (narasi per laporan sudah ada, per sinyal belum) | Rencana | P2 |
| Sentimen berita | RSS CNBC Market, Kontan Investasi, IDX Channel, Liputan6 Saham, Detik Finance → LLM batch (ticker, sentimen −1/0/+1, relevansi); seksi Berita + sentimen emiten di pre-market, `/news`, `/stock`, `/ask`. Belum memengaruhi skor sinyal (disengaja) | Ada | P1 |
| `/ask` dengan chart (vision) | Kirim gambar chart → AI membaca pola | Rencana | P2 |
| Evaluasi kualitas jawaban | `scripts/eval_ask.py`: 10 pertanyaan uji (termasuk jebakan "beli?" & "harga 2030?"), simpan ke `docs/eval/` untuk diff antar model/prompt. Rubrik otomatis belum | Sebagian | P1 |

### 5.5 Channel

| Fitur | Deskripsi | Status | Prio |
|---|---|---|---|
| Broadcast pre/after-market | Otomatis 08:15 & 17:00 WIB hari bursa | Ada | P0 |
| Identitas | Nama, deskripsi, foto profil (logo), link bot di pinned post | Ada | P0 |
| Format post konsisten | Judul tetap, emoji fungsional, narasi AI, disclaimer, CTA bot | Ada | P0 |
| Pinned "cara pakai" | Panduan singkat + arti rating (post #7) | Ada | P0 |
| Rekap mingguan & bulanan | Mingguan Sabtu 09:00 ada; bulanan belum | Sebagian | P1 |
| Grup diskusi tertaut | Grup komentar (opsional) dengan moderasi bot | Rencana | P2 |

### 5.6 Admin & operasi

| Fitur | Deskripsi | Status | Prio |
|---|---|---|---|
| Log job (`job_runs`) | Status, durasi, error tiap job | Ada | P0 |
| Backtest mingguan ke admin | Sabtu 09:00 | Ada | P1 |
| Alert error ke admin | Job gagal → pesan 🚨 ke `ADMIN_CHAT_ID` dengan nama job & error | Ada | P0 |
| `/admin` | User, subscribed, watchlist, alert, `/ask` hari ini, berita, data, 8 job terakhir. Subscriber channel tidak tersedia via Bot API | Ada | P1 |
| `/admin broadcast`, `/admin pro\|free` | Pengumuman ke semua user; set tier user | Ada | P1 |
| Health check | Endpoint/ping sederhana + notifikasi jika bot mati > 10 menit | Rencana | P1 |
| Deploy 24/7 | VPS Ubuntu 24.04 (Cloudeka/SumoPod, Jakarta), Docker Compose `restart: unless-stopped`, log rotation, hardening SSH (key only), ufw, fail2ban, swap. Runbook `docs/VPS.md`, deploy via `scripts/deploy.sh` | Ada | P0 |
| Backup DB | Snapshot SQLite harian ke storage terpisah (saat ini manual via `ssh … cat > backup.db`) | Rencana | P1 |
| Misfire handling | Job yang terlewat ≤ 2 jam tetap dijalankan (kurang mendesak setelah pindah ke VPS) | Rencana | P2 |

### 5.7 Monetisasi (opsional, setelah fase 3)

| Tier | Isi (terimplementasi) | Cara mendapat |
|---|---|---|
| **Free** | Channel penuh; semua perintah bot; watchlist ≤ 5; alert aktif ≤ 3; `/ask` 10/hari | Default |
| **Pro** | Watchlist ≤ 30; alert ≤ 20; `/ask` 50/hari | `/admin pro <chat_id>` (manual) |

**Belum ada:** pembayaran (Telegram Stars / Midtrans), model lebih kuat khusus Pro, rekap portofolio. Harga (Rp 29–49 rb/bulan) dan pembayaran diputuskan setelah retensi 30 hari ≥ 40%.

## 6. Kebutuhan non-fungsional

- **Keandalan:** laporan terkirim ≤ 5 menit dari jadwal; job idempotent; retry data; restart otomatis.
- **Waktu:** semua jadwal dalam `Asia/Jakarta`; kalender bursa diperbarui tahunan.
- **Kinerja:** `/stock` ≤ 5 detik termasuk chart; `/ask` ≤ 10 detik.
- **Biaya:** infra ≤ Rp 150 rb/bulan; LLM memakai free tier atau ≤ $10/bulan.
- **Keamanan:** token & API key hanya di env; tidak ada secret di repo/log; rate limit per user; validasi input perintah.
- **Kepatuhan:** disclaimer di setiap laporan dan jawaban AI; tidak ada rekomendasi beli/jual personal; nama produk tidak memakai merek BEI/IDX.
- **Privasi:** menyimpan chat_id, username, watchlist, alert, preferensi, dan riwayat `/ask` (untuk memori 2 jam). Pembersihan riwayat `/ask` > 30 hari belum diotomatisasi (rencana).

## 7. Arsitektur (ringkas)

```
Yahoo Finance (EOD, global, intraday) ─▶ ingestion ─▶ SQLite ─▶ indikator ─▶ rules/scoring ─▶ laporan ─┬─▶ Channel
RSS berita ─▶ news/ingest ─▶ LLM sentimen ─────────────┘            levels (S/R) ─┘  narasi LLM ─┘       └─▶ Bot (user)
APScheduler (WIB): 07:30 global · 07:45 berita · 08:15 pre-market · 09–16 intraday/15m · 12:15 tengah hari
                   16:10 berita · 16:30 EOD+alert · 17:00 after-market · Sabtu 09:00 rekap, 09:15 backtest
Bot (aiogram) ◀─▶ user — /ask (memori 2 jam) ─▶ LLM adapter (Groq gpt-oss-120b | Anthropic)
```

Python 3.12 · aiogram 3 · APScheduler · pandas · mplfinance · feedparser · SQLite · Docker · VPS Ubuntu 24.04.

## 8. Roadmap

| Fase | Fokus | Fitur utama | Selesai bila |
|---|---|---|---|
| **1 — Fondasi** ✅ | Laporan harian andal | Ingestion, indikator, rules, pre/after-market, bot dasar, `/ask`, channel, Docker | Berjalan 2 minggu tanpa intervensi |
| **2 — Kredibilitas & retensi** ✅ | Bikin orang balik tiap hari | Footer CTA & pinned post, `/stop`, rate limit `/ask`, alert error admin, `/alert` EOD, `/ihsg`, rekap mingguan, narasi AI di laporan, deploy VPS | ≥ 100 subscriber channel, ≥ 30 user bot dengan watchlist |
| **3 — Kedalaman** ✅ (kecuali bahasa EN) | Lebih banyak alasan pakai bot | Sentimen berita, `/screener`, `/settings`, inline button, universe IDX80, S/R otomatis, memori `/ask`, `/admin` | Win rate rule aktif ≥ 55%; `/ask` ≥ 20/hari |
| **4 — Skala** ✅ (kecuali pembayaran & web dashboard) | Intraday & monetisasi | Alert intraday delayed, ringkasan 12:15, `/compare`, `/sector`, tier Pro, evaluasi web dashboard | Retensi 30 hari ≥ 40% |
| **5 — Berikutnya** (diusulkan) | Operasional & kualitas | Backup DB otomatis, health check, auto-update LQ45/IDX80 & libur dari BEI, chart IHSG di after-market, rekap bulanan, narasi per sinyal, rubrik eval `/ask`, pembersihan riwayat `/ask`, filter likuiditas universe, pembayaran Pro | Semua P0/P1 tersisa selesai; 4 minggu tanpa insiden |

## 9. Risiko & mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Yahoo Finance telat/putus/berubah | Laporan terlambat atau kosong | Validasi + retry s/d 18:00; laporan parsial diberi tanda; siapkan sumber cadangan (mis. Stockbit/GoAPI) |
| Sinyal momentum lemah di pasar sideways/turun | Kredibilitas turun | Backtest mingguan; sembunyikan rule dengan win rate < 50%; tonjolkan rule mean-reversion |
| Free tier Groq berubah/limit | `/ask` gagal | Adapter provider; fallback ke Anthropic dengan spend limit; rate limit per user |
| VPS mati / provider gangguan | Job terlewat | Docker auto-restart & enable on boot (ada); health check eksternal + backup DB otomatis (rencana) |
| Persepsi "saran investasi" | Risiko regulasi OJK | Disclaimer konsisten; bahasa "skenario/level", bukan "beli/jual"; tidak ada target harga personal |
| Spam/abuse bot | Biaya & rate limit Telegram | Kuota `/ask`, batas watchlist/alert per tier (ada); blokir user & antrian broadcast (rencana) |
| Daftar IDX80/sektor tidak akurat | Saham salah/tertinggal | Cocokkan dengan pengumuman BEI tiap rebalancing; otomatisasi (rencana) |
| LLM menambah detail yang tidak ada di data | Jawaban menyesatkan | Prompt "hanya angka dari data"; eval set; narasi dibatasi 60 kata; disclaimer |

## 10. Pertanyaan terbuka

**Sudah diputuskan**
1. Universe: IDX80 (80 ticker) — filter likuiditas untuk perluasan berikutnya.
2. Rekap mingguan: ke bot **dan** channel.
3. Bahasa Inggris: ditunda (butuh i18n semua formatter).
4. Hosting: VPS Cloudeka/SumoPod Jakarta (Railway trial habis; Vercel tidak cocok untuk long polling).
5. Nama channel: `@sahamku_daily` (`@sahamku_id` sudah dipakai).

**Masih terbuka**
1. Monetisasi: Telegram Stars vs. transfer manual vs. Midtrans — putuskan setelah retensi terbukti.
2. Kapan sentimen berita boleh memengaruhi skor sinyal (perlu bukti backtest)?
3. Web dashboard: dibangun setelah ≥ 100 subscriber, atau cukup bot + channel?
4. Sumber data cadangan bila Yahoo Finance berubah (Stockbit/GoAPI)?
