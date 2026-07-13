<div align="center">

# InsightAI-RAG

**Upload a PDF. Ask it questions. Get answers grounded in what it actually says.**

InsightAI-RAG is a full-stack Retrieval-Augmented Generation app: a FastAPI backend that chunks and embeds your documents into a FAISS vector index, and a React SPA for uploading files and chatting with them — with every answer traceable back to the source passage.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![FAISS](https://img.shields.io/badge/FAISS-vector%20search-4B8BBE)
![Gemini](https://img.shields.io/badge/LLM-Gemini-8E75B2)

</div>

<br>

![Home screen](docs/screenshots/home.png)

## Table of contents

- [How it works](#how-it-works)
- [Features](#features)
- [Screenshots](#screenshots)
- [Tech stack](#tech-stack)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Project structure](#project-structure)
- [Roadmap](#roadmap)
- [License](#license)

## How it works

```
                    ┌──────────────┐
   PDF upload  ───▶ │  PyMuPDF     │  extract text per page
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │  Chunking    │  langchain-text-splitters
                    │  (1000 chars,│  200 char overlap
                    │   overlap)   │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │  Embeddings  │  Sentence Transformers
                    │              │  (all-MiniLM-L6-v2)
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │  FAISS index │  persisted to disk,
                    │ (IndexFlatIP)│  cosine similarity search
                    └──────┬───────┘
                           ▼
   Question    ───▶ ┌──────────────┐     top-k chunks     ┌──────────────┐
   in chat          │  Retrieval   │ ───────────────────▶ │    Gemini    │ ──▶ Answer + cited sources
                     └──────────────┘                      └──────────────┘
```

A document uploaded through `/upload` is chunked, embedded, and written into the same in-memory FAISS index that `/chat` queries — so a new document is searchable immediately, no reload or reindex step required.

## Features

- **Drag-and-drop PDF ingestion** — validated for type and size, chunked with configurable overlap, embedded, and indexed in one request.
- **Grounded chat** — every answer is generated only from retrieved chunks, with the source document and matched excerpts shown alongside the response.
- **Conversational query routing** — small talk and meta-questions are handled without spending a retrieval + generation round trip on them.
- **Document management** — browse everything you've uploaded, see page/chunk counts, and delete a document (which also removes its vectors from the index).
- **Light & dark themes**, keyboard-friendly chat input, and toast notifications throughout.
- **Structured JSON logging** and a typed exception hierarchy that maps domain errors (corrupted PDF, empty vector store, LLM timeout, ...) to the correct HTTP status code.

## Screenshots

<table>
<tr>
<td width="50%">

**Chat, grounded in your documents**
Every answer links back to the excerpt it came from.

![Chat](docs/screenshots/chat.png)

</td>
<td width="50%">

**Upload**
Drag, drop, done — chunked and embedded in seconds.

![Upload](docs/screenshots/upload.png)

</td>
</tr>
<tr>
<td width="50%">

**Documents**
Everything in your knowledge base, at a glance.

![Documents](docs/screenshots/documents.png)

</td>
<td width="50%">

**Settings**
Light or dark, your call.

![Settings](docs/screenshots/settings.png)

</td>
</tr>
</table>

## Tech stack

| | |
|---|---|
| **Backend** | FastAPI, Pydantic v2 (`pydantic-settings`), Uvicorn |
| **Document parsing** | PyMuPDF |
| **Chunking** | `langchain-text-splitters` |
| **Embeddings** | Sentence Transformers (`all-MiniLM-L6-v2`) |
| **Vector store** | FAISS (`IndexFlatIP`, cosine similarity) |
| **LLM** | Google Gemini (`google-genai`) |
| **Frontend** | React 18, Vite, Tailwind CSS, Framer Motion, React Router |
| **Testing** | Pytest |

## Getting started

### Prerequisites

- Python 3.11+
- Node.js 18+
- A [Gemini API key](https://ai.google.dev/)

### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env        # then set GEMINI_API_KEY
uvicorn app.main:app --reload
```

The API is now running at `http://localhost:8000` (interactive docs at `/docs`).

### Frontend

```bash
cd frontend
npm install
cp .env.example .env        # defaults to http://localhost:8000
npm run dev
```

The app is now running at `http://localhost:5173`.

### Running tests

```bash
cd backend
pytest
```

## Configuration

All backend configuration lives in `backend/.env` (see `backend/.env.example`), loaded via `pydantic-settings`:

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | **Required.** Your Google Gemini API key. |
| `FRONTEND_URL` | `http://localhost:5173` | Origin allowed by CORS. |
| `MAX_UPLOAD_SIZE_MB` | `20` | Maximum accepted PDF size. |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1000` / `200` | Characters per chunk / overlap between chunks. |
| `EMBEDDING_MODEL_NAME` | `all-MiniLM-L6-v2` | Sentence Transformers model. |
| `RETRIEVAL_TOP_K` | `5` | Chunks retrieved per query by default. |
| `RETRIEVAL_MIN_SCORE` | `0.3` | Minimum cosine similarity to keep a retrieved chunk. |
| `GEMINI_MODEL_NAME` | `gemini-3.5-flash` | Gemini model used for answer generation. |
| `GEMINI_TIMEOUT_SECONDS` | `30` | Timeout for Gemini API calls. |

The frontend reads a single variable from `frontend/.env`:

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend base URL. |

## API reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Liveness check. |
| `POST` | `/upload` | Upload a PDF — extracts, chunks, embeds, and indexes it. |
| `DELETE` | `/documents/{document_id}` | Remove a document and its vectors from the index. |
| `POST` | `/chat` | Ask a question; returns an answer grounded in retrieved chunks. |

**`POST /chat`** request body:

```json
{
  "query": "What is a project according to the PMP document?",
  "top_k": 5,
  "min_score": 0.3
}
```

response:

```json
{
  "answer": "A project is a temporary endeavor undertaken to create a unique product, service, or result...",
  "retrieved_chunks": [
    { "chunk_id": "...", "document_id": "...", "text": "...", "score": 0.65, "metadata": { "...": "..." } }
  ],
  "sources": ["ae845151-86b1-41e8-a63b-69289b88c67a"],
  "processing_time": 18.24
}
```

Full interactive documentation (generated by FastAPI) is available at `/docs` while the backend is running.

## Project structure

```
InsightAI-RAG/
├── backend/
│   └── app/
│       ├── api/v1/routes/     # health, documents, query
│       ├── core/              # config, logging, exceptions, error handlers
│       ├── models/            # Pydantic schemas
│       └── services/          # chunking, embedding, FAISS store, RAG pipeline, Gemini client
└── frontend/
    └── src/
        ├── pages/              # Home, Upload, Chat, Documents, Settings
        ├── components/         # chat/, upload/, layout/, ui/
        ├── hooks/              # useChat, useUpload, useTheme, useToast
        └── services/           # api client, chat/document services
```

## Roadmap

- [ ] Persistent, server-side document history (currently tracked per-browser)
- [ ] Multi-document collections / workspaces
- [ ] Streaming chat responses
- [ ] Support for additional file types beyond PDF

## License

MIT © [Udbhav Narawat](LICENSE)
