#!/usr/bin/env bash
set -euo pipefail

echo "============================================================"
echo "RunMetrics update"
echo "============================================================"

# Always run from the repository root, even if called from elsewhere.
cd "$(git rev-parse --show-toplevel)"

echo
echo "[1/5] Checking required files..."

if [[ ! -f "scripts/update_static_site.py" ]]; then
  echo "ERROR: scripts/update_static_site.py not found."
  echo "Run the bootstrap script first, or restore the static-site updater."
  exit 1
fi

if [[ ! -f ".env" ]]; then
  echo "WARNING: .env not found. Continuing, but Strava credentials must be in your shell environment."
fi

echo "OK."

echo
echo "[2/5] Updating static dashboard data..."

python scripts/update_static_site.py

echo
echo "[3/5] Privacy/secret scan of docs/..."

# These should never appear in public GitHub Pages output.
if grep -RInE \
  'STRAVA_CLIENT_SECRET|STRAVA_REFRESH_TOKEN|access_token|refresh_token|client_secret|summary_polyline|start_latlng|end_latlng|external_id|upload_id|athlete_id|Authorization|Bearer ' \
  docs/
then
  echo
  echo "ERROR: possible secret/private Strava field found in docs/. Aborting before commit."
  echo "Inspect the grep output above."
  exit 1
fi

echo "OK: no obvious secrets/private Strava fields found in docs/."

echo
echo "[4/5] Staging public dashboard files..."

git add \
  docs/index.html \
  docs/app.js \
  docs/style.css \
  docs/data/summary.json \
  docs/data/daily_metrics.json \
  docs/data/weekly_metrics.json \
  docs/data/activities_recent.json \
  scripts/update_static_site.py \
  update.sh

echo
echo "[5/5] Commit and push..."

if git diff --cached --quiet; then
  echo "No dashboard changes to commit."
else
  stamp="$(date '+%Y-%m-%d %H:%M')"
  git commit -m "Update RunMetrics dashboard ${stamp}"
fi

git push

echo
echo "============================================================"
echo "RunMetrics update complete."
echo "============================================================"
