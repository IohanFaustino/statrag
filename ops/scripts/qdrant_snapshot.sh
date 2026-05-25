#!/usr/bin/env sh
# Snapshot every Qdrant collection, keep last KEEP per collection.
# Runs against $QDRANT_URL (default http://qdrant:6333).
# Snapshots stored inside Qdrant storage dir (host-mounted: data/qdrant/snapshots/<collection>/).
set -eu

QDRANT_URL="${QDRANT_URL:-http://qdrant:6333}"
KEEP="${SNAPSHOT_KEEP:-3}"

echo "[snapshot] target=$QDRANT_URL keep=$KEEP"

# wait for qdrant
i=0
until curl -sf "$QDRANT_URL/healthz" >/dev/null 2>&1; do
  i=$((i+1))
  [ "$i" -gt 60 ] && { echo "[snapshot] qdrant not reachable"; exit 1; }
  sleep 2
done

collections=$(curl -sf "$QDRANT_URL/collections" \
  | sed -n 's/.*"name":"\([^"]*\)".*/\1/p' \
  | tr ',' '\n' \
  | sed 's/.*"name":"\([^"]*\)".*/\1/' \
  | sort -u)

# fallback parse via jq-style with grep
collections=$(curl -sf "$QDRANT_URL/collections" \
  | grep -oE '"name":"[^"]+"' \
  | sed 's/"name":"\(.*\)"/\1/')

echo "[snapshot] collections: $(echo $collections | tr '\n' ' ')"

for c in $collections; do
  echo "[snapshot] creating snapshot for $c"
  curl -sf -X POST "$QDRANT_URL/collections/$c/snapshots" -o /tmp/snap_$c.json || {
    echo "[snapshot] FAILED for $c"; continue;
  }

  # list + prune (keep last $KEEP by creation_time)
  names=$(curl -sf "$QDRANT_URL/collections/$c/snapshots" \
    | grep -oE '"name":"[^"]+"' \
    | sed 's/"name":"\(.*\)"/\1/' \
    | sort)
  total=$(echo "$names" | grep -c . || echo 0)
  excess=$((total - KEEP))
  if [ "$excess" -gt 0 ]; then
    to_delete=$(echo "$names" | head -n "$excess")
    for n in $to_delete; do
      echo "[snapshot] prune $c/$n"
      curl -sf -X DELETE "$QDRANT_URL/collections/$c/snapshots/$n" >/dev/null || true
    done
  fi
done

echo "[snapshot] done"
