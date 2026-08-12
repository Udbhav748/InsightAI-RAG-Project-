#!/bin/bash
# Pulls the latest code and redeploys the stack. Run this for the initial
# deploy too (after bootstrap.sh + cloning the repo + filling in .env
# files) and for every subsequent update — same command both times.
#
# Usage (from anywhere; the script locates the repo root itself):
#   bash infra/ec2/redeploy.sh              # IP:port only, no TLS
#   bash infra/ec2/redeploy.sh --with-caddy # adds the Caddy overlay (needs
#                                            # a domain already pointed at
#                                            # this instance — see Caddyfile)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.prod.yml)
if [ "${1:-}" = "--with-caddy" ]; then
  COMPOSE_FILES+=(-f docker-compose.caddy.yml)
  echo "==> Including Caddy overlay (TLS via Caddyfile's configured domains)"
fi

for f in backend/.env .env; do
  if [ ! -f "$f" ]; then
    echo "Missing $f — copy it from ${f}.example and fill in real values first." >&2
    exit 1
  fi
done

echo "==> git pull"
git pull

echo "==> Building images"
docker compose "${COMPOSE_FILES[@]}" build

echo "==> Starting stack"
docker compose "${COMPOSE_FILES[@]}" up -d

# Every rebuild leaves the previous image's layers behind as dangling
# images once the tag moves to the new build — harmless to correctness,
# but they accumulate on the instance's (usually small, free-tier) root
# volume over repeated deploys. -f skips the interactive confirmation
# prompt; only dangling (untagged, unused) images/build cache are
# removed, never anything a running container still references.
echo "==> Pruning dangling images and build cache from previous deploys"
docker image prune -f
docker builder prune -f --filter "until=168h"

echo "==> Status"
docker compose "${COMPOSE_FILES[@]}" ps

cat <<'EOF'

==> Health check:
  curl -f http://localhost:8000/health
EOF
