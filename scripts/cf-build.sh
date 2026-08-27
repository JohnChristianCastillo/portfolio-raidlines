#!/usr/bin/env bash
# The build Cloudflare Pages runs.
#
# Set this as the build command:   bash scripts/cf-build.sh
# and the output directory to:     frontend/dist
#
# main carries the code, the orphan 'data' branch carries the snapshot, and this
# brings them together at build time. Keeping them apart is what stops a repeated
# multi-megabyte snapshot from bloating main's history forever.
set -euo pipefail

echo "--- fetching the snapshot from the data branch ---"
if git fetch --depth 1 origin data 2>/dev/null; then
  rm -rf frontend/public/data
  mkdir -p frontend/public
  # git archive rather than git checkout, so the index is never touched. Harmless
  # here since nothing commits, but the same line in the refresh workflow put a whole
  # snapshot onto main, and having one form in both places keeps that from returning.
  git archive FETCH_HEAD data | tar -x
  mv data frontend/public/data
  echo "snapshot: $(find frontend/public/data -name '*.json' | wc -l) files"
else
  # A first deploy happens before any snapshot exists. Build anyway: the page says
  # it has no data rather than failing the deploy.
  echo "no data branch yet, building without a snapshot"
  mkdir -p frontend/public/data
fi

echo "--- building ---"
cd frontend
npm ci --no-audit --no-fund
npm run build
