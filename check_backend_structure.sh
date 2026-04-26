#!/usr/bin/env bash
set -e

echo "=== RunMetrics backend sanity check ==="
echo

ROOT="backend/app"
ok()   { echo "✅ $1"; }
fail() { echo "❌ $1"; exit 1; }

check_dir () { [[ -d "$1" ]] && ok "Directory exists: $1" || fail "Missing directory: $1"; }
check_file () { [[ -f "$1" ]] && ok "File exists: $1" || fail "Missing file: $1"; }
check_nonempty () { [[ -s "$1" ]] && ok "File is non-empty: $1" || fail "File is empty (should contain code): $1"; }

echo "Checking directory structure..."
check_dir "$ROOT"
check_dir "$ROOT/api"
check_dir "$ROOT/db"
echo

echo "Checking __init__.py package markers..."
check_file "$ROOT/__init__.py"
check_file "$ROOT/api/__init__.py"
check_file "$ROOT/db/__init__.py"
echo

echo "Checking required code files..."
check_file "$ROOT/main.py"
check_file "$ROOT/api/health.py"
check_file "$ROOT/api/ping.py"
check_file "$ROOT/api/strava_oauth.py"
check_file "$ROOT/api/ingest.py"
check_file "$ROOT/db/session.py"
check_file "$ROOT/db/models.py"
echo

echo "Checking files that must contain code..."
check_nonempty "$ROOT/main.py"
check_nonempty "$ROOT/api/health.py"
check_nonempty "$ROOT/api/ping.py"
check_nonempty "$ROOT/api/strava_oauth.py"
check_nonempty "$ROOT/api/ingest.py"
check_nonempty "$ROOT/db/session.py"
check_nonempty "$ROOT/db/models.py"
echo

echo "Checking critical imports..."
grep -q "from app.db.session import SessionLocal" "$ROOT/api/strava_oauth.py" \
  && ok "strava_oauth.py imports SessionLocal" \
  || fail "Missing import: SessionLocal in strava_oauth.py"

grep -q "from app.db.models import StravaToken" "$ROOT/api/strava_oauth.py" \
  && ok "strava_oauth.py imports StravaToken" \
  || fail "Missing import: StravaToken in strava_oauth.py"

grep -q "from app.db.models import StravaToken, Activity" "$ROOT/api/ingest.py" \
  && ok "ingest.py imports StravaToken, Activity" \
  || fail "Missing import: StravaToken, Activity in ingest.py"

grep -q "Base.metadata.create_all" "$ROOT/main.py" \
  && ok "DB tables initialised in main.py" \
  || fail "DB tables not initialised in main.py"

echo
echo "🎉 All backend structure checks passed."
