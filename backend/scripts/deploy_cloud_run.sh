#!/usr/bin/env bash
# Build, push, and deploy the InsightAI-RAG backend to Cloud Run.
#
# Used both for a manual deploy from your own machine and by
# .github/workflows/deploy.yml — kept as one script so the two paths can't
# drift apart. See docs/OPERATIONS.md's "Deploying to Cloud Run" section for
# the one-time GCP setup (project, Artifact Registry repo, GCS buckets,
# secrets, Workload Identity Federation) this script assumes already exists;
# it only builds/pushes/deploys, it doesn't provision infrastructure.
#
# Required environment variables:
#   GCP_PROJECT              GCP project id
#   GCP_REGION                Cloud Run region, e.g. us-central1
#   ARTIFACT_REGISTRY_REPO    Artifact Registry repo name (already created)
#   BUCKET_VECTOR_STORE       GCS bucket backing backend/vector_store/
#   BUCKET_UPLOADS            GCS bucket backing backend/uploads/
#   FRONTEND_URL              Deployed frontend origin (Vercel/Cloudflare Pages),
#                             becomes the backend's CORS allowlist
#
# Optional:
#   IMAGE_TAG                 Defaults to the current git commit SHA
#   SERVICE_NAME               Defaults to insightai-rag-backend
#
# Usage (from anywhere — paths below resolve relative to this script's own
# location, not your current directory):
#   backend/scripts/deploy_cloud_run.sh              # build, push, deploy
#   backend/scripts/deploy_cloud_run.sh --print-only  # print the gcloud
#                                                      # command, touch
#                                                      # nothing (no docker
#                                                      # build/push either) —
#                                                      # check the shape
#                                                      # before it hits your
#                                                      # account
#
# Assumes you're already authenticated (`gcloud auth login` or, in CI, the
# Workload Identity Federation step in deploy.yml) and secrets
# (gemini-api-key, api-key, ...) already exist in Secret Manager — see
# docs/OPERATIONS.md.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PRINT_ONLY=false
if [[ "${1:-}" == "--print-only" ]]; then
  PRINT_ONLY=true
fi

: "${GCP_PROJECT:?Set GCP_PROJECT (your GCP project id)}"
: "${GCP_REGION:?Set GCP_REGION (e.g. us-central1)}"
: "${ARTIFACT_REGISTRY_REPO:?Set ARTIFACT_REGISTRY_REPO}"
: "${BUCKET_VECTOR_STORE:?Set BUCKET_VECTOR_STORE}"
: "${BUCKET_UPLOADS:?Set BUCKET_UPLOADS}"
: "${FRONTEND_URL:?Set FRONTEND_URL (the deployed frontend origin, for CORS)}"

SERVICE_NAME="${SERVICE_NAME:-insightai-rag-backend}"
IMAGE_TAG="${IMAGE_TAG:-$(git -C "${BACKEND_DIR}" rev-parse --short HEAD)}"
IMAGE="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT}/${ARTIFACT_REGISTRY_REPO}/${SERVICE_NAME}:${IMAGE_TAG}"

DEPLOY_CMD=(
  gcloud run deploy "${SERVICE_NAME}"
  --image "${IMAGE}"
  --project "${GCP_PROJECT}"
  --region "${GCP_REGION}"
  --platform managed
  --allow-unauthenticated
  --execution-environment gen2
  # --max-instances=1 is a correctness requirement, not a cost tuning knob:
  # this app assumes one process holds the one in-memory FAISS index
  # (query.py's get_vector_store(), @lru_cache(maxsize=1)), and GCS FUSE
  # (below) provides no cross-writer file locking — a second concurrent
  # instance would silently corrupt the index. See docs/DESIGN_REVIEW.md Q9
  # and docs/OPERATIONS.md's "Deploying to Cloud Run" section.
  --max-instances=1
  --add-volume "name=vector-store,type=cloud-storage,bucket=${BUCKET_VECTOR_STORE},readonly=false"
  --add-volume-mount "volume=vector-store,mount-path=/app/vector_store"
  --add-volume "name=uploads,type=cloud-storage,bucket=${BUCKET_UPLOADS},readonly=false"
  --add-volume-mount "volume=uploads,mount-path=/app/uploads"
  --update-secrets "GEMINI_API_KEY=gemini-api-key:latest,API_KEY=api-key:latest"
  --set-env-vars "FRONTEND_URL=${FRONTEND_URL}"
)

if [[ "${PRINT_ONLY}" == "true" ]]; then
  echo "Image that would be built and pushed: ${IMAGE}"
  echo "Command that would run:"
  printf '  %q' "${DEPLOY_CMD[@]}"
  echo
  exit 0
fi

echo "Building ${IMAGE}..."
docker build -t "${IMAGE}" "${BACKEND_DIR}"

echo "Pushing ${IMAGE}..."
docker push "${IMAGE}"

echo "Deploying ${SERVICE_NAME} to Cloud Run..."
"${DEPLOY_CMD[@]}"
