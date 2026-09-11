# PRD — Sahamku Daily

**Versi** 1.0 · **Tanggal** 2026-09-12 · **Pemilik** Muhammad Habiibullah · **Status** Draft untuk review

## 1. Ringkasan

Sahamku adalah layanan Telegram yang membantu investor ritel Indonesia memantau saham IHSG setiap hari tanpa harus membuka charting tool. Produk terdiri dari dua permukaan yang saling melengkapi:

- **Channel `@sahamku_daily`** — koran pagi & sore: laporan pre-market (08:15 WIB) dan after-market (17:00 WIB) untuk semua subscriber.
- **Bot `@sahamku_id_bot`** — asisten pribadi: snapshot & chart per saham, watchlist, alert, dan tanya-jawab AI berbasis data.

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

**Termasuk:** saham IHSG (mulai LQ45, meluas ke IDX80 lalu seluruh papan utama), data EOD dan delayed intraday, indikator teknikal, sinyal rule-based, laporan terjadwal, chart, watchlist, alert, tanya-jawab AI, channel broadcast, panel admin.

**Tidak termasuk (untuk saat ini):** eksekusi order, integrasi sekuritas, data real-time berlisensi, rekomendasi beli/jual personal, analisis fundamental mendalam, web dashboard (dievaluasi setelah fase 3).

## 5. Fitur

Legenda status: **Ada** (sudah berjalan), **Rencana** (belum dibangun). Prioritas: **P0** wajib, **P1** penting, **P2** nice-to-have.

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
| Universe IDX80 / semua saham | Perluas daftar ticker + filter likuiditas (min. nilai transaksi harian) | Rencana | P1 |
| Auto-update daftar LQ45 & libur | Ambil dari pengumuman BEI (scrape/CSV) alih-alih hardcode | Rencana | P1 |
| Support/resistance otomatis | Pivot & swing high/low 20/60D; dipakai laporan, alert, dan `/ask` | Rencana | P1 |
| Intraday delayed | Snapshot 15 menit (Yahoo) untuk alert & ringkasan tengah hari | Rencana | P2 |
| Data fundamental ringkas | PER, PBV, dividend yield, market cap dari sumber gratis | Rencana | P2 |

### 5.2 Laporan terjadwal (channel + bot)

| Fitur | Deskripsi | Status | Prio |
|---|---|---|---|
| Pre-market 08:15 | Sentimen global (skor & label), pergerakan indeks/komoditas/kurs, level S/R IHSG, tren, catatan sektor, sinyal dari scan kemarin, watchlist (bot saja) | Ada | P0 |
| After-market 17:00 | IHSG close/%/volume, advancers/decliners, top 5 gainers/losers, sinyal bullish/bearish dengan alasan, Bollinger squeeze, watchlist (bot saja) | Ada | P0 |
| Broadcast channel | Versi publik laporan (tanpa watchlist) diposting ke `@sahamku_daily` | Ada | P0 |
| Footer CTA channel | Baris "Detail saham & tanya AI → @sahamku_id_bot" di tiap post channel | Rencana | P0 |
| Ringkasan tengah hari 12:15 | IHSG sesi 1, top movers, watchlist (dari data delayed) | Rencana | P2 |
| Rekap mingguan (Sabtu) | Performa IHSG & sektor seminggu, sinyal yang terbukti/gagal, top rule minggu ini | Rencana | P1 |
| Chart IHSG di laporan | Candlestick 60D IHSG dilampirkan di after-market | Rencana | P1 |
| Penjelasan AI di laporan | 2–3 kalimat narasi LLM ("apa artinya hari ini") di bawah angka | Rencana | P1 |
| Post "cara pakai" ter-pin | Pesan pinned di channel: jadwal, arti rating, link bot, disclaimer | Rencana | P0 |

### 5.3 Bot — perintah interaktif

| Perintah | Deskripsi | Status | Prio |
|---|---|---|---|
| `/start`, `/help` | Daftar penerima laporan, menu perintah | Ada | P0 |
| `/scan` | Laporan after-market on-demand dari data terakhir | Ada | P0 |
| `/stock KODE` | Snapshot close/%/vol, indikator, rating, sinyal aktif + chart 60D | Ada | P0 |
| `/watch`, `/unwatch`, `/watchlist` | Watchlist pribadi, ikut di laporan | Ada | P0 |
| `/ask pertanyaan` | Tanya AI dengan konteks harga, indikator, sinyal, sentimen global | Ada | P0 |
| Fallback perintah tak dikenal | Arahkan ke `/help` | Ada | P1 |
| `/alert KODE > 10000` | Alert harga/level (close di atas/bawah, tembus S/R, RSI). Dicek saat EOD (fase 2) lalu intraday delayed (fase 3) | Rencana | P1 |
| `/screener` | Filter cepat: `rating=bullish`, `rsi<30`, `vol>2x`, `squeeze` | Rencana | P1 |
| `/compare A B C` | Perbandingan 2–4 saham: return 1W/1M/3M, RSI, posisi vs SMA, chart normalisasi | Rencana | P2 |
| `/ihsg` | Snapshot indeks + chart + level S/R | Rencana | P1 |
| `/sector` | Ringkasan per sektor (return hari ini, jumlah bullish/bearish) | Rencana | P2 |
| `/settings` | Jam kirim laporan, matikan pre/after-market, bahasa (ID/EN) | Rencana | P1 |
| `/stop` / `/resume` | Berhenti/lanjut menerima laporan tanpa memblokir bot | Rencana | P0 |
| `/backtest RULE` | Tabel win rate satu rule + contoh sinyal terakhir | Rencana | P2 |
| Inline button | Tombol "Chart", "Watch", "Tanya AI" di bawah snapshot | Rencana | P1 |

### 5.4 AI

| Fitur | Deskripsi | Status | Prio |
|---|---|---|---|
| `/ask` berbasis data | Konteks: IHSG, global, 15 bar terakhir, indikator, sinyal; provider Groq (gratis) atau Anthropic | Ada | P0 |
| Deteksi ticker | Kode KAPITAL atau `$kode`; maks 3 saham per pertanyaan | Ada | P0 |
| Guardrail | Tidak memberi perintah beli/jual; disclaimer; tidak mengarang angka (prompt) | Ada | P0 |
| Rate limit `/ask` | Kuota per user/hari (mis. 10) untuk melindungi free tier & biaya | Rencana | P0 |
| Memori percakapan singkat | 3–5 giliran terakhir per chat untuk pertanyaan lanjutan | Rencana | P1 |
| Narasi sinyal | LLM menulis 1 kalimat "kenapa" untuk tiap sinyal di laporan | Rencana | P1 |
| Sentimen berita | RSS Kontan/Bisnis/CNBC → skor sentimen per emiten & sektor, masuk pre-market dan `/ask` | Rencana | P1 |
| `/ask` dengan chart (vision) | Kirim gambar chart → AI membaca pola | Rencana | P2 |
| Evaluasi kualitas jawaban | Set 30 pertanyaan uji + rubrik; dijalankan saat ganti model/prompt | Rencana | P1 |

### 5.5 Channel

| Fitur | Deskripsi | Status | Prio |
|---|---|---|---|
| Broadcast pre/after-market | Otomatis 08:15 & 17:00 WIB hari bursa | Ada | P0 |
| Identitas | Nama, deskripsi, foto profil, link bot di bio | Sebagian | P0 |
| Format post konsisten | Judul tetap, emoji fungsional, disclaimer, CTA bot | Sebagian | P0 |
| Pinned "cara pakai" | Panduan singkat + arti rating | Rencana | P0 |
| Rekap mingguan & bulanan | Post Sabtu & awal bulan | Rencana | P1 |
| Grup diskusi tertaut | Grup komentar (opsional) dengan moderasi bot | Rencana | P2 |

### 5.6 Admin & operasi

| Fitur | Deskripsi | Status | Prio |
|---|---|---|---|
| Log job (`job_runs`) | Status, durasi, error tiap job | Ada | P0 |
| Backtest mingguan ke admin | Sabtu 09:00 | Ada | P1 |
| Alert error ke admin | Job gagal / data tidak lengkap s/d 18:00 → pesan ke `ADMIN_CHAT_ID` | Rencana | P0 |
| `/admin stats` | Jumlah user, watchlist, `/ask` hari ini, job terakhir, subscriber channel | Rencana | P1 |
| `/admin broadcast` | Kirim pengumuman ke semua user bot | Rencana | P1 |
| Health check | Endpoint/ping sederhana + notifikasi jika bot mati > 10 menit | Rencana | P1 |
| Deploy 24/7 | Docker Compose (ada), VPS/Oracle (rencana), auto-restart, log rotation | Sebagian | P0 |
| Backup DB | Snapshot SQLite harian ke storage terpisah | Rencana | P1 |
| Misfire handling | Job yang terlewat saat host sleep ≤ 2 jam tetap dijalankan | Rencana | P1 |

### 5.7 Monetisasi (opsional, setelah fase 3)

| Tier | Isi |
|---|---|
| **Free** | Channel penuh; bot: `/stock`, `/scan`, watchlist ≤ 5, `/ask` 5/hari |
| **Pro** (Rp 29–49 rb/bulan) | Watchlist tak terbatas, alert intraday, `/screener`, `/compare`, `/ask` 50/hari dengan model lebih kuat, rekap portofolio |

Keputusan monetisasi ditunda sampai metrik retensi terbukti.

## 6. Kebutuhan non-fungsional

- **Keandalan:** laporan terkirim ≤ 5 menit dari jadwal; job idempotent; retry data; restart otomatis.
- **Waktu:** semua jadwal dalam `Asia/Jakarta`; kalender bursa diperbarui tahunan.
- **Kinerja:** `/stock` ≤ 5 detik termasuk chart; `/ask` ≤ 10 detik.
- **Biaya:** infra ≤ Rp 150 rb/bulan; LLM memakai free tier atau ≤ $10/bulan.
- **Keamanan:** token & API key hanya di env; tidak ada secret di repo/log; rate limit per user; validasi input perintah.
- **Kepatuhan:** disclaimer di setiap laporan dan jawaban AI; tidak ada rekomendasi beli/jual personal; nama produk tidak memakai merek BEI/IDX.
- **Privasi:** hanya menyimpan chat_id, username, watchlist; tidak menyimpan isi pertanyaan `/ask` lebih dari 30 hari (rencana).

## 7. Arsitektur (ringkas)

```
Yahoo Finance ─▶ ingestion ─▶ SQLite ─▶ indikator ─▶ rules/scoring ─▶ laporan ─┬─▶ Channel
                                                     │                          └─▶ Bot (user)
                                      APScheduler (WIB) ─────────────────────────┘
Bot (aiogram) ◀─▶ user  ── /ask ─▶ LLM adapter (Groq | Anthropic)
```

Python 3.12 · aiogram 3 · APScheduler · pandas · mplfinance · SQLite · Docker.

## 8. Roadmap

| Fase | Fokus | Fitur utama | Selesai bila |
|---|---|---|---|
| **1 — Fondasi** (selesai) | Laporan harian andal | Ingestion, indikator, rules, pre/after-market, bot dasar, `/ask`, channel, Docker | Berjalan 2 minggu tanpa intervensi |
| **2 — Kredibilitas & retensi** (2–3 minggu) | Bikin orang balik tiap hari | Footer CTA & pinned post, `/stop`, rate limit `/ask`, alert error admin, `/alert` EOD, `/ihsg`, rekap mingguan, narasi AI di laporan, deploy VPS | ≥ 100 subscriber channel, ≥ 30 user bot dengan watchlist |
| **3 — Kedalaman** (4–6 minggu) | Lebih banyak alasan pakai bot | Sentimen berita, `/screener`, `/settings`, inline button, universe IDX80, S/R otomatis, memori `/ask`, `/admin` | Win rate rule aktif ≥ 55%; `/ask` ≥ 20/hari |
| **4 — Skala** (setelahnya) | Intraday & monetisasi | Alert intraday delayed, ringkasan 12:15, `/compare`, `/sector`, tier Pro, evaluasi web dashboard | Retensi 30 hari ≥ 40% |

## 9. Risiko & mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Yahoo Finance telat/putus/berubah | Laporan terlambat atau kosong | Validasi + retry s/d 18:00; laporan parsial diberi tanda; siapkan sumber cadangan (mis. Stockbit/GoAPI) |
| Sinyal momentum lemah di pasar sideways/turun | Kredibilitas turun | Backtest mingguan; sembunyikan rule dengan win rate < 50%; tonjolkan rule mean-reversion |
| Free tier Groq berubah/limit | `/ask` gagal | Adapter provider; fallback ke Anthropic dengan spend limit; rate limit per user |
| Host (laptop) sleep/mati | Job terlewat | Pindah ke VPS; misfire grace; health check + alert |
| Persepsi "saran investasi" | Risiko regulasi OJK | Disclaimer konsisten; bahasa "skenario/level", bukan "beli/jual"; tidak ada target harga personal |
| Spam/abuse bot | Biaya & rate limit Telegram | Rate limit per chat; blokir; broadcast antrian |

## 10. Pertanyaan terbuka

1. Universe fase 3: IDX80 atau langsung semua saham dengan filter likuiditas?
2. Apakah rekap mingguan cukup di channel, atau juga ke bot?
3. Bahasa Inggris — perlukah di fase 3 (diaspora/asing) atau ditunda?
4. Monetisasi via Telegram Stars vs. transfer manual vs. Midtrans?
5. Nama channel: tetap `@sahamku_daily` atau rebrand saat username `@sahamku` tersedia?
