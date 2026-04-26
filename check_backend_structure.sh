#!/usr/bin/env bash
set -e
ROOT="backend/app"
check() { [[ -e "$1" ]] || { echo "❌ Missing $1"; exit 1; }; }
check backend/app/main.py
check backend/app/api/analytics.py
check web/index.html
check web/script.js
echo "✅ Basic checks passed."
