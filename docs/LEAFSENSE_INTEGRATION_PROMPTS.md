# Wiring LeafSense in as the real backend for Leaf Diagnosis

InsightAI-RAG has a fully-built but never-actually-backed integration
point for an external plant-disease vision model called "LeafSense":
`backend/app/services/vision_client.py` makes a real, working HTTP call
to `POST {vision_service_url}/predict/{model_id}`, `rag_service.py`'s
`handle_diagnose` runs the prediction through the same corrective RAG
loop as normal chat, and the frontend (`Diagnose.jsx`) has a complete
upload → analyze → result UI. Nothing was ever missing on InsightAI's
side — but nothing has ever been listening on the other end.

The model behind LeafSense is `Udbhav748/Plant-Disease-Detection-using-DEEP-LEARNING`
on GitHub — confirmed to be the same project: that repo's README
literally names itself "LeafSense," implements the exact "Hybrid CBAM +
EfficientNetB0 + ViT, 38 classes" architecture InsightAI's own
`docs/ARCHITECTURE.md` already documents, and exposes the exact
`POST /predict/{model_id}` contract `vision_client.py` already calls.

The GitHub repo itself has no trained weights (gitignored, no release
asset). But a **complete local working copy** exists at
`C:\Users\Udbhav Narawat\AI-ML-FullStack\02-Projects\Portfolio-Projects\LeafSense\`,
right next to `InsightAI-RAG\` — full backend, frontend, dataset, and
critically `models/cbam_vit_efficientnet_hybrid.h5` (119 MB, present on
disk). Its own `backend/server.log` shows it has already successfully
served real `POST /predict/hybrid-model` calls returning HTTP 200 with
real predictions in the past.

**This is not a training task.** It's "reliably run two already-working
things together and close a few real gaps" — four bundles below, each a
standalone prompt. Agents 1, 2, 3 have zero file overlap and run fully
in parallel. Agent 4 depends on their output to verify against —
sequence it last.

## Key facts every prompt below builds on (already verified)

- Local LeafSense root: `C:\Users\Udbhav Narawat\AI-ML-FullStack\02-Projects\Portfolio-Projects\LeafSense\`
- Its `backend/main.py` runs on `uvicorn.run(app, host='localhost', port=8000)` by default — must be started with `--port 8001` to avoid colliding with InsightAI-RAG's own backend (InsightAI's `config.py` already defaults `vision_service_url` to `http://localhost:8001` expecting exactly this).
- Weights already on disk at `LeafSense/models/cbam_vit_efficientnet_hybrid.h5`; `backend/.env` already has `HYBRID_MODEL_PATH=../models/cbam_vit_efficientnet_hybrid.h5` correctly set.
- `backend/requirements.txt`: `tensorflow==2.21.0`, `keras==3.13.2`, `fastapi`, `uvicorn`, `python-multipart`, `pillow`, `numpy`, `python-dotenv`. Needs Python 3.9–3.13 (TensorFlow constraint) — install into its **own** venv, separate from InsightAI-RAG's backend env, since InsightAI never imports TensorFlow itself and the two apps' dependency sets should stay isolated.
- Known, already-documented gotcha in that repo's own code comments: `tf.keras.models.load_model()` fails on this architecture under Keras 3 (a CBAM merge-node incompatibility). `main.py` already works around this via `model_arch.build_hybrid()` + `model.load_weights()`, not a naive `load_model()`. Nothing to fix here — just don't "helpfully" simplify it back.
- The 38-class label list is hardcoded in **two places** that must stay in sync: LeafSense's own `backend/main.py` (its `CLASS_NAMES`) and InsightAI's `vision_client.py`'s `CLASS_LABEL_MAP` (38 raw-label → (crop, disease) tuples). Both came from the same PlantVillage-style dataset, so they're very likely already identical — but this has never been verified string-for-string, and a silent mismatch degrades gracefully but *wrongly* (falls back to `crop="unknown"` instead of erroring) — exactly the kind of gap that hides itself.
- InsightAI's `Diagnose.jsx` has **no dedicated "vision service is down" messaging** today — a `VisionServiceError` (502, `"Could not reach LeafSense at ..."`) surfaces through the same generic error panel as any other failure.
- Nothing today starts LeafSense automatically alongside InsightAI-RAG — no docker-compose entry, no script.

---

## Agent 1 — Get LeafSense running reliably on its own

**Files**: entirely inside `C:\Users\Udbhav Narawat\AI-ML-FullStack\02-Projects\Portfolio-Projects\LeafSense\` (a separate git repo from InsightAI-RAG). New file: `LeafSense/backend/start.ps1`.

> LeafSense (`LeafSense/backend/main.py`) is a FastAPI service serving a
> trained plant-disease model. It already works — `backend/server.log`
> shows real `POST /predict/hybrid-model` calls returning HTTP 200 — but
> there's no repeatable way to start it, and it must run on port 8001,
> not its hardcoded default of 8000, because it needs to run alongside
> another backend (InsightAI-RAG) that also defaults to port 8000.
>
> `main.py`'s entrypoint is `uvicorn.run(app, host='localhost', port=8000)`
> — that port is hardcoded in *code*, so running `python main.py` will
> always bind 8000 regardless of any external flag. The only way to get
> port 8001 is to invoke uvicorn directly from the CLI instead:
> `uvicorn main:app --host localhost --port 8001`.
>
> `backend/requirements.txt` needs `tensorflow==2.21.0`/`keras==3.13.2`,
> which require Python 3.9–3.13. Create a **dedicated venv** for this
> service (`LeafSense/backend/.venv`) — do not install these into any
> shared/global Python environment, and do not touch InsightAI-RAG's own
> backend environment at all (it never imports TensorFlow itself, and
> should stay that way).
>
> `backend/.env` already correctly has
> `HYBRID_MODEL_PATH=../models/cbam_vit_efficientnet_hybrid.h5`, and the
> weights file already exists on disk at
> `LeafSense/models/cbam_vit_efficientnet_hybrid.h5` (119 MB). Nothing
> needs training — just load and serve.
>
> **Do this:**
> 1. Create `LeafSense/backend/start.ps1`: creates the venv at
>    `LeafSense/backend/.venv` if it doesn't exist (using any available
>    Python 3.9–3.13 interpreter — check what's installed via `py -0` or
>    similar before assuming a specific version is present), installs
>    `-r requirements.txt` into it, then runs
>    `uvicorn main:app --host localhost --port 8001` from inside
>    `LeafSense/backend/`. Print a clear "LeafSense running on
>    http://localhost:8001" line once uvicorn starts.
> 2. Do NOT change `main.py`'s own `if __name__ == "__main__":` block —
>    leave `python main.py`'s behavior (port 8000) untouched; the new
>    script is an *alternative* entrypoint, not a replacement.
> 3. Do NOT touch `model_arch.py`'s `build_hybrid()` + `load_weights()`
>    pattern — it's a deliberate workaround for a documented Keras 3
>    incompatibility with `load_model()` on this architecture. Don't
>    "simplify" it back to `load_model()`.
>
> **Verify:** run the script, then from another terminal:
> `curl http://localhost:8001/ping` → expect `"Hello, I am alive"`.
> `curl http://localhost:8001/model-info` → expect
> `{"num_classes": 38, "model_loaded": true, "test_accuracy": 0.9895, ...}`.
> Then a real prediction: `curl -X POST http://localhost:8001/predict/test -F "file=@<path to any real leaf image>"`
> (use a real image from `LeafSense/data/split_dataset/` if that
> directory has actual files, or any real leaf photo) → expect
> `{"class": "<one of the 38 raw labels>", "confidence": <0-1 float>}`
> with HTTP 200.

---

## Agent 2 — Reconcile the 38-class label mapping

**Files**: `InsightAI-RAG/backend/app/services/vision_client.py`, `InsightAI-RAG/backend/tests/test_vision_client.py`.

> InsightAI-RAG's `backend/app/services/vision_client.py` calls an
> external vision service ("LeafSense") and maps its raw output label
> (e.g. `"Apple___Apple_scab"`) to a plain-language `(crop, disease)`
> tuple via a hardcoded `CLASS_LABEL_MAP: dict[str, tuple[str, str]]`
> with 38 entries. If LeafSense ever returns a raw label that ISN'T a
> key in this dict, `diagnose_image()` doesn't error — it logs a
> `vision_unmapped_class` warning and silently falls through with
> `crop, disease = "unknown", raw_class`. That's a real, self-hiding bug
> risk: the two label lists (this file's `CLASS_LABEL_MAP`, and
> LeafSense's own authoritative class list in its
> `LeafSense/backend/main.py`, a sibling project at
> `C:\Users\Udbhav Narawat\AI-ML-FullStack\02-Projects\Portfolio-Projects\LeafSense\backend\main.py`)
> were written independently and have never been diffed against each
> other string-for-string.
>
> **Do this:**
> 1. Open `LeafSense/backend/main.py` and find its class list (a
>    hardcoded Python list of 38 raw strings, comment: "Class order must
>    match `train_ds.class_names`... do not reorder"). This is the
>    authoritative source — LeafSense's `/predict` endpoint can only ever
>    return one of these exact strings.
> 2. Open `vision_client.py`'s `CLASS_LABEL_MAP` and list its 38 keys.
> 3. Diff the two sets of strings exactly (watch for subtle mismatches:
>    underscores vs spaces, the comma in labels like
>    `"Pepper,_bell___Bacterial_spot"`, trailing underscores like
>    `"Corn_(maize)___Common_rust_"`). Every string LeafSense's list
>    contains must exist as a key in `CLASS_LABEL_MAP`.
> 4. Fix any mismatch found — `CLASS_LABEL_MAP`'s keys must exactly match
>    LeafSense's real strings (LeafSense's list is the source of truth,
>    since it's what the model actually outputs).
> 5. Add a test to `backend/tests/test_vision_client.py` (create it if it
>    doesn't exist, following this repo's existing test-file conventions
>    — check an existing test file in the same directory for style) that
>    hardcodes the full 38-string list copied from LeafSense's
>    `main.py` at the time you write this test, and asserts every one is
>    a key in `CLASS_LABEL_MAP`. This is what catches future drift if
>    either list changes later without the other being updated.
>
> **Verify:** `pytest backend/tests/test_vision_client.py` passes; the
> full backend `pytest` suite stays green.

---

## Agent 3 — Frontend messaging for a down/slow vision service

**Files**: `InsightAI-RAG/frontend/src/pages/Diagnose.jsx`, `InsightAI-RAG/frontend/src/utils/errorMessage.js`, `InsightAI-RAG/frontend/src/components/diagnose/DiagnosisResult.jsx` (read-only reference for existing icon/style conventions).

> When InsightAI-RAG's vision service (LeafSense) is unreachable, the
> backend raises `VisionServiceError` (HTTP 502, `error_code:
> "VISION_SERVICE_ERROR"`, `taxonomy_category: "tool"`, message like
> `"Could not reach LeafSense at http://localhost:8001: ..."`). Today,
> `frontend/src/pages/Diagnose.jsx`'s error state just displays whatever
> `getErrorMessage()` (`frontend/src/utils/errorMessage.js`) returns —
> which for any `AppError` is a generic string suffixed with
> `"[ERROR_CODE] (taxonomy)"`. A user sees a raw, confusing string like
> `"Could not reach LeafSense at http://localhost:8001: ... [VISION_SERVICE_ERROR] (tool)"`
> instead of something that tells them what's actually going on.
>
> **Do this:**
> 1. Find where `Diagnose.jsx` (or its `useDiagnose` hook,
>    `frontend/src/hooks/useDiagnose.js`) receives the error and sets
>    `errorMessage`. Add a check: if the underlying error's
>    `error_code === 'VISION_SERVICE_ERROR'` (check the exact response
>    shape the backend sends via its error handler — it's a JSON body
>    with `error_code` at the top level, per `app/core/error_handlers.py`'s
>    convention already used elsewhere in this app), set a distinct,
>    friendlier message instead: something like "The plant diagnosis
>    service isn't running right now. Please try again in a moment."
>    Do this either inside `getErrorMessage()` itself (as a new special
>    case, following whatever pattern it already uses for other
>    error-code-specific messages, if any exist) or locally in
>    `Diagnose.jsx`/`useDiagnose.js` — pick whichever matches this file's
>    existing structure once you've read it.
> 2. Reuse existing icon/color conventions already imported in
>    `Diagnose.jsx`/`DiagnosisResult.jsx` (check what's already pulled
>    from `lucide-react` in these files) for any visual treatment — don't
>    add a new icon library or invent a new color token.
> 3. Keep the existing Try again / Choose another photo buttons exactly
>    as they are — this is a messaging fix, not a new interaction flow.
> 4. Every other error type (e.g. a client-side oversized-image
>    rejection, a generic 500) must keep showing its own distinct
>    message, unaffected by this change.
>
> **Verify:** with LeafSense NOT running, go through the Diagnose flow
> in the browser with a real image — confirm the friendly message
> appears, not a raw error-code string. Then trigger a different error
> (e.g. select a file over the 20MB client-side limit) and confirm its
> own distinct message still shows correctly.

---

## Agent 4 — Orchestration + full live end-to-end verification (run last)

**Files**: `InsightAI-RAG/README.md` (its existing "running locally" section), `InsightAI-RAG/backend/.env.example` (comment-only update if needed). No application code changes.

> Agents 1-3 make LeafSense startable (`LeafSense/backend/start.ps1`),
> fix its class-label mapping (`vision_client.py`), and fix the
> frontend's error messaging for when it's down. Your job: make running
> both projects together a documented, repeatable two-step process, and
> prove the whole flow actually works end to end.
>
> **Do this:**
> 1. Read `InsightAI-RAG/README.md`'s current "running locally"
>    instructions. Add a short, clearly-marked optional section: "Leaf
>    Diagnosis (optional)" — explaining that this feature needs
>    LeafSense running separately, with the exact two commands: start
>    InsightAI-RAG's own backend/frontend as already documented, then in
>    a third terminal, run `LeafSense/backend/start.ps1` (from Agent 1).
>    State plainly that this is optional — the rest of the app works
>    fully without it.
> 2. **Do NOT add a `leafsense` service to `docker-compose.yml`.**
>    TensorFlow's installed footprint (several hundred MB) directly
>    conflicts with this project's own established "low local storage"
>    constraint (the same reasoning that kept image-captioning/vision-QA
>    off by default earlier this session). A native, documented two-
>    terminal workflow (step 1) gets the same result without baking a
>    multi-hundred-MB TensorFlow layer into a container image everyone
>    building this project pulls, whether they use Leaf Diagnosis or
>    not. State this reasoning in your own commit/PR description so it's
>    not silently revisited later.
> 3. Check `backend/.env.example`'s existing `VISION_SERVICE_URL`/
>    `VISION_SERVICE_API_KEY` documentation comments — update only if
>    anything about the actual run command changes what a user needs to
>    set (the default `http://localhost:8001` should already be
>    correct and probably needs no change).
> 4. **Live verification, after Agents 1-3's changes exist:** start
>    InsightAI-RAG's backend and frontend normally. Start LeafSense via
>    `start.ps1`. In the browser, go to `/diagnose`, upload a real leaf
>    photo (there are real images inside `LeafSense/data/split_dataset/`
>    if populated — check first; otherwise source one real photo for a
>    crop this app's own document corpus covers, per its README's own
>    note that the corpus "currently only covers apple, corn, potato,
>    tomato, and peach" — so the RAG half of the answer has something
>    to retrieve too, not just the raw prediction). Confirm: a real
>    crop/disease prediction with a confidence score renders, and (for
>    an apple/corn/potato/tomato/peach photo) the RAG-grounded answer
>    text appears too, not just the raw classification.
> 5. Then stop LeafSense and repeat the same upload — confirm Agent 3's
>    friendly "service isn't running" message appears instead of a raw
>    error or a crash.
>
> **Verify:** the full backend `pytest` suite still passes (no code
> changes from this agent should affect it, but confirm anyway); attach
> a screenshot of the successful live diagnosis and the down-service
> friendly-error state to whatever you report back.
