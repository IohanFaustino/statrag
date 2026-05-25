# Docker stack — Quickstart

Compose now manages **4 services**: `qdrant` (vector DB), `statrag-chat` (FastAPI :8765), `statrag-web` (nginx :5173 serving Vite build + proxying `/api` → chat), and `qdrant-backup` (oneshot snapshot job).

## Start the full stack

From the project root:

```bash
docker compose -f ops/docker/docker-compose.yml up -d --build
```

Qdrant alone (host dev mode):

```bash
docker compose -f ops/docker/docker-compose.yml up -d qdrant
```

## Backup routine

`qdrant-backup` runs automatically on every `up`/restart:
- Calls Qdrant snapshot API per collection
- Stores under `/qdrant/snapshots/<collection>/` (host-mounted: `data/qdrant_snapshots/`)
- Prunes to last `SNAPSHOT_KEEP=3` per collection

Trigger manually:

```bash
docker compose -f ops/docker/docker-compose.yml run --rm qdrant-backup
```

Restore a snapshot:

```bash
curl -X PUT "http://localhost:6333/collections/<coll>/snapshots/recover" \
  -H "Content-Type: application/json" \
  -d '{"location":"file:///qdrant/snapshots/<coll>/<file>.snapshot"}'
```

## Verify the container is healthy

```bash
docker ps   # STATUS should show "(healthy)" after ~15 s
```

Or poll explicitly:

```bash
docker inspect qdrant --format '{{.State.Health.Status}}'
```

## Dashboard

Open the Qdrant web UI at:

```
http://localhost:6333/dashboard
```

## Smoke test

Activate your project virtualenv, then:

```bash
python docker/smoke_ping.py
```

The script requires `qdrant-client` on the host:

```bash
pip install qdrant-client
```

If `qdrant-client` is not installed, the script exits 0 and notes the skip —
container health is the primary readiness signal.

## Connection details

| Protocol | Host URL                    |
|----------|-----------------------------|
| REST     | http://localhost:6333        |
| gRPC     | localhost:6334               |

Connect from Python:

```python
from qdrant_client import QdrantClient
client = QdrantClient(host="localhost", port=6333)
```

## Stop the container (data is kept)

```bash
docker compose -f docker/docker-compose.yml down
```

Vector data is persisted at `data/qdrant/` and survives container restarts.

## Preserved Chroma data

The previous Chroma vector store is preserved at `data/chroma/` for rollback
safety. Do NOT delete it until you have confirmed the migration to Qdrant is
successful and all collections have been re-ingested.

When you are ready to clean it up:

```bash
rm -rf data/chroma/
```

Only run this command after you have verified Qdrant is serving all required
collections and the old Chroma data is no longer needed.
