#!/usr/bin/env bash
set -e
echo "=== RunMetrics backend sanity check ==="
ROOT="backend/app"
[[ -f "$ROOT/api/pmc.py" ]] || { echo "❌ Missing backend/app/api/pmc.py"; exit 1; }
python -m py_compile backend/app/api/pmc.py backend/app/main.py backend/app/db/models.py
echo "✅ OK"
