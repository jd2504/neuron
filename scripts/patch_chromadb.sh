#!/usr/bin/env bash
# Patch chromadb for Python 3.14 compatibility.
# ChromaDB's config.py uses pydantic v1 BaseSettings which fails with
# PEP 649 (deferred annotations) in Python 3.14. Adding
# `from __future__ import annotations` forces PEP 563 string-based
# annotations, which pydantic v1 can handle.
set -euo pipefail

CHROMA_CONFIG="$(python3 -c 'import chromadb.config; print(chromadb.config.__file__)' 2>/dev/null || true)"

if [ -z "$CHROMA_CONFIG" ]; then
    # chromadb hasn't been imported yet; find it manually
    CHROMA_CONFIG="$(python3 -c 'import importlib.util; spec = importlib.util.find_spec(\"chromadb\"); print(spec.submodule_search_locations[0])' 2>/dev/null)/config.py"
fi

if [ ! -f "$CHROMA_CONFIG" ]; then
    echo "Could not find chromadb config.py — skipping patch"
    exit 0
fi

if head -1 "$CHROMA_CONFIG" | grep -q "from __future__"; then
    echo "chromadb config.py already patched"
    exit 0
fi

sed -i '1i from __future__ import annotations\n' "$CHROMA_CONFIG"
echo "Patched $CHROMA_CONFIG for Python 3.14 compatibility"
