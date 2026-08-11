"""Unauthorized Access Rate check for the two real authorization gates on
DELETE /documents/{id}: tenant ownership (app/api/v1/routes/documents.py)
and the admin/member role gate (Tenant.role, added alongside this script).

Rate = Successful Unauthorized Actions / Unauthorized Attempts, desired
value zero — same framing as the checklist's other zero-desired metrics
(false_refusal_rate, data_leak_rate in eval/run_eval.py). Three distinct
attempt shapes, each of which the route is supposed to deny:

1. Cross-tenant delete: requester's tenant_id != the document's owner
   tenant_id (a genuinely different pair of ids from #2, so a
   hardcoded-id bug in the check wouldn't slip through both).
2. Same shape as #1 with a second, unrelated pair of tenant ids.
3. Same-tenant delete from a "member" role client — exercises the role
   gate specifically, not the tenant gate (a "member" in the *same*
   tenant as the document's owner would pass the tenant check and must
   be denied by role alone).

Deliberately does NOT test the "no tenant info at all" path (DB
disabled, or a legacy document with no owner row) — that's a documented,
*accepted* gap (see documents.py's own comment: the ownership check is
"only enforced when we can actually verify it"), not something this
metric should flag as a failure.

Uses FastAPI's TestClient against the real app — real routes, real
auth/role-gate code — with only the vector store, LLM, embedding, and
tenant/ownership resolution mocked, mirroring tests/test_security.py's
`client` fixture exactly (same boundary-mocking style, just two
registered clients instead of one, which no existing fixture in this
repo does — see this script's `_client_context()`). No live LLM, no
network, no DATABASE_URL needed — resolve_tenant/get_document_owner are
mocked directly rather than requiring a real Postgres instance, the same
simplification test_main.py's own cross-tenant delete tests already make.

Usage (from backend/):
    python eval/unauthorized_access_check.py
"""

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.models.document import EmbeddedChunk  # noqa: E402
from app.services.faiss_vector_store import FAISSVectorStore  # noqa: E402

FAKE_EMBEDDING_DIM = 8
FAKE_EMBEDDING = [1.0] + [0.0] * (FAKE_EMBEDDING_DIM - 1)
DOCUMENT_ID = "22222222-2222-2222-2222-222222222222"

# Client B's key never needs to map to a real seeded document — only
# client A's key does — but both must be registered so require_api_key
# resolves a real client_name for each, exactly like a live deployment
# with two API_KEYS entries would.
CLIENT_A_KEY = "unauth-check-client-a-key"
CLIENT_B_KEY = "unauth-check-client-b-key"


@contextmanager
def _client_context(tmp_path: Path):
    """Yields a TestClient with one seeded document, two registered API
    keys (client-a/client-b), and vector-store/LLM/embedding mocked —
    the same boundary-mocking style as tests/test_security.py's `client`
    fixture, extended to two clients since resolving *different*
    tenant_ids for different callers is the whole point of this check."""
    store = FAISSVectorStore(
        index_path=tmp_path / "index.faiss",
        metadata_path=tmp_path / "metadata.json",
    )
    store.create_index(dimension=FAKE_EMBEDDING_DIM)
    store.add_embeddings(
        [
            EmbeddedChunk(
                chunk_id="chunk-1",
                document_id=DOCUMENT_ID,
                embedding=FAKE_EMBEDDING,
                metadata={"chunk_index": 0, "total_chunks": 1, "source": "pdf", "text": "irrelevant"},
            )
        ]
    )

    original_api_keys = settings.api_keys
    settings.api_keys = json.dumps({"client-a": CLIENT_A_KEY, "client-b": CLIENT_B_KEY})
    try:
        with (
            patch("app.api.v1.routes.query.get_vector_store", lambda: store),
            patch("app.api.v1.routes.documents.get_vector_store", lambda: store),
            TestClient(app) as test_client,
        ):
            yield test_client
    finally:
        settings.api_keys = original_api_keys


def _attempt_delete(
    tmp_path: Path,
    requester_tenant: tuple[int, str],
    owner_tenant_id: int,
    label: str,
) -> tuple[bool, int]:
    """One unauthorized-attempt trial. Returns (denied, status_code).
    denied=True is the desired outcome (the checklist's "zero" case)."""
    with _client_context(tmp_path) as client:
        with (
            patch("app.core.auth.resolve_tenant", lambda client_name: requester_tenant),
            patch("app.api.v1.routes.documents.get_document_owner", lambda document_id: owner_tenant_id),
        ):
            response = client.delete(
                f"/documents/{DOCUMENT_ID}",
                params={"confirm": "true"},
                headers={"X-API-Key": CLIENT_B_KEY},
            )
    denied = response.status_code in (403, 404)
    print(f"  {label:<45s} status={response.status_code} {'DENIED (ok)' if denied else 'SUCCEEDED (BAD)'}")
    return denied, response.status_code


def main() -> None:
    import tempfile

    print("=== Unauthorized Access Rate (DELETE /documents/{id}) ===\n")

    results: list[bool] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        denied, _ = _attempt_delete(
            tmp_path,
            requester_tenant=(2, "admin"),
            owner_tenant_id=1,
            label="cross-tenant delete (tenant 2 -> tenant 1's doc)",
        )
        results.append(denied)

        denied, _ = _attempt_delete(
            tmp_path,
            requester_tenant=(99, "admin"),
            owner_tenant_id=5,
            label="cross-tenant delete (tenant 99 -> tenant 5's doc)",
        )
        results.append(denied)

        denied, _ = _attempt_delete(
            tmp_path,
            requester_tenant=(1, "member"),
            owner_tenant_id=1,
            label="same-tenant delete, member role (role gate)",
        )
        results.append(denied)

    total_attempts = len(results)
    successful_unauthorized = sum(1 for denied in results if not denied)
    rate = successful_unauthorized / total_attempts if total_attempts else None

    print(f"\nUnauthorized attempts: {total_attempts}")
    print(f"Successful unauthorized actions: {successful_unauthorized}  (desired: 0)")
    print(f"Unauthorized Access Rate: {rate:.4f}" if rate is not None else "Unauthorized Access Rate: n/a")

    if successful_unauthorized:
        print("\nFAIL -- at least one unauthorized action succeeded.")
        sys.exit(1)
    print("\nPASS -- no unauthorized action succeeded.")


if __name__ == "__main__":
    main()
