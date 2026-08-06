FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# faiss-cpu and torch (pulled in by sentence-transformers) link against
# libgomp at runtime, which python:3.11-slim doesn't ship by default.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# sentence-transformers pulls in torch, and plain `pip install torch` on
# Linux defaults to the CUDA build — several GB of GPU libraries this
# CPU-only container will never use. Installing the CPU wheel first
# satisfies that dependency before requirements.txt gets a chance to
# trigger the CUDA one.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/uploads /app/vector_store \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
