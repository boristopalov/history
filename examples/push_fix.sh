#!/bin/sh
# Example external collector: no Python and no daemon, just the HTTP API.
# Usage: ./push_fix.sh <lat> <lon>
# Add `-H "Authorization: Bearer $TOKEN"` if the server has an api_token.
set -eu
now=$(date +%s)
curl --fail --silent --show-error "${HISTORY_URL:-http://127.0.0.1:8765}/ingest" \
  --header 'Content-Type: application/json' \
  --data @- <<JSON
{
  "collector": "shell-example",
  "cursor": "$now",
  "events": [
    {"source": "location", "source_id": "shell-$now", "ts": $now,
     "lat": $1, "lon": $2, "is_fix": true}
  ]
}
JSON
