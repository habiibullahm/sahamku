#!/usr/bin/env bash
# Setup VPS Ubuntu 22.04/24.04 untuk Sahamku (sekali jalan, sebagai root).
#
#   ssh root@IP
#   curl -fsSL https://raw.githubusercontent.com/habiibullahm/sahamku/main/scripts/vps_setup.sh -o setup.sh
#   bash setup.sh
#
# Yang dilakukan: update, user `deploy` (sudo, docker), SSH key, hardening SSH (opsional),
# ufw (22 saja), fail2ban, swap 2 GB, timezone Asia/Jakarta, Docker, clone repo ke /opt/sahamku.
# Setelah selesai: isi /opt/sahamku/.env lalu `docker compose up -d`.

set -euo pipefail

REPO="https://github.com/habiibullahm/sahamku.git"
APP_DIR="/opt/sahamku"
DEPLOY_USER="deploy"
SWAP_GB=2

if [[ $EUID -ne 0 ]]; then echo "Jalankan sebagai root"; exit 1; fi

echo "==> [1/8] Update sistem"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q && apt-get upgrade -yq
apt-get install -yq ca-certificates curl git ufw fail2ban unattended-upgrades

echo "==> [2/8] Timezone Asia/Jakarta"
timedatectl set-timezone Asia/Jakarta

echo "==> [3/8] Swap ${SWAP_GB}G"
if ! swapon --show | grep -q swapfile; then
  fallocate -l "${SWAP_GB}G" /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl -w vm.swappiness=10 >/dev/null && echo 'vm.swappiness=10' >> /etc/sysctl.conf
fi

echo "==> [4/8] Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

echo "==> [5/8] User ${DEPLOY_USER}"
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
  usermod -aG sudo,docker "$DEPLOY_USER"
  echo "${DEPLOY_USER} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/90-${DEPLOY_USER}
fi
# salin authorized_keys root (kalau login pakai key) ke deploy
if [[ -f /root/.ssh/authorized_keys ]]; then
  install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/${DEPLOY_USER}/.ssh"
  cp /root/.ssh/authorized_keys "/home/${DEPLOY_USER}/.ssh/"
  chown "$DEPLOY_USER:$DEPLOY_USER" "/home/${DEPLOY_USER}/.ssh/authorized_keys"
  chmod 600 "/home/${DEPLOY_USER}/.ssh/authorized_keys"
fi

echo "==> [6/8] Firewall + fail2ban"
ufw allow OpenSSH >/dev/null
ufw --force enable >/dev/null
cat > /etc/fail2ban/jail.local <<'EOF'
[sshd]
enabled = true
maxretry = 5
bantime = 1h
EOF
systemctl enable --now fail2ban
dpkg-reconfigure -f noninteractive unattended-upgrades >/dev/null 2>&1 || true

echo "==> [7/8] Clone repo ke ${APP_DIR}"
if [[ ! -d "$APP_DIR/.git" ]]; then
  git clone "$REPO" "$APP_DIR"
else
  git -C "$APP_DIR" pull --ff-only
fi
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"
mkdir -p "$APP_DIR/data" && chown "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR/data"
[[ -f "$APP_DIR/.env" ]] || cp "$APP_DIR/.env.example" "$APP_DIR/.env"

echo "==> [8/8] Selesai"
cat <<EOF

Langkah berikutnya:
  1. Isi konfigurasi:   nano ${APP_DIR}/.env
       TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID, CHANNEL_ID, GROQ_API_KEY, GROQ_MODEL, UNIVERSE
  2. Matikan bot di laptop (docker compose down) — Telegram hanya izinkan satu polling.
  3. Jalankan:          cd ${APP_DIR} && docker compose up -d --build
     (start pertama backfill 3 tahun, ±1-2 menit)  lalu:  docker compose logs -f
  4. (Opsional, disarankan) Setelah yakin bisa login sebagai '${DEPLOY_USER}' dengan SSH key:
       sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/; s/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
       systemctl restart ssh
EOF
