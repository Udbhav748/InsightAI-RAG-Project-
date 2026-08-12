#!/bin/bash
# One-time OS-level setup for a fresh EC2 instance (tested against Ubuntu
# 22.04/24.04 AMIs). Installs Docker, adds swap, and stops there —
# deliberately doesn't touch the repo or the app stack. Run this once via
# SSH, then clone the repo and use redeploy.sh for the actual app deploy.
#
# Usage: scp this file to the instance (or paste it in), then:
#   chmod +x bootstrap.sh && sudo ./bootstrap.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root (sudo ./bootstrap.sh)." >&2
  exit 1
fi

echo "==> Installing Docker Engine + Compose plugin"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
else
  echo "Docker already installed, skipping."
fi

# Lets the instance's default non-root user (ubuntu on Ubuntu AMIs) run
# docker without sudo. Harmless if the user doesn't exist or is already
# in the group.
if id ubuntu >/dev/null 2>&1; then
  usermod -aG docker ubuntu || true
fi

echo "==> Swap"
# This project has a documented history of OOM under tight memory (see
# docs/OPERATIONS.md's "Memory" section — the backend alone peaked around
# ~480MB on Render's 512MB tier, and that's before Postgres, the frontend's
# nginx, and Caddy each add their own share). EC2's free-tier t2.micro/
# t3.micro instances have only 1GB RAM, no swap by default — a 2GB
# swapfile is cheap insurance against an OOM-kill under a burst rather than
# a graceful slowdown. Skips cleanly if swap already exists (re-running
# this script, or an AMI that already provisions one).
if [ "$(swapon --show | wc -l)" -eq 0 ]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  if ! grep -q '/swapfile' /etc/fstab; then
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
  fi
  echo "2G swapfile created and enabled."
else
  echo "Swap already active, skipping."
fi

cat <<'EOF'

==> Done. Next steps (as the ubuntu user, not root):
  1. git clone <this repo's URL> insightai-rag && cd insightai-rag
  2. cp backend/.env.example backend/.env   # fill in real secrets
  3. cp .env.example .env                   # set VITE_API_BASE_URL
  4. bash infra/ec2/redeploy.sh

If you added yourself to the docker group just now, log out and back in
(or run `newgrp docker`) before step 4 — group membership doesn't apply
to your current shell session automatically.
EOF
