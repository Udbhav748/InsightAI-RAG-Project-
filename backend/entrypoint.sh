#!/bin/sh
set -e

# AWS_LAMBDA_FUNCTION_NAME is a Lambda-reserved env var, always set inside a
# real Lambda execution environment and never set locally or in
# docker-compose.yml — so this whole block is a no-op outside Lambda.
if [ -n "$AWS_LAMBDA_FUNCTION_NAME" ]; then
  # Lambda's container filesystem is read-only outside /tmp. This app's
  # three write paths (upload_service.py, faiss_vector_store.py,
  # feedback_service.py) always resolve to /app/<name> — never a
  # configurable absolute path — so they're redirected onto /tmp here,
  # once, at container start, instead of by changing application code.
  # Python's file I/O follows symlinks transparently, so no code changes
  # are needed for this to work.
  mkdir -p /tmp/uploads /tmp/vector_store /tmp/feedback
  rm -rf /app/uploads /app/vector_store /app/feedback
  ln -s /tmp/uploads /app/uploads
  ln -s /tmp/vector_store /app/vector_store
  ln -s /tmp/feedback /app/feedback

  # huggingface_hub writes a filelock next to cached model weights even on
  # a pure read — fails under /app's now-read-only filesystem even though
  # the model (baked into the image at build time) needs no re-download.
  # Copying the already-baked cache into /tmp once per cold start keeps
  # the "no network fetch at startup" property while giving the lock file
  # somewhere writable to live.
  mkdir -p /tmp/hf_cache
  cp -r /app/.cache/huggingface /tmp/hf_cache/huggingface
  export HF_HOME=/tmp/hf_cache/huggingface
  export TRANSFORMERS_CACHE=/tmp/hf_cache/huggingface
  export SENTENCE_TRANSFORMERS_HOME=/tmp/hf_cache/huggingface
  export HF_HUB_OFFLINE=1
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
