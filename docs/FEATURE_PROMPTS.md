# InsightAI-RAG: 13 standalone build prompts for 4 parallel agents

Thirteen features, evaluated this session against three hard
constraints (zero ongoing cost, freely deployable, low local storage/
dependency footprint) — 5 traced to two external repos
(`docs/EXTERNAL_FEATURES_PLAN.md`), 6 fixing real gaps found while
re-reading this codebase's own `rag_service.py`, 3 agentic-AI additions.
Grouped into 4 bundles, one per agent, to minimize cross-agent file
collisions (a perfectly clash-free split isn't possible at this size —
`rag_service.py` is where nearly every backend RAG-quality feature
naturally lives — see "Shared files" below for exactly which files
overlap and how to handle it).

**Each prompt below is fully standalone.** Give an agent only its own
bundle; it does not need to read this repo's other docs, re-explore the
codebase, or open kotaemon/onyx to execute its prompts — every fact
needed (exact file, function, line, signature) is already stated.

## Ground rules (apply to every prompt, all 4 agents)

- **Zero paid cost.** No new paid API, no new heavy model download.
  Every LLM call used by these features reuses the existing
  `LLMClient`/provider already configured (Groq/Gemini) — never a new
  provider.
- **New capability = new `Settings` flag, defaulting `False`.** This
  codebase's universal convention (`backend/app/core/config.py`): every
  optional behavior is off until explicitly enabled, documented with a
  comment explaining why it defaults off. Two prompts in this set are
  exceptions (pure info-surfacing/rendering, zero cost, zero behavior
  change) — each says so explicitly when that applies.
- **Every new backend field is additive and defaulted.** Never remove
  or change the type of an existing field. This is what keeps the
  existing `pytest` suite green without editing old tests.
- **Fail-safe by construction.** If a new LLM call inside one of these
  features errors, times out, or returns something unparseable, degrade
  to the pre-existing behavior — never turn a new feature's failure into
  a request-level failure. This mirrors every existing enhancement in
  `rag_service.py`/`research_agent.py` (e.g. web search failing degrades
  to an empty result list, never a 500).
- **Verification, every prompt, two steps:** (1) run `pytest` from
  `backend/` — the full suite must stay green; add new tests for the new
  behavior in the same file as the feature's existing tests (e.g.
  `test_main.py` for `/chat`-shaped changes). (2) A live check: start the
  backend (`uvicorn app.main:app --reload`) and frontend (`npm run dev`),
  exercise the new behavior in an actual browser — each prompt below
  states exactly what to click/type and what you should see.

## Shared files — who touches what, and how to not conflict

| File | Touched by | Nature of each touch | Rule |
|---|---|---|---|
| `backend/app/core/config.py` | Agent 1 (adds `query_contextualization_enabled`, `citation_verification_enabled`, `clarifying_question_enabled`), Agent 2 (adds `local_research_agent_enabled`, `local_research_max_subqueries`), Agent 3 (adds `chunk_dedup_enabled`, `chunk_dedup_similarity_threshold`, `duplicate_document_detection_enabled`, `duplicate_document_similarity_threshold`) | Pure line-appends inside the `Settings` class, one flag per feature, each with its own doc-comment explaining why it defaults off | Append your new flags at the very end of the `Settings` class body (just before `model_config = SettingsConfigDict(...)`). Never reorder, reformat, or edit an existing flag. |
| `backend/app/models/schemas.py` | All 4 agents add distinct new fields/classes | `ChatResponse.retrieval_confidence`, `ChatResponse.is_clarifying_question` (Agent 1); `ChatRequest.persona`, `ChatResponse.follow_up_questions` (Agent 2); `Document`-related fields, `ChatRequest.document_ids` (Agent 3); new `HighlightResponse` class (Agent 4) | Only edit the specific model(s) your own prompts name. Add new fields at the end of each model's field list. Never reorder or remove an existing field. |
| `backend/app/services/rag_service.py` | Agent 1 (grading/correction loop: `_grade_retrieval`, `_is_ungrounded`, `_correct`/`_correct_streamed`, plus the tail of `handle_query`/`stream_query`), Agent 2 (new hook points inside `handle_query`/`stream_query` for persona threading, follow-up generation, and a new research branch), Agent 3 (one added keyword argument at the two existing `retrieve()` call sites only) | Agents 1 and 2 make structurally deeper edits (new branches/params); Agent 3's touch is trivial by comparison | If building sequentially: land Agent 1's changes first, then Agent 2, then Agent 3's one-line addition. If building in parallel on separate branches, resolve this file's merge by hand, one hunk at a time (`git add -p`) rather than a blind merge — this file is the one real collision risk in this whole plan. |
| `backend/app/api/v1/routes/documents.py` | Agent 3 (modifies the existing `POST /upload` and `GET /documents` handlers to accept an optional `collection` parameter), Agent 4 (adds two brand-new route functions, `GET /documents/{id}/file` and `GET /documents/{id}/pages/{page_number}/highlight`) | Agent 3 edits existing function bodies; Agent 4 only appends new functions | Low real risk since the edits are in different functions. Agent 4 should add its new route functions at the end of the file. |

There is **no functional dependency between any of the 13 features** —
each is independently additive. The guidance above is purely to avoid
textual merge conflicts, not because one feature's code requires
another's to exist first.

---

# Agent 1: Answer-quality core

Your bundle: 4 features, all inside `backend/app/services/rag_service.py`'s
grading/correction loop. Build and test them one at a time, in the
order given — each is a standalone prompt, but this order keeps your
own diffs to this one file easy to review as you go.

## Prompt 1.1 — Retrieval confidence banner

**Goal:** surface the retrieval-quality grade the backend already
computes internally, so the user sees when an answer's grounding was
weak, instead of it only affecting internal routing invisibly.

**Context you need:** `backend/app/services/rag_service.py` has a
method `_grade_retrieval(self, query: str, chunks: list[RetrievedChunk]) -> str`
(around line 571) that returns exactly one of `"good"`, `"weak"`, or
`"insufficient"`:
```python
def _grade_retrieval(self, query: str, chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        grade, top_score = "insufficient", None
    else:
        top_score = max(chunk.score for chunk in chunks)
        grade = "good" if top_score >= settings.retrieval_grade_threshold else "weak"
    ...
    return grade
```
This grade is already computed inside `handle_query` (the blocking
`/chat` path) and `stream_query` (the streaming `/chat/stream` path) —
both methods on `ChatService` — to decide whether to hand off to the
research agent or web-search fallback. Today, that grade string is
computed and then discarded; it never reaches the API response.

**Backend changes:**
1. In `backend/app/models/schemas.py`, find the `ChatResponse` class
   (around line 94) and add one new field at the end of its field list:
   ```python
   retrieval_confidence: Literal["good", "weak", "insufficient"] = "good"
   ```
   (`Literal` is already imported in this file for other fields — check
   the top of the file; if not, add `Literal` to the existing `typing`
   import line.) Default `"good"` so any code path that doesn't set it
   explicitly still validates.
2. In `rag_service.py`'s `handle_query` method: find where the grade is
   computed (the call to `self._grade_retrieval(...)`) and where the
   final `ChatResponse(...)` is constructed and returned. Store the
   grade in a local variable when computed, and pass
   `retrieval_confidence=grade` into that final `ChatResponse(...)`
   constructor call.
3. Do the same in `stream_query`: find where it builds the payload for
   the final `{"type": "done", ...}` SSE event (this is what `query.py`'s
   `_sse_line` serializes via `model_dump(mode="json")` when the payload
   is a Pydantic model) and thread the same grade value into it.
4. **No new `Settings` flag for this feature** — it's pure information
   surfacing already computed internally, zero added cost, zero
   behavior change. This matches the precedent set by this session's
   earlier `SourceReference.content_type`/`page_number` fields, which
   also shipped without a flag.

**Frontend changes:**
1. `frontend/src/hooks/useChat.js` — inside the `fetchAnswer` function's
   `onDone: (payload) => { ... }` callback (where it currently reads
   `payload.answer` and `payload.sources` into the assistant message
   object), add: `retrievalConfidence: payload.retrieval_confidence`.
2. `frontend/src/components/chat/ChatBubble.jsx` — this component
   receives a `message` prop and, for assistant messages that aren't
   streaming, renders `<CitedAnswer text={message.content} sources={message.sources} />`.
   Immediately after that (still inside the `!isUser && !message.isStreaming`
   block), add a small conditional notice:
   ```jsx
   {message.retrievalConfidence && message.retrievalConfidence !== 'good' && (
     <p className="mt-1.5 text-xs text-amber-600 dark:text-amber-500">
       Low confidence — double-check this against the source.
     </p>
   )}
   ```
   Match whatever muted/warning text color classes are already used
   elsewhere in this file (check the existing feedback/error text
   classes in this same component and reuse that palette instead of
   inventing new ones if `amber` isn't already in use in this codebase).

**Verify:**
- `pytest backend/tests/test_main.py` — add an assertion that a chat
  response includes `retrieval_confidence` and that it's one of the
  three valid values; the full suite must stay green.
- Live: start both servers, upload a PDF, ask a question clearly
  answerable from it (banner should NOT appear), then ask something
  off-topic/unanswerable (banner SHOULD appear, worded "Low confidence —
  double-check this against the source").

## Prompt 1.2 — Query contextualization before retrieval

**Goal:** fix a real retrieval-quality gap — follow-up questions
currently retrieve blind to conversation context.

**Context you need:** in `rag_service.py`'s `handle_query` method,
retrieval is called like this (around line 865):
```python
chunks = retrieve(
    query, self._vector_store, top_k=top_k, min_score=min_score, tenant_id=tenant_id
)
```
`query` here is always the raw, current-turn text — never rewritten
using conversation history. Separately, a few lines earlier, history is
truncated: `recent_history = history[-_MAX_HISTORY_TURNS:] if history else None`
(`_MAX_HISTORY_TURNS = 6` is a module constant near the top of the
file) — but `recent_history` is only ever passed into the *generation*
step (`_generate`, `_correct`, etc.), never into retrieval. The exact
same pattern repeats in `stream_query` (around line 1090) with its own
`recent_history`. This means a follow-up like "what about the other
region?" gets embedded and searched using only that literal sentence,
blind to what "the other region" refers to.

**Backend changes:**
1. In `backend/app/core/config.py`, add a new flag inside the
   `Settings` class, at the end, before `model_config = SettingsConfigDict(...)`:
   ```python
   # When True, a follow-up question (one where conversation history
   # exists) is rewritten into a standalone question via one extra LLM
   # call before it's used for retrieval — the raw follow-up text alone
   # ("what about the other one?") often retrieves poorly since it's
   # missing the context a human reader would infer from prior turns.
   # Off by default: it's one additional LLM call, only on follow-up
   # turns (never on a first message, since there's no history to use).
   query_contextualization_enabled: bool = False
   ```
2. In `rag_service.py`, add a new method on `ChatService`:
   ```python
   def _contextualize_query(self, query: str, history: list[dict] | None) -> str:
       """Rewrite a follow-up question into a standalone one, using
       conversation history, before it's used for retrieval. Only called
       when history is non-empty. Degrades to the raw query on any LLM
       failure — this is a retrieval-quality enhancement, never a
       dependency the request can fail on."""
       if not history:
           return query
       prompt = (
           "Conversation history:\n"
           + "\n".join(f"{turn.get('role', 'user')}: {turn.get('content', '')}" for turn in history)
           + f"\n\nFollow-up question: {query}\n\n"
           "Rewrite the follow-up question as a standalone question that "
           "makes sense without the conversation history. Return ONLY the "
           "rewritten question, nothing else."
       )
       try:
           rewritten = self._llm_client.generate(prompt).strip()
           return rewritten if rewritten else query
       except Exception:
           return query
   ```
3. In `handle_query`, right before the `retrieve(...)` call shown above,
   add:
   ```python
   retrieval_query = query
   if settings.query_contextualization_enabled and recent_history:
       retrieval_query = self._contextualize_query(query, recent_history)
   ```
   then change the `retrieve(...)` call to pass `retrieval_query` instead
   of `query` as its first argument. **Important:** every other use of
   `query` in this method (generation, citations, caching, logging) must
   stay as the original `query` — only the value passed into `retrieve()`
   changes. Apply the identical change in `stream_query` at its own
   `retrieve(...)` call site.

**Frontend changes:** none — this is fully transparent to the client.

**Verify:**
- `pytest` — add a unit test for `_contextualize_query` mocking
  `self._llm_client.generate` to confirm it's called with history present
  and skipped (returns the raw query unchanged, no LLM call) when
  history is empty/None. Full suite must stay green.
- Live: enable `QUERY_CONTEXTUALIZATION_ENABLED=true` in `backend/.env`,
  restart the backend, upload a document about two comparable things
  (e.g. two products/regions), ask "tell me about X", then ask "what
  about Y" as a follow-up — confirm the answer correctly addresses Y
  rather than misinterpreting the pronoun-less follow-up.

## Prompt 1.3 — Citation-groundedness verifier

**Goal:** strengthen this app's core trust mechanism. Today it can miss
genuine hallucination.

**Context you need:** `rag_service.py`'s `_is_ungrounded` method (around
line 623) is the entire check behind the existing reflection/regenerate
loop:
```python
def _is_ungrounded(
    self, answer: str, chunks: list[RetrievedChunk], web_results: list[WebSearchResult]
) -> bool:
    if not chunks and not web_results:
        return False
    return not answer.strip() or answer.strip() == FALLBACK_REPLY
```
This only catches an empty answer or the literal fallback string — it
has no idea whether a specific cited claim is actually supported by its
cited chunk. `FALLBACK_REPLY` is imported from `prompt_builder.py`
(`"I couldn't find that information in the uploaded documents."`). This
check is called from `_correct` and `_correct_streamed` (both around
lines 635-799), which — if it returns `True` — regenerate the answer
once using `REFLECTION_INSTRUCTION` (also from `prompt_builder.py`),
and if still ungrounded and web search is enabled, fall back to a web
search and regenerate once more. There's a hard cap:
`_MAX_LLM_CALLS = 3` (module constant) total `generate()` calls per
request, checked before each regeneration attempt.

The app's citation convention: the LLM is instructed (via
`prompt_builder.py`'s `_INSTRUCTIONS`) to cite sources inline as `[N]`
markers, where N corresponds to a chunk's position in the retrieved
list (1-indexed).

**Backend changes:**
1. In `backend/app/core/config.py`, add:
   ```python
   # When True, a generated answer's [N] citation markers are checked
   # against their cited chunks via one extra LLM call before the answer
   # is accepted — catching a claim that cites a real chunk but
   # misstates what it says (something _is_ungrounded's empty/fallback
   # check can't detect). Bounded to one combined call per answer, never
   # one call per citation. Off by default: real added cost on every
   # answer that has citations.
   citation_verification_enabled: bool = False
   ```
2. In `rag_service.py`, add a new method:
   ```python
   def _verify_citations(self, answer: str, chunks: list[RetrievedChunk]) -> bool:
       """True if every [N] citation in `answer` is actually supported by
       its cited chunk's text. True (pass) if there are no citations to
       check, or on any LLM/parse failure — this is a stricter check
       layered on top of _is_ungrounded, never a stricter gate that can
       make an otherwise-fine answer fail closed."""
       import re
       citation_numbers = sorted(set(int(n) for n in re.findall(r"\[(\d+)\]", answer)))
       if not citation_numbers:
           return True
       chunk_by_number = {i + 1: chunk for i, chunk in enumerate(chunks)}
       cited_pairs = [
           (n, chunk_by_number[n].text) for n in citation_numbers if n in chunk_by_number
       ]
       if not cited_pairs:
           return True
       prompt = (
           "Answer:\n" + answer + "\n\n"
           + "\n\n".join(f"Excerpt [{n}]:\n{text}" for n, text in cited_pairs)
           + "\n\nFor each excerpt number above, does the answer's claim "
           "attributed to it actually match what that excerpt says? "
           'Respond with ONLY a JSON object like {"1": true, "2": false}, '
           "one entry per excerpt number shown."
       )
       try:
           import json
           raw = self._llm_client.generate(prompt).strip()
           raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
           result = json.loads(raw)
           return all(result.get(str(n), True) for n, _ in cited_pairs)
       except Exception:
           return True
   ```
3. In both `_correct` and `_correct_streamed`, find the first line —
   `if not self._is_ungrounded(answer, chunks, web_results): return ...`
   (the early-return when the answer looks fine) — and change the
   condition to also fail this check when citation verification is on:
   ```python
   ungrounded = self._is_ungrounded(answer, chunks, web_results) or (
       settings.citation_verification_enabled and not self._verify_citations(answer, chunks)
   )
   if not ungrounded:
       return answer, llm_calls, steps_taken, web_results, web_search_attempted
   ```
   Everything after that in both methods (the regenerate/web-fallback
   logic, the `_MAX_LLM_CALLS` cap) stays exactly as it is today — you're
   only changing what counts as "ungrounded," not building a second
   correction mechanism.

**Frontend changes:** none — a stronger internal check is invisible; the
user either sees a better-corrected answer, or the pre-existing
"reflecting" trace stage if a regeneration fires.

**Verify:**
- `pytest` — mock `self._llm_client.generate` to return a JSON object
  with a `false` entry and confirm `_correct` triggers a regeneration;
  confirm it does NOT regenerate when `citation_verification_enabled` is
  `False` even if citations would fail verification. Full suite green.
- Live: enable `CITATION_VERIFICATION_ENABLED=true`, ask a question
  against an uploaded document, confirm the answer still comes through
  normally (the "reflecting" trace stage should only appear rarely, when
  the model's own citations are genuinely wrong).

## Prompt 1.4 — Ask-instead-of-guess clarifying question

**Goal:** when the system has tried everything and still doesn't have a
confident answer, ask the user one clarifying question instead of
returning a canned "I couldn't find that" line.

**Context you need:** this depends on Prompt 1.1's `retrieval_confidence`
grade value existing (build 1.1 first, or at minimum compute the grade
the same way it does — see the `_grade_retrieval` method described
there). After `_correct`/`_correct_streamed` finish (described in
Prompt 1.3 above), if the answer is still ungrounded and the grade was
`"insufficient"`, today the response just carries `FALLBACK_REPLY`
(`"I couldn't find that information in the uploaded documents."`, from
`prompt_builder.py`).

**Backend changes:**
1. In `backend/app/core/config.py`, add:
   ```python
   # When True, if retrieval graded "insufficient" and the corrective
   # loop still couldn't produce a grounded answer, the app asks the
   # user one short clarifying question instead of returning the fixed
   # "couldn't find that" line — a better outcome when the real problem
   # is an ambiguous question, not missing content. Degrades to today's
   # exact fallback behavior on any LLM failure. Off by default: one
   # extra LLM call, only in this specific (rare) end state.
   clarifying_question_enabled: bool = False
   ```
2. In `backend/app/models/schemas.py`'s `ChatResponse`, add:
   ```python
   is_clarifying_question: bool = False
   ```
3. In `rag_service.py`'s `handle_query`, after the point where `_correct`
   has returned its final `answer` and you have the retrieval `grade`
   value (from Prompt 1.1 — if that prompt hasn't been applied yet in
   your working copy, compute it the same way: `grade = self._grade_retrieval(query, chunks)`,
   called once, before the correction loop, exactly like the existing
   code already does to decide the research/web-fallback branch), add:
   ```python
   is_clarifying_question = False
   if (
       settings.clarifying_question_enabled
       and grade == "insufficient"
       and answer.strip() == FALLBACK_REPLY
   ):
       try:
           clarifying_prompt = (
               f"The user asked: {query}\n\n"
               "No relevant information was found in their documents, and "
               "the question may be ambiguous or missing detail. Suggest "
               "ONE short clarifying question to ask them. Return ONLY the "
               "question, nothing else."
           )
           clarification = self._llm_client.generate(clarifying_prompt).strip()
           if clarification:
               answer = clarification
               is_clarifying_question = True
       except Exception:
           pass  # falls through, answer stays FALLBACK_REPLY exactly as today
   ```
   Thread `is_clarifying_question=is_clarifying_question` into the final
   `ChatResponse(...)` construction. Apply the same change in
   `stream_query`, threading it into the final `"done"` event payload.

**Frontend changes:**
1. `frontend/src/hooks/useChat.js` — in `fetchAnswer`'s `onDone` callback,
   add `isClarifyingQuestion: payload.is_clarifying_question ?? false`.
2. `frontend/src/components/chat/ChatBubble.jsx` — where the assistant
   bubble renders `<CitedAnswer .../>`, add a small visual cue when
   `message.isClarifyingQuestion` is true — e.g. a `?`-prefixed border
   color change using Tailwind classes already present elsewhere in
   this file (check what accent color classes already exist in this
   component, such as `border-accent-500` used elsewhere in this
   codebase, and reuse rather than introduce a new color).

**Verify:**
- `pytest` — mock a fully-ungrounded, `"insufficient"`-graded path,
  confirm `is_clarifying_question=True` and `answer` is no longer the
  literal `FALLBACK_REPLY` string when the flag is on; confirm behavior
  is unchanged (still the literal fallback line) when the flag is off.
  Full suite green.
- Live: enable `CLARIFYING_QUESTION_ENABLED=true`, ask a question
  completely unrelated to any uploaded document, confirm you get back a
  clarifying question rather than the flat "couldn't find that" line.

---

# Agent 2: Agentic capabilities + personalization

Your bundle: 3 features, all adding a new capability (not modifying the
correction loop) via hook points in `rag_service.py` plus new/extended
files.

## Prompt 2.1 — Persona presets

**Goal:** let the user pick a tone/style for answers, without ever
letting that override the app's core grounding rules.

**Context you need:** `backend/app/services/prompt_builder.py`'s
`build_prompt` function (around line 163) has this signature:
```python
def build_prompt(
    query: str,
    chunks: list[RetrievedChunk],
    history: list[dict] | None = None,
    extra_instruction: str | None = None,
    web_results: list[WebSearchResult] | None = None,
) -> str:
```
It assembles the final prompt string as (around line 181):
```python
return (
    f"{instructions}\n\n"
    f"{_format_history(history)}"
    f"Context:\n{context}\n\n"
    f"Question: {query.strip()}\n\n"
    "Answer:"
)
```
where `instructions` is the fixed `_INSTRUCTIONS` string (with
`_WEB_RESULTS_INSTRUCTION` appended if `web_results` is given, and
`extra_instruction` — e.g. the reflection instruction used by the
correction loop — appended last if given). There is currently **no**
persona/style mechanism anywhere in this file. `build_structured_prompt`
(around line 209) has the same basic shape for JSON-mode output.

**Design constraint — state this exactly, don't skip it:** a persona
may only change tone/style. It must never be able to disable or weaken
the grounding/citation instructions in `_INSTRUCTIONS`. Implement this
by always keeping `_INSTRUCTIONS` first and unconditional, appending the
persona instruction next, and keeping `extra_instruction` (reflection)
last — so a correction attempt always has the final word regardless of
persona.

**Backend changes:**
1. In `prompt_builder.py`, add near the top (after the existing
   constants like `FALLBACK_REPLY`):
   ```python
   # Tone/style presets a user can select per request. These may only
   # affect HOW an answer is phrased — never whether it's grounded. Kept
   # as short, additive instruction fragments appended after
   # _INSTRUCTIONS, never as a replacement for it.
   PERSONAS: dict[str, str] = {
       "concise": "Keep your answer to 2-3 sentences unless the question genuinely needs more.",
       "eli5": "Explain your answer in plain, simple language, as if to someone new to the topic.",
   }
   ```
2. Add a `persona: str | None = None` parameter to both `build_prompt`
   and `build_structured_prompt`. In each, right after `instructions =
   _INSTRUCTIONS` (or wherever the base instructions string is first
   assigned) and before the web-results/extra-instruction appends, add:
   ```python
   if persona and persona in PERSONAS:
       instructions = f"{instructions}\n\n{PERSONAS[persona]}"
   ```
3. In `backend/app/models/schemas.py`'s `ChatRequest`, add:
   ```python
   persona: str | None = None
   ```
4. In `rag_service.py`, `handle_query` and `stream_query` both need a
   new `persona: str | None = None` parameter, threaded into every call
   to `build_prompt`/`build_structured_prompt` inside `_generate`,
   `_generate_structured`, `_generate_streamed`, `_correct`, and
   `_correct_streamed` (all of these currently accept/pass through a
   `history` parameter the same way — add `persona` alongside it in each
   signature and each call site).
5. In `backend/app/api/v1/routes/query.py`, the `chat` and `chat_stream`
   route handlers call `chat_service.handle_query(...)`/`stream_query(...)`
   with named arguments already (`payload.query, top_k=..., min_score=...,
   history=..., session_id=..., confirm_web_search=..., ...`) — add
   `persona=payload.persona` to both calls.

**Frontend changes:**
1. `frontend/src/components/chat/ChatInput.jsx` — this component
   currently has props `{ onSend, disabled }` and renders a `<form>`
   containing a `<textarea>` and a submit button. Add a native
   `<select>` inside that form (there's no dedicated dropdown component
   in `components/ui/` — style it with the shared `input` CSS class the
   same way `frontend/src/pages/Documents.jsx`'s sort dropdown does):
   ```jsx
   <select
     value={persona}
     onChange={(e) => setPersona(e.target.value)}
     className="input w-auto shrink-0 text-xs"
   >
     <option value="">Default</option>
     <option value="concise">Concise</option>
     <option value="eli5">Simple (ELI5)</option>
   </select>
   ```
   `persona`/`setPersona` state should live in `frontend/src/pages/Chat.jsx`
   (lifted state, same pattern React apps commonly use for a controlled
   child input) and be passed down as new props to `ChatInput`. Change
   `ChatInput`'s `onSend` call site (inside its `handleSubmit`) to call
   `onSend(trimmed, persona)` instead of `onSend(trimmed)`.
2. `frontend/src/pages/Chat.jsx` currently renders
   `<ChatInput onSend={ask} disabled={isSending} />` and destructures
   `ask` from `useChat()`. Change the suggestion buttons and `ChatInput`
   to pass persona through: `onSend={(text, persona) => ask(text, persona)}`.
3. `frontend/src/hooks/useChat.js` — `ask(query)` currently computes
   history and calls `fetchAnswer(query, history)`. Change its signature
   to `ask(query, persona)` and pass `persona` through to `fetchAnswer`,
   which itself needs a new `persona` parameter threaded into its call
   to `streamChatMessage(query, { history, sessionId: sessionIdRef.current, persona }, {...})`.
4. `frontend/src/services/chatService.js` — its `buildChatPayload(query, options)`
   function currently has:
   ```js
   function buildChatPayload(query, options) {
     const payload = { query }
     if (options.topK != null) payload.top_k = options.topK
     if (options.minScore != null) payload.min_score = options.minScore
     if (options.history?.length) payload.history = options.history
     if (options.sessionId) payload.session_id = options.sessionId
     return payload
   }
   ```
   Add one line: `if (options.persona) payload.persona = options.persona`.

**Verify:**
- `pytest` — unit test that `build_prompt` with `persona="concise"`
  includes the concise instruction text in its output, and that
  `_INSTRUCTIONS`'s grounding text is present regardless of persona.
  Full suite green.
- Live: ask the same question twice, once with each persona selected,
  confirm the tone differs (e.g. "concise" gives a shorter answer) while
  both still cite sources normally.

## Prompt 2.2 — Auto-suggested follow-up questions

**Goal:** after each answer, suggest 2-3 natural follow-up questions,
matching the "related questions" pattern common in modern AI assistants.

**Context you need:** `rag_service.py`'s `handle_query` builds the final
answer via `_generate`/`_correct` and constructs the returned
`ChatResponse` — that's the exact point to add one more cheap
generation call. The existing `LLMClient` interface (imported as
`from app.services.llm_client import LLMClient`) exposes a synchronous
`generate(prompt: str) -> str` method — that's the only method this
feature needs.

**Backend changes:**
1. In `backend/app/core/config.py`, add:
   ```python
   # When True, one extra small LLM call after the main answer suggests
   # up to 3 short follow-up questions the user might ask next (the
   # "related questions" pattern). Parsed defensively — any failure
   # degrades to an empty list, never affects the main answer. Off by
   # default: added latency + one extra LLM call per request.
   follow_up_questions_enabled: bool = False
   ```
2. In `backend/app/models/schemas.py`'s `ChatResponse`, add:
   ```python
   follow_up_questions: list[str] = Field(default_factory=list)
   ```
   (Check whether `Field`/`field` is already imported in this file for
   other list-default fields — likely yes, e.g. for
   `allowed_upload_mime_types`-style defaults elsewhere in this
   codebase's schemas; if not, add the import.)
3. In `rag_service.py`, add a method:
   ```python
   def _suggest_follow_ups(self, query: str, answer: str) -> list[str]:
       """Suggest up to 3 short follow-up questions. Degrades to an
       empty list on any LLM/parse failure — never blocks or fails the
       main answer."""
       prompt = (
           f"Question: {query}\nAnswer: {answer}\n\n"
           "Suggest up to 3 short, natural follow-up questions the user "
           'might ask next. Return ONLY a JSON array of strings, e.g. '
           '["question one?", "question two?"]. Return an empty array [] '
           "if you can't think of good ones."
       )
       try:
           import json
           raw = self._llm_client.generate(prompt).strip()
           raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
           result = json.loads(raw)
           return [str(q) for q in result][:3] if isinstance(result, list) else []
       except Exception:
           return []
   ```
4. In `handle_query`, right before constructing the final `ChatResponse`,
   add:
   ```python
   follow_up_questions = []
   if settings.follow_up_questions_enabled:
       follow_up_questions = self._suggest_follow_ups(query, answer)
   ```
   and thread `follow_up_questions=follow_up_questions` into the
   `ChatResponse(...)` call. Do the same in `stream_query` for its final
   `"done"` event payload.

**Frontend changes:**
1. `frontend/src/hooks/useChat.js` — in `fetchAnswer`'s `onDone`
   callback, add `followUpQuestions: payload.follow_up_questions ?? []`.
2. `frontend/src/components/chat/ChatBubble.jsx` — this component
   already threads an `onRegenerate` callback prop down from
   `frontend/src/pages/Chat.jsx` (called on the existing Regenerate
   button). Add a new `onFollowUpClick` prop the same way, and render,
   below the existing answer/action-buttons block (only when
   `!isUser && !message.isStreaming && message.followUpQuestions?.length`):
   ```jsx
   <div className="mt-2 flex flex-wrap gap-1.5">
     {message.followUpQuestions.map((q) => (
       <Button key={q} variant="ghost" size="sm" onClick={() => onFollowUpClick(q)}>
         {q}
       </Button>
     ))}
   </div>
   ```
3. In `frontend/src/pages/Chat.jsx`, pass `onFollowUpClick={ask}` (or
   `(q) => ask(q, persona)` if Prompt 2.1 has already been applied in
   your working copy — pass whatever `ask` currently expects) to each
   `<ChatBubble>` instance.

**Verify:**
- `pytest` — mock `self._llm_client.generate` to return a valid JSON
  array, confirm it lands in `follow_up_questions`; mock a malformed
  response, confirm it degrades to `[]` without raising. Full suite
  green.
- Live: enable `FOLLOW_UP_QUESTIONS_ENABLED=true`, ask a question,
  confirm 1-3 clickable follow-up pills appear below the answer and
  clicking one asks that question.

## Prompt 2.3 — Local Document Research Agent

**Goal:** give complex multi-part questions against the user's own
documents a real multi-step retrieval pass, instead of exactly one
`retrieve()` call no matter how complex the question is.

**Context you need:** `backend/app/services/research_agent.py` already
implements a plan→search→read→synthesize loop, but it is hard-wired to
*web* search only — its `run(query, confirm_web_search=False) -> ResearchFindings`
method (around line 132) calls `self._plan_queries(query)` (an LLM call
in JSON mode that breaks the query into up to `settings.research_max_subqueries`
sub-queries), then runs each sub-query through `search_web()` in
parallel via a `ThreadPoolExecutor`, reads the top pages, and
synthesizes via `build_prompt(query, [], web_results=results)` — note
`chunks=[]` is hard-coded; it never calls this app's own local
`retrieve()` at all. Meanwhile, `rag_service.py`'s `handle_query` and
`stream_query` each call local `retrieve()` exactly once per request,
with whatever `top_k` was resolved — there's no local multi-hop
decomposition today.

`ResearchFindings` is a dataclass (around line 112):
```python
@dataclass
class ResearchFindings:
    results: list[WebSearchResult] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    pages_read: int = 0
    steps: list[dict[str, Any]] = field(default_factory=list)
    answer: str = ""
```

**Backend changes:**
1. Extract the planning step into a small shared module,
   `backend/app/services/query_planning.py`:
   ```python
   """Shared sub-query planning, used by both the web ResearchAgent and
   the local-document LocalResearchAgent — one JSON-mode LLM call that
   breaks a complex query into up to max_subqueries standalone
   sub-queries. Degrades to [query] itself on any failure."""

   import json
   import logging

   from app.services.llm_client import LLMClient

   logger = logging.getLogger(__name__)

   _PLAN_PROMPT = (
       "Break this question into up to {max_subqueries} standalone "
       "search queries that together would answer it. If the question "
       "is already simple, return just one query (the original "
       'question). Return ONLY a JSON object like {{"queries": ["...", "..."]}}.\n\n'
       "Question: {query}"
   )

   def plan_subqueries(llm_client: LLMClient, query: str, max_subqueries: int) -> list[str]:
       try:
           raw = llm_client.generate(
               _PLAN_PROMPT.format(query=query, max_subqueries=max(1, max_subqueries))
           ).strip()
           raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
           parsed = json.loads(raw)
           queries = parsed.get("queries") if isinstance(parsed, dict) else None
           if isinstance(queries, list) and queries:
               return [str(q) for q in queries][:max(1, max_subqueries)]
       except Exception:
           logger.warning("subquery_planning_failed", extra={"extra_fields": {"query": query}})
       return [query]
   ```
   Then update `research_agent.py`'s own `_plan_queries` method to call
   `plan_subqueries(self._llm_client, query, settings.research_max_subqueries)`
   internally instead of duplicating this logic — check its current
   implementation first and replace its body with a call to the new
   shared helper, keeping its own method signature unchanged so nothing
   else in `research_agent.py` needs to change.
2. Add `backend/app/services/local_research_agent.py`:
   ```python
   """LocalResearchAgent: the same plan-decompose-search-synthesize shape
   as ResearchAgent (research_agent.py), pointed at this app's own
   document retrieval instead of the web. Used when a query is complex
   enough that one retrieve() call may only surface part of the answer
   (e.g. a question comparing two sections of a document)."""

   import logging
   from concurrent.futures import ThreadPoolExecutor
   from dataclasses import dataclass, field

   from app.core.config import settings
   from app.models.document import RetrievedChunk
   from app.services.llm_client import LLMClient
   from app.services.prompt_builder import build_prompt, strip_sources_section
   from app.services.query_planning import plan_subqueries
   from app.services.retrieval_service import retrieve
   from app.services.vector_store import VectorStore

   logger = logging.getLogger(__name__)


   @dataclass
   class LocalResearchFindings:
       chunks: list[RetrievedChunk] = field(default_factory=list)
       queries: list[str] = field(default_factory=list)
       answer: str = ""


   class LocalResearchAgent:
       def __init__(self, llm_client: LLMClient, vector_store: VectorStore):
           self._llm_client = llm_client
           self._vector_store = vector_store

       def run(self, query: str, tenant_id: int | None = None) -> LocalResearchFindings:
           queries = plan_subqueries(self._llm_client, query, settings.local_research_max_subqueries)
           chunks_by_id: dict[str, RetrievedChunk] = {}
           with ThreadPoolExecutor(max_workers=max(1, len(queries))) as pool:
               futures = [
                   pool.submit(retrieve, q, self._vector_store, tenant_id=tenant_id)
                   for q in queries
               ]
               for future in futures:
                   try:
                       for chunk in future.result():
                           chunks_by_id[chunk.chunk_id] = chunk
                   except Exception:
                       logger.warning("local_research_subquery_failed", extra={"extra_fields": {}})
           merged_chunks = list(chunks_by_id.values())
           if not merged_chunks:
               return LocalResearchFindings(queries=queries)
           prompt = build_prompt(query, merged_chunks)
           try:
               answer = strip_sources_section(self._llm_client.generate(prompt)).strip()
           except Exception:
               answer = ""
           return LocalResearchFindings(chunks=merged_chunks, queries=queries, answer=answer)
   ```
3. In `backend/app/core/config.py`, add:
   ```python
   # When True, a weak/insufficient-retrieval query gets handed to
   # LocalResearchAgent (local_research_agent.py) instead of (or ahead
   # of) the web-search research agent: it decomposes the query into
   # sub-queries and runs multiple local retrieve() passes, merging the
   # results — useful for questions that need combining content from
   # different parts of a document. Off by default: adds LLM planning
   # + multiple retrieval calls per weak-retrieval query.
   local_research_agent_enabled: bool = False

   # Max sub-queries LocalResearchAgent's planning step may emit.
   local_research_max_subqueries: int = 3
   ```
4. In `rag_service.py`'s `ChatService.__init__`, add:
   ```python
   self._local_research_agent = LocalResearchAgent(llm_client, vector_store)
   ```
   (alongside the existing `self._research_agent = ResearchAgent(llm_client)`
   line). In `handle_query`, find the existing gate that hands off to
   the web research agent (`settings.research_agent_enabled and
   settings.web_search_enabled` combined with `grade != "good" or
   plan.action == "research"`) and add a parallel branch, checked
   first (local documents are the primary source of truth):
   ```python
   if settings.local_research_agent_enabled and grade != "good":
       findings = self._local_research_agent.run(query, tenant_id=tenant_id)
       if findings.answer:
           # build the ChatResponse from findings.answer/findings.chunks
           # following the same shape the existing research-agent
           # handoff branch already uses for its own findings.answer
           ...
   elif settings.research_agent_enabled and settings.web_search_enabled and (...):
       ... # existing web research handoff, unchanged
   ```
   Match the exact response-construction shape the existing web-research
   handoff branch already uses (check how it builds `sources`/`tool_used`/
   `answer_source` from `ResearchFindings` and mirror that for
   `LocalResearchFindings`, using `tool_used="local_research"` and
   `answer_source="documents"`). Apply the same branch shape in
   `stream_query`, emitting a new trace stage (e.g. `{"type": "trace",
   "stage": "local_research", "detail": {...}}`) before synthesizing.

**Frontend changes:**
1. `frontend/src/components/chat/AgentTraceStrip.jsx` — its `traceLabel(stage, detail)`
   function is a switch statement with cases for `'planning'`,
   `'retrieval'`, `'grading'`, `'web_search'`, `'generating'`,
   `'reflecting'` (each returning a human-readable label; unrecognized
   stages fall through to the raw string via `default: return stage`).
   Add one more case, matching whatever stage string you emitted above:
   ```js
   case 'local_research':
     return 'Researching your documents'
   ```

**Verify:**
- `pytest` — unit test `LocalResearchAgent.run` with a mocked
  `retrieve`/`llm_client`, confirming it merges chunks from multiple
  sub-queries and dedups by `chunk_id`. Full suite green.
- Live: enable `LOCAL_RESEARCH_AGENT_ENABLED=true`, upload a document
  with two distinct sections, ask a question that requires combining
  both (e.g. "compare X in section 2 with Y in section 5"), confirm the
  trace shows "Researching your documents" and the answer draws from
  both sections.

---

# Agent 3: Documents, collections & vector-store hygiene

Your bundle: 3 features clustered around document processing and the
FAISS vector store.

## Prompt 3.1 — Named document collections ("doc sets")

**Goal:** let users tag documents into named collections and scope a
chat to just one collection instead of the whole library.

**Context you need:**
- `backend/app/models/db_models.py`'s `Document` model (around line 96)
  has columns `id, tenant_id, document_id, original_filename,
  stored_filename, file_size, total_pages, total_chunks,
  total_embeddings, pages_ocred, upload_timestamp` — no collection/tag
  column exists.
- `backend/app/services/document_repository.py`'s `persist_document`
  function (around line 23) is keyword-only:
  ```python
  def persist_document(*, tenant_id, document_id, original_filename, stored_filename,
                        file_size, total_pages, total_chunks, total_embeddings, pages_ocred) -> None:
  ```
  it's a no-op if the DB is disabled or `tenant_id is None`, and never
  raises (best-effort, catches `Exception`). `list_documents(tenant_id)`
  (around line 101) returns a list of dicts with the same field names.
- `backend/app/models/schemas.py`'s `DocumentListItem` and
  `DocumentProcessingResponse` mirror those same fields.
- `backend/app/api/v1/routes/documents.py`'s `POST /upload` handler
  (around line 159) currently only accepts `file: UploadFile = File(...)`.
  Its `GET /documents` handler (around line 35) accepts `all_tenants: bool = False`.
- `backend/app/services/document_processing_service.py` orchestrates the
  actual pipeline (extract → chunk → embed → index → persist metadata) —
  **its exact `process()` signature wasn't confirmed in this round of
  exploration; open this file yourself and find where it calls
  `persist_document(...)` before making the change below**, rather than
  guessing the call site.
- Retrieval-side: `backend/app/services/retrieval_service.py`'s
  `retrieve()` function signature is:
  ```python
  def retrieve(query, vector_store, top_k=None, min_score=None, tenant_id=None) -> list[RetrievedChunk]:
  ```
  `backend/app/services/faiss_vector_store.py`'s `search()` method
  (lines ~132-172) filters by `tenant_id` inside its scoring loop
  (confirmed exact behavior: when `tenant_id is not None`, it fetches
  every score, i.e. `k = self._index.ntotal`, then filters and stops
  once `len(results) >= top_k` — this over-fetch exists specifically so
  tenant filtering doesn't starve the real top-k). `search_bm25()`
  (lines ~174-188) delegates to a `BM25Index.search(query, top_k,
  tenant_id=None)` method (in `backend/app/services/hybrid_search.py`,
  lines ~60-81) which also filters candidate positions by
  `record["metadata"].get("tenant_id") == tenant_id` before ranking.
  `hybrid_search()` (same file, calls both and fuses scores) has its own
  top-level function signature you'll need to check and extend.

**Backend changes:**
1. Add a new column to `Document` in `db_models.py`:
   ```python
   collection: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
   ```
2. Create a new Alembic migration (check `backend/alembic/versions/`
   for the most recent existing migration's exact revision-chaining
   style and follow it precisely — `down_revision` must point at
   whatever the current latest migration file is): add the `collection`
   column to the `documents` table, nullable, indexed.
3. In `document_repository.py`: add `collection: str | None = None` as a
   new keyword-only parameter to `persist_document`, pass it into the
   `Document(...)` constructor call; add `"collection": row.collection`
   to the dict `list_documents` returns per row; add an optional
   `collection: str | None = None` parameter to `list_documents` itself
   that, when given, adds a `.filter(Document.collection == collection)`
   to its query.
4. In `schemas.py`: add `collection: str | None = None` to both
   `DocumentListItem` and `DocumentProcessingResponse`.
5. In `documents.py`'s `upload_document` handler, add
   `collection: str | None = Form(None)` as a new parameter alongside
   `file: UploadFile = File(...)`, and thread it into whatever call this
   handler makes into `DocumentProcessingService` (check its current
   call — likely `service.process(file, tenant_id=tenant_id)` — add
   `collection=collection`). In `DocumentProcessingService.process()`
   (the file/method you need to open directly, per above), thread the
   new `collection` parameter through to its `persist_document(...)`
   call. In `list_uploaded_documents`, add an optional
   `collection: str | None = None` query parameter, passed into
   `list_documents(tenant_id, collection=collection)`.
6. Chat-scoping: in `schemas.py`'s `ChatRequest`, add
   `document_ids: list[str] | None = None`. In `retrieval_service.py`'s
   `retrieve()`, add a `document_ids: list[str] | None = None` parameter,
   threaded into whatever internal search call(s) it makes (both the
   hybrid-search path and the plain-semantic-search fallback path — check
   both branches). In `faiss_vector_store.py`'s `search()` method, add
   the same `document_ids` parameter; inside its scoring/filtering loop
   (the same place the existing `tenant_id` check lives), add an
   additional condition: skip a candidate if
   `document_ids is not None and record["document_id"] not in document_ids`.
   Do the identical addition to `search_bm25()` and `BM25Index.search()`
   in `hybrid_search.py` (its own tenant_id filter is the exact place to
   add this alongside), and to the top-level `hybrid_search()` function's
   signature, passing `document_ids` through to both underlying searches.
   Finally, in `rag_service.py`'s `handle_query` and `stream_query`, add
   a `document_ids: list[str] | None = None` parameter to each, threaded
   into their own `retrieve(...)` calls; in `query.py`'s `chat`/`chat_stream`
   handlers, pass `document_ids=payload.document_ids` into their
   `handle_query`/`stream_query` calls.

**Frontend changes:**
1. `frontend/src/pages/Upload.jsx` (not read in this round's exploration
   — open it directly) — add an optional text input for a collection
   name, included in the `FormData` passed to
   `frontend/src/services/documentService.js`'s `uploadDocument`. Update
   `uploadDocument(file, onProgress)` to accept an optional third
   argument `collection` and append it to the `FormData` if given.
2. `frontend/src/pages/Documents.jsx` — this page currently has a search
   input and a sort `<select>` in a row together (around where
   `SearchInput` and the sort `<select>` are rendered, conditionally
   shown when `documents.length > 0`). Add a second native `<select>`
   in that same row, populated from the distinct `collection` values
   present in `documents` (`[...new Set(documents.map(d => d.collection).filter(Boolean))]`),
   filtering the displayed list the same way the existing search-query
   filter already does inside the `filtered` `useMemo`. Add a small
   "Chat about this collection" button/action (e.g. per active filter)
   that navigates to `/chat` with
   `navigate('/chat', { state: { documentIds: matchingDocumentIds } })`.
3. `frontend/src/pages/Chat.jsx`/`frontend/src/hooks/useChat.js` — mirror
   how `location.state.sessionId` is already read once on mount and
   passed into `useChat(initialSessionId)`; add a second piece of
   `location.state` (`documentIds`) read the same way, stored in a ref,
   and threaded into `fetchAnswer`'s call to `streamChatMessage`, which
   itself needs `document_ids` added to `chatService.js`'s
   `buildChatPayload` the same way `sessionId`/`history` are already
   added there.

**Verify:**
- `pytest` — new tests in `test_main.py`/a new `test_document_collections.py`
  covering: uploading with a collection persists and returns it;
  `GET /documents?collection=X` filters correctly; a chat request with
  `document_ids` set only retrieves from those documents (mock
  `retrieve`/the vector store to confirm the parameter is passed
  through). Full suite green.
- Live: upload two documents into two different named collections,
  confirm `Documents.jsx` can filter to just one, and confirm a chat
  scoped to one collection's `document_ids` only answers from that
  collection's content (ask something only present in the other
  collection's document and confirm it's not used).

## Prompt 3.2 — Semantic chunk dedup at indexing

**Goal:** fix a real, observed bug — near-duplicate chunks can silently
starve each other out of retrieval — by refusing to index a chunk that's
a near-duplicate of one already indexed for the same document.

**Context you need:** `backend/app/services/hybrid_search.py`'s
`_min_max_normalize` function (lines 84-95):
```python
def _min_max_normalize(scores: list[float]) -> list[float]:
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi == lo:
        return [1.0 if hi > 0 else 0.0 for _ in scores]
    return [(score - lo) / (hi - lo) for score in scores]
```
With exactly 2 near-identical candidate chunks, this mathematically
forces the lower-scoring one to exactly `0.0` — confirmed via live
testing this session (a synthetic PDF whose table content was also
present as duplicate flowing text produced exactly this: one chunk
scored `1.0`, the near-duplicate scored `0.0`, and the `0.0` one was
then excluded by the default `retrieval_min_score` floor). This isn't a
bug in the normalization itself — it's what happens when there's no
dedup upstream of it.

`backend/app/services/faiss_vector_store.py`'s `add_embeddings` method
(lines 80-130) has zero dedup checking today — any new chunk (even an
exact duplicate) is added unconditionally:
```python
def add_embeddings(self, embedded_chunks: list[EmbeddedChunk]) -> None:
    with self._lock:
        # validates dimension, then:
        self._index.add(vectors)
        self._metadata.extend(...)
        # rebuilds BM25, asserts ntotal == len(metadata)
```
Chunk embeddings are already L2-normalized (`embedding_service.py`'s
`generate_embeddings` calls `model.encode(..., normalize_embeddings=True)`),
so cosine similarity between two chunks equals their inner product.
`self._metadata` is a flat list of dicts, each shaped
`{"chunk_id": ..., "document_id": ..., "metadata": {...}}`, positionally
aligned with FAISS index rows — the exact same list `delete_document`
already linear-scans (`[i for i, record in enumerate(self._metadata) if
record["document_id"] != document_id]`) to find a document's chunks.
`self._index.reconstruct(i)` returns the raw vector at position `i` (used
elsewhere in this file, e.g. `delete_document`'s rebuild step calls
`reconstruct_n` for the bulk case) — `IndexFlatIP` stores exact raw
vectors, so this works for a single-position lookup too.

**Backend changes:**
1. In `backend/app/core/config.py`, add:
   ```python
   # When True, a new chunk whose embedding is a near-duplicate
   # (cosine similarity >= chunk_dedup_similarity_threshold) of an
   # already-indexed chunk from the SAME document is skipped rather than
   # indexed — this is what prevents the exact scoring bug observed this
   # session, where two near-identical chunks starve each other out via
   # hybrid search's min-max score normalization. Off by default: a
   # linear-scan comparison cost per new chunk within its own document.
   chunk_dedup_enabled: bool = False

   # Cosine-similarity threshold above which two chunks from the same
   # document are treated as duplicates. High (0.97) — this catches true
   # near-duplicates, not just topically-similar chunks.
   chunk_dedup_similarity_threshold: float = 0.97
   ```
2. In `faiss_vector_store.py`, add a new private method on
   `FAISSVectorStore`:
   ```python
   def _is_duplicate_of_existing(self, document_id: str, vector) -> bool:
       """True if `vector` is a near-duplicate (cosine similarity >=
       settings.chunk_dedup_similarity_threshold) of any already-indexed
       chunk belonging to `document_id`. Vectors are assumed
       L2-normalized, so inner product == cosine similarity. Linear scan
       over self._metadata restricted to this document, same pattern
       delete_document already uses — fine at this app's per-document
       scale."""
       if not settings.chunk_dedup_enabled:
           return False
       positions = [
           i for i, record in enumerate(self._metadata)
           if record["document_id"] == document_id
       ]
       for i in positions:
           existing_vector = self._index.reconstruct(i)
           similarity = float(np.dot(existing_vector, vector))
           if similarity >= settings.chunk_dedup_similarity_threshold:
               return True
       return False
   ```
   (`numpy` is almost certainly already imported in this file as `np` —
   check; add the import if not. `settings` must already be imported
   from `app.core.config`.)
3. In `add_embeddings`, before adding each chunk's vector and metadata
   (inside whatever loop or batch-construction currently builds the
   `vectors`/metadata to add), filter out chunks where
   `self._is_duplicate_of_existing(chunk.document_id, vector)` is `True`
   — log one `chunk_deduplicated` event per skip (matching this file's
   existing logging style, e.g. how `MetadataSyncError`-adjacent asserts
   are logged elsewhere) — then proceed with only the surviving
   chunks/vectors exactly as today. If ALL chunks in a batch are
   filtered out, `add_embeddings` should simply add nothing (a valid,
   non-error outcome) rather than raising.

**Frontend changes:** none.

**Verify:**
- `pytest` — unit test `add_embeddings` with `chunk_dedup_enabled=True`:
  add one chunk, then attempt to add a near-identical one (construct two
  vectors with cosine similarity above the threshold), confirm the
  second is silently skipped (`self._index.ntotal` doesn't increase);
  confirm a genuinely different chunk for the same document IS added.
  Full suite green.
- Live: enable `CHUNK_DEDUP_ENABLED=true`, upload a PDF whose content
  legitimately repeats (e.g. a table that's also flowing text on the
  same page, similar to this session's own test case), confirm
  `total_embeddings` in the upload response is lower than it would be
  with the flag off.

## Prompt 3.3 — Duplicate-document detection on upload

**Goal:** warn (never block) when a newly-uploaded document closely
resembles one already indexed for the same tenant — directly helps
avoid wasted storage from accidental re-uploads.

**Context you need:** `backend/app/services/faiss_vector_store.py`'s
`get_chunks_by_document(document_id, tenant_id=None)` method (lines
240-256) already exists and returns a document's chunks (each given a
placeholder `score=1.0`, sorted by `chunk_index`) — this is the method
to reuse for building a cheap "fingerprint" of an existing document.
`backend/app/services/embedding_service.py`'s `get_embedding_model()`
(`@lru_cache(maxsize=1)`) returns the already-loaded
`SentenceTransformer` used everywhere else in this app — reuse it
directly rather than loading anything new. As with Prompt 3.1, the
exact orchestration sequence in
`backend/app/services/document_processing_service.py`'s `process()`
method (extract → chunk → embed → index → persist metadata) needs to be
read directly by you before wiring this in — don't guess its call
order.

**Backend changes:**
1. In `backend/app/core/config.py`, add:
   ```python
   # When True, a newly-uploaded document's first chunk's embedding is
   # compared against other same-tenant documents' first-chunk
   # embeddings; if similarity >= duplicate_document_similarity_threshold,
   # the upload still succeeds (never blocked) but the response names
   # the document it resembles. Off by default: adds one comparison pass
   # per upload.
   duplicate_document_detection_enabled: bool = False

   duplicate_document_similarity_threshold: float = 0.95
   ```
2. In `backend/app/models/schemas.py`'s `DocumentProcessingResponse`,
   add:
   ```python
   possible_duplicate_of: str | None = None
   ```
3. In `document_processing_service.py`'s `process()` method, after the
   new document's chunks have been embedded and indexed (i.e. after the
   point where `total_embeddings`/`document_id` for the new upload are
   already known — find this exact point yourself in the current code),
   and only `if settings.duplicate_document_detection_enabled`: fetch the
   new document's first chunk via
   `vector_store.get_chunks_by_document(new_document_id, tenant_id=tenant_id)[0]`
   (guard for an empty list — a zero-chunk document has nothing to
   fingerprint, skip the check); compare its embedding against every
   OTHER same-tenant document's first-chunk embedding the same way (you
   will need a way to enumerate other document_ids for this tenant —
   `document_repository.list_documents(tenant_id)` already returns this,
   excluding the new document's own `document_id`); compute cosine
   similarity (vectors are L2-normalized, so this is an inner product,
   same as Prompt 3.2's approach — if you don't have direct access to
   each chunk's raw vector via `get_chunks_by_document`'s return shape,
   check whether `RetrievedChunk` there needs augmenting, or fetch via
   the same `self._index.reconstruct(i)` approach Prompt 3.2 uses,
   applied to this document's known metadata position); if any exceeds
   the threshold, set a local `possible_duplicate_of` variable to that
   other document's `document_id`. Thread it into the final
   `DocumentProcessingResponse(...)` this method returns. Wrap the whole
   check in a broad `try/except`, defaulting to `possible_duplicate_of=None`
   on any failure — this must never fail an upload.

**Frontend changes:**
1. `frontend/src/hooks/useUpload.js` — this hook already has the exact
   precedent to extend, its existing conditional-notes array:
   ```js
   const notes = []
   if (result.pages_ocred > 0) notes.push(`${result.pages_ocred} page(s) recovered via OCR`)
   if (result.images_captioned > 0) notes.push(`${result.images_captioned} image(s) captioned`)
   if (result.total_tables > 0) notes.push(`${result.total_tables} table(s) extracted`)
   ```
   Add one more line: `if (result.possible_duplicate_of) notes.push('may duplicate an already-uploaded document')`.

**Verify:**
- `pytest` — new test: upload a document, then upload a near-identical
  one (same text content) with the flag on, confirm
  `possible_duplicate_of` is set to the first document's ID; confirm
  it's `None` for two genuinely different documents, and confirm it's
  always `None` when the flag is off. Full suite green.
- Live: enable `DUPLICATE_DOCUMENT_DETECTION_ENABLED=true`, upload the
  same PDF twice, confirm the second upload's success toast mentions
  "may duplicate an already-uploaded document" and that the upload still
  succeeds normally.

---

# Agent 4: Citation UX & admin ops

Your bundle: 3 features, zero `rag_service.py` touch — new routes,
frontend-heavy.

## Prompt 4.1 — In-app PDF citation preview

**Goal:** clicking a citation opens the actual source PDF at the right
page with the cited passage highlighted, instead of just showing an
excerpt string.

**Context you need:**
- `backend/app/api/v1/routes/documents.py` already has an exact
  precedent for tenant-scoped, file-adjacent serving — its
  `get_document_image` handler (around line 136):
  ```python
  @router.get("/documents/{document_id}/images/{image_id}")
  def get_document_image(document_id: str, image_id: str, request: Request) -> FileResponse:
      _ensure_document_accessible(request, document_id)
      image = next((i for i in load_image_manifest(document_id) if i.image_id == image_id), None)
      if image is None:
          raise DocumentNotFoundError(f"No image found with id {image_id}")
      path = image_storage_dir() / image.storage_path
      if not path.is_file():
          raise DocumentNotFoundError(f"No image found with id {image_id}")
      return FileResponse(path, media_type=image.mime_type)
  ```
  `_ensure_document_accessible(request, document_id)` (defined earlier in
  the same file) is the exact ownership-check helper to reuse — it
  raises `DocumentNotFoundError` (404) if the requester's tenant doesn't
  own the document, and is a no-op if tenant scoping can't be verified
  (DB disabled).
- The raw uploaded PDF is saved by `backend/app/services/upload_service.py`'s
  `save_uploaded_file`, using the filename pattern
  `stored_filename = f"{document_id}{extension}"` (e.g.
  `<uuid>.pdf`), inside `UPLOAD_DIR = settings.data_dir(settings.upload_dir_name)`.
  `documents.py`'s existing `delete_document` handler already locates a
  document's file the same way you will need to:
  `UPLOAD_DIR.glob(f"{document_id}.*")`.
- `backend/app/services/document_service.py`'s PDF text extraction uses
  plain PyMuPDF (`fitz`) — confirmed `page.search_for(text)` (a built-in
  PyMuPDF method that returns a list of bounding-box rectangles for
  occurrences of `text` on that page) is not used anywhere in this
  codebase today, so adding it is fully additive with zero risk to the
  existing extraction path. This app already treats page numbers as
  1-indexed everywhere (confirmed convention in `document_service.py`).
- `backend/app/models/schemas.py`'s `SourceReference` already has
  `page_number: int | None = None` (added earlier this session) — this
  feature only activates its "View in PDF" button for citations that
  have a non-null `page_number`.

**Backend changes:**
1. In `documents.py`, add two new route functions at the end of the
   file (after the existing routes), reusing the existing imports
   already at the top of this file (`FileResponse`, `DocumentNotFoundError`,
   `_ensure_document_accessible`, `UPLOAD_DIR`):
   ```python
   @router.get("/documents/{document_id}/file")
   def get_document_file(document_id: str, request: Request) -> FileResponse:
       _ensure_document_accessible(request, document_id)
       matches = list(UPLOAD_DIR.glob(f"{document_id}.*"))
       if not matches:
           raise DocumentNotFoundError(f"No document found with id {document_id}")
       return FileResponse(matches[0], media_type="application/pdf")


   @router.get(
       "/documents/{document_id}/pages/{page_number}/highlight",
       response_model=HighlightResponse,
   )
   def get_page_highlight(
       document_id: str, page_number: int, request: Request, text: str
   ) -> HighlightResponse:
       _ensure_document_accessible(request, document_id)
       matches = list(UPLOAD_DIR.glob(f"{document_id}.*"))
       if not matches:
           raise DocumentNotFoundError(f"No document found with id {document_id}")
       import fitz

       document = fitz.open(matches[0])
       try:
           if page_number < 1 or page_number > document.page_count:
               raise DocumentNotFoundError(f"No page {page_number} in document {document_id}")
           page = document[page_number - 1]
           rects = page.search_for(text)
           return HighlightResponse(
               page_number=page_number,
               page_width=page.rect.width,
               page_height=page.rect.height,
               rects=[[r.x0, r.y0, r.x1, r.y1] for r in rects],
           )
       finally:
           document.close()
   ```
   Add `HighlightResponse` to the existing import from `app.models.schemas`
   at the top of this file.
2. In `schemas.py`, add a new class:
   ```python
   class HighlightResponse(BaseModel):
       page_number: int
       page_width: float
       page_height: float
       rects: list[list[float]] = Field(default_factory=list)
   ```

**Frontend changes:**
1. Add `pdfjs-dist` to `frontend/package.json`'s `dependencies` (this is
   the one new dependency in this entire 13-feature plan — no lighter
   real alternative exists for in-browser PDF rendering).
2. `frontend/src/components/ui/Modal.jsx` currently accepts
   `{ open, onClose, title, children, footer }` and is hard-capped at
   `max-w-md` with no way to override. Add an optional `size` prop,
   defaulting to `"md"` (today's exact unchanged behavior):
   ```jsx
   export default function Modal({ open, onClose, title, children, footer, size = 'md' }) {
     const widthClass = size === 'full' ? 'max-w-4xl' : 'max-w-md'
     // use widthClass in place of the current hard-coded max-w-md class
   }
   ```
3. Create `frontend/src/components/chat/PdfPreviewModal.jsx` — a new
   component using `Modal` with `size="full"`, that on open fetches
   `GET /documents/{documentId}/file` (via the shared `api` axios
   instance from `frontend/src/services/api.js`, using
   `responseType: 'blob'`) and renders it with `pdfjs-dist`, navigated to
   `pageNumber`, additionally fetching
   `GET /documents/{documentId}/pages/{pageNumber}/highlight?text=<excerpt>`
   and drawing the returned `rects` as absolutely-positioned highlight
   overlays scaled from `page_width`/`page_height` to the rendered
   canvas's actual pixel size.
4. `frontend/src/components/chat/SourceReferences.jsx` — inside its
   per-source rendering (where it currently shows the resolved document
   name/icon/label and an expand toggle), add a "View in PDF" button,
   shown only when `source.page_number != null`, that opens
   `PdfPreviewModal` with `{ documentId: source.document_id, pageNumber:
   source.page_number, excerpt: source.excerpt }`.

**Verify:**
- `pytest` — new tests: `GET /documents/{id}/file` returns the right
  bytes for the owning tenant and 404s for a different tenant; the
  highlight route returns a sane (non-empty, when the text genuinely
  appears) or empty (when it doesn't) `rects` list for a known page/text
  combination. Full suite green.
- Live: upload a PDF, ask a question that gets cited with a
  `page_number`, click "View in PDF" on that citation, confirm the PDF
  opens to the correct page with a visible highlight over the cited
  text.

## Prompt 4.2 — Usage analytics dashboard, admin-only

**Goal:** give an admin user a simple usage-analytics view, reading data
this app already logs.

**Context you need:**
- `backend/app/core/permissions.py` (the whole file is short, ~67
  lines): its registry is
  ```python
  DOCUMENT_DELETE = "document_delete"
  DOCUMENT_LIST_ALL_TENANTS = "document_list_all_tenants"

  ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
      "admin": frozenset({DOCUMENT_DELETE, DOCUMENT_LIST_ALL_TENANTS}),
      "member": frozenset(),
  }
  ```
  plus `_DEGRADE_ALLOW_WHEN_NO_ROLE = frozenset({DOCUMENT_DELETE})` (only
  `DOCUMENT_DELETE` defaults to allowed when role is `None`/DB
  disabled — deliberately NOT the pattern to copy for a new analytics
  permission, since analytics should default to denied, not allowed,
  when role can't be determined). `check_permission(request, permission,
  *, message, **log_fields)` reads `request.state.role`, raises
  `ForbiddenError` (403) if not permitted, otherwise returns silently.
- `backend/app/models/db_models.py`'s `UsageLog` model (already exists,
  already populated by existing middleware) has columns: `id,
  request_id, tenant_id, client_name, path, method, status_code,
  latency_ms, created_at`.
- `backend/app/services/user_service.py`'s `get_user_by_id` already
  returns `(email, tenant_id, role)` — role is already computed
  server-side today, just not exposed over `/auth/me`. Check
  `backend/app/api/v1/routes/auth.py`'s `GET /auth/me` handler and
  `CurrentUserResponse` in `schemas.py` directly — if `role` isn't
  already a field there, add it (it may already be present from when
  this route was originally built; verify rather than assume).
- `frontend/src/pages/Settings.jsx`'s exact section order today: Header →
  "Appearance" card → "Data" card → "System status" card (LLM +
  Multi-modal RAG sub-sections, fed by `getHealthStatus()`) → an info
  footer card → a confirm-clear `Modal`. This file does **not** currently
  import `useAuth` at all.
- The frontend `user` object (from `AuthContext.jsx`/`useAuth.js`) has no
  `role` field today — confirmed by reading both files.
- `frontend/package.json` has no chart library — build the visualization
  with plain CSS/flex, matching this repo's current zero-charting
  baseline.

**Backend changes:**
1. In `permissions.py`, add:
   ```python
   ANALYTICS_VIEW = "analytics_view"
   ```
   add it to `ROLE_PERMISSIONS["admin"]`'s frozenset (leave `"member"`'s
   empty frozenset unchanged), and do **not** add it to
   `_DEGRADE_ALLOW_WHEN_NO_ROLE` (analytics should be denied, not
   allowed, when role is unknown).
2. If `CurrentUserResponse` (schemas.py) doesn't already include `role`,
   add `role: str` to it, and confirm `auth.py`'s `/auth/me` handler
   passes it through from `get_user_by_id`'s existing return value.
3. Create `backend/app/api/v1/routes/admin.py`:
   ```python
   """Admin-only operational routes — currently just usage analytics.
   Every route here must call permissions.check_permission first."""

   from datetime import date

   from fastapi import APIRouter, Depends, Request
   from sqlalchemy import func

   from app.core import permissions
   from app.core.auth import require_auth
   from app.core.database import SessionLocal, db_enabled
   from app.models.db_models import UsageLog
   from app.models.schemas import UsageSummaryResponse, UsageSummaryRow

   router = APIRouter(tags=["Admin"], dependencies=[Depends(require_auth)])


   @router.get("/admin/usage-summary", response_model=UsageSummaryResponse)
   def get_usage_summary(request: Request) -> UsageSummaryResponse:
       permissions.check_permission(
           request, permissions.ANALYTICS_VIEW, message="Viewing usage analytics requires the admin role."
       )
       if not db_enabled():
           return UsageSummaryResponse(rows=[])
       with SessionLocal() as db:
           results = (
               db.query(
                   func.date(UsageLog.created_at).label("day"),
                   func.count(UsageLog.id).label("request_count"),
                   func.avg(UsageLog.latency_ms).label("avg_latency_ms"),
               )
               .group_by(func.date(UsageLog.created_at))
               .order_by(func.date(UsageLog.created_at).desc())
               .limit(30)
               .all()
           )
       rows = [
           UsageSummaryRow(day=str(r.day), request_count=r.request_count, avg_latency_ms=round(r.avg_latency_ms or 0, 1))
           for r in results
       ]
       return UsageSummaryResponse(rows=rows)
   ```
   Check `backend/app/core/database.py` for the exact existing
   `SessionLocal`/`db_enabled` import shape used elsewhere (e.g.
   `document_repository.py`) and match it precisely rather than
   guessing.
4. In `schemas.py`, add:
   ```python
   class UsageSummaryRow(BaseModel):
       day: str
       request_count: int
       avg_latency_ms: float

   class UsageSummaryResponse(BaseModel):
       rows: list[UsageSummaryRow] = Field(default_factory=list)
   ```
5. Register the new router in `backend/app/main.py` — find where the
   other routers are registered via `app.include_router(...)` and add
   one for `admin.router`, matching the exact existing style.

**Frontend changes:**
1. Confirm/add `role` to whatever `AuthContext.jsx`/`useAuth.js` stores
   as the `user` object — check how `getMe()` in
   `frontend/src/services/authService.js` currently maps the
   `/auth/me` response, and thread `role` through the same way `email`
   already is.
2. Add `getUsageSummary()` to a new or existing admin-facing service
   file (e.g. `frontend/src/services/adminService.js`), calling
   `GET /admin/usage-summary` via the shared `api` axios instance.
3. In `Settings.jsx`, import `useAuth`, destructure `user`, and add a
   new `<Card padding="lg">` section between the existing "System
   status" card and the info-footer card, gated on
   `user?.role === 'admin'`. Fetch `getUsageSummary()` in a `useEffect`
   the same way this file already fetches `getHealthStatus()`. Render
   each row as a simple flex bar:
   ```jsx
   <div className="flex items-center gap-2 text-xs">
     <span className="w-20 shrink-0 text-slate-500 dark:text-ink-muted">{row.day}</span>
     <div className="h-2 flex-1 rounded bg-slate-900/5 dark:bg-white/[0.05]">
       <div
         className="h-2 rounded bg-accent-500"
         style={{ width: `${Math.min(100, (row.request_count / maxCount) * 100)}%` }}
       />
     </div>
     <span className="w-10 shrink-0 text-right text-slate-500 dark:text-ink-muted">{row.request_count}</span>
   </div>
   ```
   where `maxCount` is the largest `request_count` across all rows,
   computed once for scaling.

**Verify:**
- `pytest` — confirm `GET /admin/usage-summary` returns 403 for a
  non-admin, and a real aggregation for an admin (seed a few
  `UsageLog` rows in the test). Full suite green.
- Live: log in as a non-admin user, confirm Settings shows no analytics
  section; grant your test tenant admin (via `ADMIN_CLIENT_NAMES` or the
  `Tenant.role` column, whichever this app's existing admin-granting
  convention is for your test account), log in again, confirm the
  section appears with real bars reflecting actual request activity.

## Prompt 4.3 — Keyword highlighting in citation excerpts

**Goal:** make citation excerpts scannable by highlighting the terms
from the user's question that actually appear in them. Pure frontend,
zero backend change.

**Context you need:** `frontend/src/components/chat/SourceReferences.jsx`
renders each source with a `CONTENT_TYPE_META`-driven icon/label, and
inside its expand/collapse panel, plain excerpt text:
```jsx
const CONTENT_TYPE_META = {
  image_caption: { icon: ImageIcon, label: 'Figure' },
  table: { icon: Table2, label: 'Table' },
}

export default function SourceReferences({ sources = [], expandedIds, onToggle, sourceRefs }) {
  // ...
  // inside the expand panel: {source.excerpt}
}
```
It's rendered by `frontend/src/components/chat/CitedAnswer.jsx`, which
passes `sources`/`expandedIds`/`onToggle`/`sourceRefs` down — it does
NOT currently pass the user's query text. `ChatBubble.jsx` renders
`<CitedAnswer text={message.content} sources={message.sources} />` — the
user's original query isn't threaded to either component today; you'll
need to find where the user's most recent query is available in
`ChatBubble.jsx`'s scope (check the `message`/surrounding messages list
this component has access to, or thread a new prop down from
`frontend/src/pages/Chat.jsx`, which does have direct access to the
messages array via `useChat()`) and pass it through as a new `query`
prop, `ChatBubble` → `CitedAnswer` → `SourceReferences`.

**Frontend changes:**
1. Add a small pure helper, either inline in `SourceReferences.jsx` or
   in a new tiny `frontend/src/utils/highlightTerms.js`:
   ```js
   const STOPWORDS = new Set(['the', 'a', 'an', 'is', 'are', 'was', 'were', 'what', 'how', 'why', 'does', 'do', 'in', 'on', 'of', 'to', 'and', 'or'])

   export function highlightTerms(excerpt, query) {
     if (!query) return excerpt
     const terms = [...new Set(
       query
         .toLowerCase()
         .split(/\W+/)
         .filter((w) => w.length > 2 && !STOPWORDS.has(w))
     )]
     if (terms.length === 0) return excerpt
     const pattern = new RegExp(`(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi')
     const parts = excerpt.split(pattern)
     return parts.map((part, i) =>
       terms.some((t) => part.toLowerCase() === t) ? (
         <mark key={i} className="rounded bg-accent-500/20 px-0.5 text-inherit">{part}</mark>
       ) : (
         part
       )
     )
   }
   ```
2. Thread a new `query` prop: `SourceReferences({ sources = [], expandedIds, onToggle, sourceRefs, query })`
   → in `CitedAnswer.jsx`, accept and pass through a `query` prop →
   in `ChatBubble.jsx`, accept a new `query` prop passed down from
   wherever it's rendered (`frontend/src/pages/Chat.jsx`'s message-list
   render) — the simplest source for this value is the nearest preceding
   user message's `content` in the `messages` array, found the same way
   this file already finds `lastAssistantId` (`[...messages].reverse().find(...)`)
   — compute the preceding user query per assistant message when
   rendering the list, and pass it as the new prop.
3. In `SourceReferences.jsx`, replace the excerpt's plain
   `{source.excerpt}` rendering with `{highlightTerms(source.excerpt, query)}`.

**Verify:**
- No backend tests needed (no backend change). If this repo has any
  frontend test tooling (check `frontend/package.json`'s scripts — as of
  this session there is none configured), skip automated frontend
  tests; otherwise note that explicitly rather than inventing a test
  setup.
- Live: ask a question, expand a citation card, confirm the words from
  your question that appear in the excerpt are visually highlighted
  (e.g. a subtle background highlight), and that excerpts with no
  matching terms still render normally (no crash, no highlighting).
