#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8765}"

echo "=== Ingesting all PDFs ==="

for pdf in texts/*.pdf; do
    echo "Ingesting: $pdf"
    curl -s -X POST "$BASE_URL/ingest" \
        -H "Content-Type: application/json" \
        -d "{\"pdf_path\": \"$pdf\"}" \
        --max-time 1800
    echo
done

echo
echo "=== Health check ==="
curl -s "$BASE_URL/health" | python3 -m json.tool
