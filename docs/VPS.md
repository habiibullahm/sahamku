# Runbook VPS — Sahamku

VPS: Ubuntu 24.04, 2 vCPU / 2 GB RAM / 40 GB, Jakarta (Cloudeka via SumoPod). User login `ubuntu`
(root dinonaktifkan oleh image), akses hanya dengan SSH key. Aplikasi di `/opt/sahamku`, dimiliki
user `deploy`, berjalan sebagai container Docker `sahamku-bot`.

## Ringkasan perintah harian

| Tujuan | Perintah (dari laptop) |
|---|---|
| Masuk ke VPS | `ssh sahamku-vps` |
| Deploy kode terbaru (setelah commit) | `bash scripts/deploy.sh` |
| Lihat log bot | `ssh sahamku-vps "cd /opt/sahamku && sudo docker compose logs -f"` |
| Restart bot | `ssh sahamku-vps "cd /opt/sahamku && sudo docker compose restart"` |
| Ubah konfigurasi | `ssh sahamku-vps "sudo nano /opt/sahamku/.env"` lalu `sudo docker compose up -d` |
| Cek status | `ssh sahamku-vps "sudo docker ps; free -m; df -h /"` |
| Backup DB ke laptop | `ssh sahamku-vps "sudo cat /opt/sahamku/data/sahamku.db" > backup.db` |

## Setup dari nol (apa yang dilakukan dan kenapa)

### 0. Akses SSH dengan key (laptop)

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/sahamku_vps -C "sahamku-laptop"
# daftarkan kunci publik ke VPS — satu-satunya langkah yang butuh password
type $env:USERPROFILE\.ssh\sahamku_vps.pub | ssh ubuntu@IP "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
```

`~/.ssh/config`:

```
Host sahamku-vps
  HostName 43.157.227.176
  User ubuntu
  IdentityFile ~/.ssh/sahamku_vps
  IdentitiesOnly yes
```

Kunci privat `~/.ssh/sahamku_vps` adalah satu-satunya jalan masuk setelah login password dimatikan —
simpan cadangannya di password manager. Ganti laptop: tambahkan key baru ke `authorized_keys` dulu.

### 1–6. `scripts/vps_setup.sh` (dijalankan sekali sebagai root/sudo)

| # | Langkah | Kenapa |
|---|---|---|
| 1 | `apt update && upgrade`, install `curl git ufw fail2ban unattended-upgrades` | Tutup celah yang sudah diketahui; patch keamanan otomatis tiap hari |
| 2 | `timedatectl set-timezone Asia/Jakarta` | Log/`date` di VPS dalam WIB (bot sendiri sudah pakai WIB eksplisit) |
| 3 | Swap 2 GB (`/swapfile`, `swappiness=10`) | RAM hanya 2 GB; mencegah OOM kill saat backfill/chart bersamaan |
| 4 | Docker (`get.docker.com`), `systemctl enable docker` | Image sama dengan laptop; container `restart: unless-stopped` hidup lagi setelah reboot |
| 5 | User `deploy` (grup `sudo`, `docker`) | Pemilik `/opt/sahamku`; aplikasi tidak dimiliki root |
| 6 | `ufw allow OpenSSH; ufw enable`; `fail2ban` sshd (5× gagal → blokir 1 jam) | Bot tidak membuka port (long polling keluar). Satu-satunya pintu = SSH; IP publik langsung di-scan bot dalam hitungan menit |

Cara menjalankan (repo private → kirim script lewat scp, bukan curl raw):

```bash
scp scripts/vps_setup.sh sahamku-vps:/tmp/setup.sh
ssh sahamku-vps "sudo bash /tmp/setup.sh"
```

Langkah 7 di script (`git clone`) gagal untuk repo private — abaikan, lanjut ke bagian berikut.

### 7. Kode aplikasi

```bash
git archive --format=tar HEAD | ssh sahamku-vps "sudo mkdir -p /opt/sahamku && sudo tar -x -C /opt/sahamku -f - && sudo chown -R deploy:deploy /opt/sahamku"
```

Mengirim snapshot commit terakhir lewat pipa SSH; VPS tidak perlu kredensial GitHub.
Dibungkus di `scripts/deploy.sh` (kirim + `docker compose up -d --build` + cek log).

### 8. Konfigurasi & data

```bash
scp .env sahamku-vps:/tmp/sahamku.env && ssh sahamku-vps "sudo mv /tmp/sahamku.env /opt/sahamku/.env && sudo chmod 600 /opt/sahamku/.env && sudo chown deploy:deploy /opt/sahamku/.env"
```

DB dari laptop (opsional, membawa watchlist/alert/user). Salin lewat SQLite backup API agar konsisten:

```bash
python -c "import sqlite3; s=sqlite3.connect('data/sahamku.db'); d=sqlite3.connect('snap.db'); s.backup(d)"
scp snap.db sahamku-vps:/tmp/sahamku.db && ssh sahamku-vps "sudo mkdir -p /opt/sahamku/data && sudo mv /tmp/sahamku.db /opt/sahamku/data/sahamku.db && sudo chown -R deploy:deploy /opt/sahamku/data"
```

Tanpa DB, entrypoint container backfill 3 tahun otomatis (±2 menit).

### 9. Pindah polling

```bash
docker compose down                                   # di laptop — WAJIB dulu
ssh sahamku-vps "cd /opt/sahamku && sudo docker compose up -d --build"
```

Telegram hanya mengizinkan satu `getUpdates` per bot; dua instance → error `Conflict`.

### 10. Verifikasi

```bash
ssh sahamku-vps "cd /opt/sahamku && sudo docker compose logs --since 2m | grep -E 'Run polling|next run|Traceback'"
ssh sahamku-vps "sudo docker inspect sahamku-bot --format 'status={{.State.Status}} restart={{.HostConfig.RestartPolicy.Name}}'"
```

Lalu `/admin` di Telegram → statistik harus berasal dari VPS.

### 11. Hardening akhir (setelah login key terbukti lancar)

```bash
ssh sahamku-vps "sudo passwd ubuntu"      # ganti password bawaan provider
ssh sahamku-vps "sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config && sudo systemctl restart ssh"
```

## Troubleshooting

| Gejala | Penyebab umum | Tindakan |
|---|---|---|
| `Permission denied (publickey,password)` | Key belum di `authorized_keys` user yang benar, atau user salah (`root` vs `ubuntu`) | Ulangi langkah 0 dengan user `ubuntu` |
| `Connection timed out` | Firewall provider / VPS masih provisioning | Tunggu; cek security group di dashboard mengizinkan port 22 |
| Log: `Conflict: terminated by other getUpdates` | Dua instance bot hidup | `docker compose down` di laptop |
| Container restart terus | `.env` salah/kosong | `sudo docker compose logs --tail 50`; perbaiki `.env`; `up -d` |
| Job jam tertentu tidak jalan | Timezone/hari libur | `date` harus WIB; cek `IDX_HOLIDAYS` di `universe.py` |
| Memori penuh | Backfill besar/chart | `free -m`; swap sudah 2 GB; upgrade RAM bila `used` konsisten > 1,5 GB |
| Setelah reboot bot tidak naik | Docker tidak `enabled` | `sudo systemctl enable --now docker`; container punya `restart: unless-stopped` |

## Menambah bot/aplikasi lain di VPS yang sama

Struktur yang disarankan: satu folder per aplikasi dengan `docker-compose.yml` dan `.env` masing-masing
(`/opt/<nama-app>`), semua dengan `restart: unless-stopped`. Untuk agent Claude Code: user Linux terpisah
(`dev`) + `tmux`, Node.js LTS, dan API key terpisah dengan spend limit.
