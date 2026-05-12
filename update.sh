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
echo "[2b/5] Updating local/private Strava stream cache..."

# Local-only stream cache for later threshold / HR-drift analysis.
# This writes to data/strava/streams/, which is gitignored and not published.
python scripts/fetch_strava_streams.py --after-days 120 --max-new 25 --include-latlng

echo
echo "[2c/5] Analysing local streams for threshold/drift summaries..."

python scripts/analyse_streams_plus.py --window-min 20 --rolling-days 90

echo
echo "[2c-extra/5] Matching repeated runs locally by GPS efficiency..."
python scripts/run_gps_match_from_config.py

echo
echo "[2d/5] Generating training insights..."

python scripts/generate_training_insights.py
python scripts/generate_training_v2.py
python scripts/generate_data_quality.py

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
  config/runmetrics_config.json \
  docs/index.html \
  docs/app.js \
  docs/style.css \
  docs/data_quality.js \
  docs/training_v2.js \
  docs/insights.js \
  docs/data/summary.json \
  docs/data/daily_metrics.json \
  docs/data/weekly_metrics.json \
  docs/data/activities_recent.json \
  docs/data/data_quality.json \
  docs/data/run_types.json \
  docs/data/efficiency_trends.json \
  docs/data/matched_route_verdicts.json \
  docs/data/steady_fade_verdict.json \
  docs/data/block_review.json \
  docs/data/fun_stats_v2.json \
  docs/data/insights.json \
  docs/data/threshold_history.json \
  docs/data/drift_summary.json \
  docs/data/matched_runs.json \
  docs/data/threshold_history.json \
  docs/data/drift_summary.json \
  scripts/update_static_site.py \
  scripts/generate_data_quality.py \
  scripts/run_gps_match_from_config.py \
  scripts/generate_training_v2.py \
  scripts/match_runs_by_gps_efficiency.py \
  scripts/generate_training_insights.py \
  scripts/analyse_streams_plus.py \
  scripts/fetch_strava_streams.py \
  scripts/analyse_streams.py \
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
