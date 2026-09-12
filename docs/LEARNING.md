# 📚 Catatan Pembelajaran — Proyek Sahamku

> Dokumentasi apa yang dipelajari saat membangun **Sahamku** (bot Telegram + channel scan harian saham IHSG) dari nol sampai berjalan 24/7 di VPS, ditambah setup **Hermes Agent**. Ditulis untuk diimpor ke Notion — tiap bagian bisa dijadikan halaman/toggle sendiri.

**Periode:** 11–12 September 2026 · **Repo:** `habiibullahm/sahamku` (private) · **Stack:** Python 3.12, aiogram, APScheduler, pandas, SQLite, Docker, Ubuntu VPS

---

## 0. Peta besar: dari ide ke produksi

| Tahap | Yang dibuat | Pelajaran kunci |
|---|---|---|
| Ide & desain | Gambaran arsitektur, pilih Telegram bot sebagai UI pertama | Mulai dari permukaan paling murah (bot) sebelum web dashboard |
| PRD | Dokumen kebutuhan produk: persona, fitur + prioritas P0–P2, roadmap 4 fase | PRD bukan formalitas — jadi checklist eksekusi dan alat komunikasi |
| MVP (fase 1) | Ingestion → indikator → sinyal → laporan → bot | Kerjakan urutan data dulu, UI belakangan |
| Fase 2–4 | Alert, screener, berita+sentimen, narasi AI, intraday, tier | Setiap fitur = kode + test + deploy + verifikasi nyata |
| Operasional | Docker → VPS, hardening SSH, runbook | Produk belum "selesai" sebelum bisa hidup tanpa laptop |

---

## 1. Produk & perencanaan

### Bot vs Channel Telegram
- **Bot** = dua arah, personal (watchlist, `/ask`), user harus `/start`.
- **Channel** = satu arah, broadcast, cukup *join*, mudah di-share.
- Channel **tidak bisa berdiri sendiri** — butuh bot untuk mengisinya. Pola: channel untuk akuisisi, bot untuk engagement.

### Menulis PRD yang berguna
- Struktur: ringkasan → tujuan & metrik → persona → ruang lingkup (termasuk/tidak) → fitur dengan **status** & **prioritas** → non-fungsional → arsitektur → roadmap → risiko → pertanyaan terbuka.
- Status jujur (*Ada / Sebagian / Rencana*) lebih berguna daripada daftar keinginan. Perbarui PRD setelah tiap fase (v1.0 → v1.1).

### Regulasi & etika
- Bahasa "sinyal analitis / skenario / level", bukan "beli/jual". Disclaimer di setiap laporan dan jawaban AI.
- Jangan pakai merek BEI/IDX sebagai nama produk.

---

## 2. Data pasar & analisis teknikal

### Sumber data
- **Yahoo Finance** (`yfinance`): gratis, EOD + intraday delayed ±15 menit, ticker `.JK`, plus indeks global/komoditas/kurs. Cukup untuk MVP; data real-time IDX berlisensi.
- Jebakan yang ditemui:
  - `yf.download` untuk **1 ticker** tetap mengembalikan kolom MultiIndex → cek `isinstance(df.columns, pd.MultiIndex)`.
  - Bar hari ini **parsial** kalau ditarik saat jam bursa → job EOD dijadwalkan 16:30 setelah post-trading.
  - Data bisa telat → **validasi kelengkapan + retry** tiap 15 menit sampai batas waktu, lalu kirim laporan parsial yang diberi tanda.

### Jam bursa IDX (WIB)
Pre-opening 08:45 · Sesi 1 09:00–12:00 (Jumat 11:30) · Sesi 2 13:30–15:50 (Jumat 14:00) · Post-trading s/d 16:15. Kalender libur harus di-hardcode/diupdate tahunan.

### Indikator yang dipakai
SMA 20/50/200, EMA 9/21, RSI 14 (Wilder), MACD 12/26/9, Bollinger 20/2σ, ATR 14, volume avg 20D. Ditulis manual dengan pandas — lebih mudah dikontrol daripada bergantung pada `pandas-ta` (yang bermasalah di pandas 3).

### Rule-based signal & scoring
- Rule = **event** (golden/death cross, RSI cross 30/70, breakout 20D + volume, MACD cross) atau **state** (posisi vs SMA200). State ikut skor tapi tidak ditampilkan sebagai "alasan".
- Bobot per rule → skor → rating (≥ +2 bullish, ≤ −2 bearish).
- Backtest 3 tahun LQ45 (win rate & return 5/10/20D): rule **mean-reversion (RSI)** ~53–59%, **momentum (breakout, golden cross)** < 45% di periode IHSG turun. Pelajaran: jangan percaya rule sebelum di-backtest, dan hasil backtest itu spesifik rezim pasar.

### Support/resistance otomatis
Pivot swing high/low (±5 bar, 120 hari) → cluster ±1,5% → ambil 2 terdekat di bawah (S) dan di atas (R) harga. Tambahkan ekstrem `2×window` bar terakhir karena pivot tidak bisa terbentuk di bar terbaru.

---

## 3. Python & arsitektur aplikasi

### Struktur modul (separation of concerns)
```
ingestion/ (ambil data) → indicators/ (hitung) → signals/ (rule + skor) → analysis/ (bangun laporan)
→ report/ (format teks/chart) → bot/ (handler + scheduler) · llm/ (adapter AI) · news/ · db.py
```
Setiap lapisan bisa diuji sendiri; `scripts/run_job.py` menjalankan satu job tanpa Telegram.

### Konfigurasi
`pydantic-settings` membaca `.env`; nilai kosong (`ADMIN_CHAT_ID=`) gagal divalidasi sebagai `int` → perlu `field_validator(mode="before")` yang mengubah `""` → `None`.

### SQLite di produksi kecil
- Cukup untuk single-process bot; **WAL mode** untuk baca/tulis bersamaan.
- `CREATE TABLE IF NOT EXISTS` **tidak** menambah kolom ke tabel lama → butuh migrasi `ALTER TABLE ADD COLUMN` (cek `PRAGMA table_info`).
- Salin DB yang sedang dipakai lewat **backup API** (`src.backup(dst)`), bukan copy file — konsisten walau ada WAL.

### Async, thread, dan matplotlib
- aiogram async; kerja berat (yfinance, chart) dijalankan `asyncio.to_thread`.
- **pyplot tidak thread-safe** → render chart dibungkus `asyncio.Lock`.
- `matplotlib.use("Agg")` untuk server tanpa display.

### Testing & lint
- `pytest` dengan DataFrame sintetis (deterministik via `np.random.default_rng(42)`); DB test memakai `tmp_path` + `monkeypatch` pada `settings.db_path`.
- `ruff` (E, F, I, W, UP; line 100). Test "keamanan HTML" mencegah bug Telegram parse entities terulang.

### Windows-specific
- `cat <<'EOF'` di Git Bash bisa merusak `\n`/`·`/`\$` dalam kode Python → lebih aman tulis file dengan editor/tool lalu jalankan, atau pakai script patch Python.
- `.gitattributes` `* text=auto eol=lf` menghilangkan noise CRLF.

---

## 4. Telegram Bot API (aiogram 3)

- **Long polling**: bot yang menghubungi Telegram; tidak butuh port/domain. Hanya **satu** proses `getUpdates` per bot → `Conflict` kalau dua instance.
- `parse_mode=HTML` lebih mudah daripada MarkdownV2, tapi **semua teks dinamis wajib `html.escape()`** — label "SMA50<SMA200" pernah membuat `can't parse entities: Unsupported start tag`.
- Batas: pesan **4096** karakter (potong di batas baris agar tag tidak terbelah), caption foto **1024** (kirim foto dan teks terpisah).
- `link_preview_is_disabled=True` di `DefaultBotProperties` supaya link berita tidak memunculkan preview.
- Handler fallback (`F.text`) harus didaftarkan **paling akhir**.
- Inline keyboard + `callback_query`; `edit_reply_markup` untuk toggle tombol.
- User yang memblokir bot → `TelegramForbiddenError` → tandai unsubscribe.
- Bot **tidak bisa** menambahkan dirinya jadi admin channel dan tidak bisa membaca jumlah subscriber channel; pengaturan admin lewat aplikasi Telegram. Bot API bisa: `setMyName`, `setMyDescription`, `setMyShortDescription`, `setMyCommands`, `pinChatMessage`; foto profil hanya via BotFather.
- Pencarian bot saat "Add Administrator" di Telegram **Web** sering kosong — pakai aplikasi HP.

---

## 5. Penjadwalan (APScheduler)

- `AsyncIOScheduler(timezone=ZoneInfo("Asia/Jakarta"))`; `CronTrigger(day_of_week="mon-fri", hour=..., minute=...)`.
- Setiap job diawali `if not is_trading_day(): return`.
- Job dinamis (retry, kirim laporan) lewat `DateTrigger` + `replace_existing=True`.
- Bungkus job: catat ke tabel `job_runs` (status/durasi/error) dan kirim alert ke admin bila gagal → observabilitas murah.

---

## 6. LLM di aplikasi nyata

### Pilihan provider
- **Anthropic** (Claude): kualitas tertinggi; SDK `anthropic` — model `claude-opus-5`, adaptive thinking, streaming, prompt caching.
- **Groq free tier** (`openai/gpt-oss-120b`): gratis, cepat, cukup bagus untuk narasi & klasifikasi; model reasoning menghitung token "berpikir" ke `max_tokens` → cek `finish_reason == "length"`.
- **OpenAI-compatible reseller** (SumoPod `https://ai.sumopod.com/v1`): satu key untuk banyak model; dukungan tool-calling bergantung server.
- Pola **adapter** (`llm/providers.py`): ganti provider lewat `.env` tanpa ubah kode.

### Teknik yang terbukti
- **Grounding**: kirim data terstruktur (bar OHLCV, indikator, sinyal, berita) sebagai konteks; instruksi "hanya angka dari data".
- **Guardrail** di prompt: tanpa perintah beli/jual, disclaimer, batas kata.
- **Cache hasil** yang sama untuk semua user (narasi per tanggal) → hemat kuota & konsisten.
- **Klasifikasi batch** (sentimen berita) dengan output JSON: batch kecil (15), parser toleran terhadap JSON terpotong.
- **Memori percakapan** = simpan giliran terakhir per chat di DB, kirim ulang sebagai `messages` sebelumnya.
- Deteksi ticker: huruf **KAPITAL** atau `$kode`, jangan `upper()` seluruh kalimat ("buka" ≠ BUKA).
- Model open-source suka menyelipkan markdown `**` → bersihkan sebelum kirim ke Telegram.
- Selalu siapkan **set pertanyaan evaluasi** (termasuk jebakan) untuk membandingkan model/prompt.

### Biaya
Estimasi per `/ask` dengan Opus 5 ≈ $0,04–0,07; top-up $5–10 cukup untuk uji coba. Rate limit per user wajib sebelum bot dibuka ke orang lain.

---

## 7. Berita & sentimen

- Tidak semua media punya RSS yang hidup — **uji dulu** (`feedparser`): yang aktif CNBC Market, Kontan Investasi, IDX Channel, Liputan6 Saham, Detik Finance; Bisnis.com/Kompas/Investor.id tidak.
- Dedupe berdasarkan hash link; deteksi ticker rule-based (kode + alias nama perusahaan) sebagai fallback LLM.
- Sentimen berita **sengaja tidak** dimasukkan ke skor sinyal sebelum ada bukti backtest.

---

## 8. Docker & deployment

- `Dockerfile` (python:3.12-slim), `entrypoint.sh` (backfill otomatis kalau DB kosong), `docker-compose.yml` (`restart: unless-stopped`, `env_file`, volume `/data`, rotasi log).
- `docker kill`/`stop` dianggap stop manual → tidak di-restart; PID 1 di container kebal sinyal dari dalam — uji auto-restart tidak bisa "dipalsukan" dari dalam container.
- **Platform**: Vercel (serverless) tidak cocok untuk long polling + scheduler; Railway cocok tapi trial habis; **VPS** paling fleksibel dan murah untuk banyak bot.
- Repo private → VPS tidak bisa `git clone`; kirim kode dengan `git archive HEAD | ssh … tar -x` (script `deploy.sh`).

---

## 9. VPS, Linux & keamanan

### SSH & kunci
- Pasangan kunci `ssh-keygen -t ed25519`: privat di laptop (rahasia), publik di server (`~/.ssh/authorized_keys`).
- Alias di `~/.ssh/config` (`Host sahamku-vps`) → cukup `ssh sahamku-vps`.
- Image Ubuntu cloud (Tencent/Cloudeka) menonaktifkan `root`; user default `ubuntu` dengan sudo.
- Matikan login password: `PasswordAuthentication no`. **Jebakan**: sshd memakai nilai **pertama** yang dibaca, dan cloud-init menulis `yes` di `sshd_config.d/50-cloud-init.conf` → file hardening harus bernama lebih awal (`00-hardening.conf`). Verifikasi dengan `sshd -T`.
- Jangan pernah mengirim password/key privat lewat chat; kalau terlanjur, ganti.

### Hardening dasar
`apt upgrade` + `unattended-upgrades`, `ufw` (hanya 22), `fail2ban` (IP publik langsung di-scan dalam menit pertama), user aplikasi terpisah (`deploy`), swap untuk RAM kecil, timezone.

### Membaca `free -m`
`available` (bukan `free`) adalah angka yang penting; `buff/cache` adalah pinjaman kernel yang dilepas saat dibutuhkan; swap terpakai tinggi = tanda RAM kurang.

---

## 10. Hermes Agent (Nous Research)

- Install: `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`; `hermes setup` (pilih **Full setup** untuk bawa key sendiri).
- Provider **Custom endpoint** untuk OpenAI-compatible (SumoPod): base URL `https://ai.sumopod.com/v1`, mode **Chat Completions**, model sesuai daftar `/v1/models`.
- Terminal backend **Local** = agent bisa menjalankan shell di VPS → batasi Telegram ke `TELEGRAM_ALLOWED_USERS` (user ID sendiri), jangan "open access".
- Tool opsional (browser, vision, image gen, TTS) butuh key/RAM tambahan — nyalakan bila perlu.
- Editor prompt (nano) di Hermes: `Ctrl+X` lalu `N` untuk batal; `Ctrl+O`, Enter, `Ctrl+X` untuk kirim.
- Konsep: **streaming** (`stream=True`) mengirim jawaban per chunk untuk UI responsif; **n8n** = automasi low-code yang bisa memakai endpoint OpenAI-compatible.

---

## 11. Cara kerja yang terbukti efektif

- **Rencana → implementasi → test → deploy → verifikasi nyata** untuk tiap fitur; bukti (log job, DB, pesan terkirim) lebih penting daripada "seharusnya jalan".
- **Code review** terpisah setelah MVP menemukan 7 bug nyata (label tersembunyi, race chart, pesan > 4096, dll.).
- Jadikan setiap bug produksi sebagai **test** baru.
- Runbook (`docs/VPS.md`) dan PRD hidup di repo — bukan di kepala.
- Simpan secret hanya di `.env`; `.gitignore` sejak commit pertama; scan staged files sebelum commit pertama.

---

## 12. Glosarium singkat

| Istilah | Arti |
|---|---|
| EOD | End of day — data penutupan harian |
| OHLCV | Open, High, Low, Close, Volume |
| LQ45 / IDX80 | Indeks 45 / 80 saham paling likuid di BEI |
| RSI, MACD, Bollinger, ATR | Indikator momentum / tren / volatilitas |
| Golden/death cross | SMA50 memotong SMA200 ke atas / bawah |
| Backtest | Uji aturan pada data historis |
| Long polling | Bot menarik update dari Telegram secara berulang |
| Long polling conflict | Dua proses menarik update bot yang sama |
| WAL | Write-ahead log SQLite untuk konkurensi |
| SSH key | Pasangan kunci privat/publik untuk login server |
| fail2ban / ufw | Pemblokir brute-force / firewall Linux |
| OpenAI-compatible | API yang meniru format `chat/completions` OpenAI |
| Tool calling | Model meminta program menjalankan fungsi (shell, file, API) |
| Streaming | Jawaban model dikirim bertahap per chunk |

---

## 13. Yang belum & ide lanjutan

- Backup DB otomatis & health check eksternal (uptime monitor).
- Auto-update daftar LQ45/IDX80 dan libur dari BEI.
- Pembayaran tier Pro (Telegram Stars / Midtrans).
- Bahasa Inggris (i18n formatter).
- Web dashboard setelah ≥ 100 subscriber.
- Evaluasi apakah sentimen berita layak masuk skor sinyal (backtest).

*Terakhir diperbarui: 2026-09-12*
