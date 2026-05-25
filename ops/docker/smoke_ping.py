#!/usr/bin/env python3
"""
Smoke test for the Qdrant vector DB container.
Requires only: qdrant-client (no other project dependencies).

Usage:
    python smoke_ping.py

Exit codes:
    0 - all checks passed
    1 - one or more checks failed
"""
import sys

COLLECTION_NAME = "smoke_test"
HOST = "localhost"
PORT = 6333

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
    # query_points was introduced in qdrant-client 1.7+; search() was removed in 1.14+
    try:
        from qdrant_client.models import QueryRequest  # noqa: F401 — just a presence check
    except ImportError:
        pass
    _CLIENT_AVAILABLE = True
except ImportError:
    _CLIENT_AVAILABLE = False


def main() -> int:
    if not _CLIENT_AVAILABLE:
        print(
            "SKIP: qdrant-client is not installed on this host. "
            "Install with: pip install qdrant-client\n"
            "Live smoke test skipped — container health is the primary readiness signal."
        )
        return 0

    # 1. Connect
    try:
        client = QdrantClient(host=HOST, port=PORT)
    except Exception as exc:
        print(f"ERROR: Failed to create QdrantClient: {exc}")
        return 1

    # 2. List existing collections
    try:
        collections = client.get_collections()
        names = [c.name for c in collections.collections]
        print(f"get_collections OK  existing collections: {names}")
    except Exception as exc:
        print(f"ERROR: get_collections failed: {exc}")
        return 1

    # 3. Create throwaway collection (idempotent: delete first if it exists)
    try:
        if client.collection_exists(COLLECTION_NAME):
            client.delete_collection(COLLECTION_NAME)
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=4, distance=Distance.COSINE),
        )
        print(f"collection created: {COLLECTION_NAME!r}")
    except Exception as exc:
        print(f"ERROR: could not create collection: {exc}")
        return 1

    # 4. Upsert one point
    try:
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                PointStruct(
                    id=1,
                    vector=[0.1, 0.9, 0.3, 0.7],
                    payload={"label": "smoke_doc"},
                )
            ],
        )
        print("upsert OK")
    except Exception as exc:
        print(f"ERROR: upsert failed: {exc}")
        _cleanup(client)
        return 1

    # 5. Query the collection
    # qdrant-client >= 1.14 uses query_points(); older versions used search().
    try:
        if hasattr(client, "query_points"):
            response = client.query_points(
                collection_name=COLLECTION_NAME,
                query=[0.1, 0.9, 0.3, 0.7],
                limit=1,
            )
            results = response.points
        else:
            results = client.search(
                collection_name=COLLECTION_NAME,
                query_vector=[0.1, 0.9, 0.3, 0.7],
                limit=1,
            )
        top = results[0] if results else None
        print(f"search OK  top result id={top.id if top else None} score={top.score if top else None}")
    except Exception as exc:
        print(f"ERROR: search failed: {exc}")
        _cleanup(client)
        return 1

    # 6. Delete the throwaway collection
    _cleanup(client)

    print("smoke_ping PASSED")
    return 0


def _cleanup(client: "QdrantClient") -> None:
    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"collection {COLLECTION_NAME!r} deleted")
    except Exception as exc:
        print(f"WARN: cleanup failed (collection may already be absent): {exc}")


if __name__ == "__main__":
    sys.exit(main())
