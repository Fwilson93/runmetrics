#!/usr/bin/env bash
set -euo pipefail

# Run from repo root.
python scripts/update_static_site.py

# Hard stop if anything sensitive appears in the public site folder.
if grep -RInE 'STRAVA_CLIENT_SECRET|STRAVA_REFRESH_TOKEN|access_token|refresh_token|client_secret|summary_polyline|start_latlng|end_latlng|external_id|upload_id' docs/; then
  echo "ERROR: possible secret/private Strava field found in docs/. Aborting." >&2
  exit 1
fi

# GitHub Pages generally serves from docs/ on the selected branch.
git add docs/index.html docs/app.js docs/style.css docs/data/ scripts/update_static_site.py scripts/publish_site.sh

if git diff --cached --quiet; then
  echo "No static dashboard changes to commit."
else
  git commit -m "Update RunMetrics static dashboard"
fi

git push
