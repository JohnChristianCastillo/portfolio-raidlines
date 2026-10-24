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
# Only a branch that does not exist is a reason to build without data. Anything else
# that goes wrong must fail the build, so Cloudflare keeps serving the last good
# deploy. An earlier version treated every failed fetch as "no branch yet", and one
# transient fetch error replaced the live site with an empty one that reported
# success.
#
# ls-remote --exit-code returns 2 for "no such branch" and something else for a
# network or auth failure, which is the distinction that matters here.
state=""
for wait in 5 15 45 0; do
  code=0
  git ls-remote --exit-code --heads origin data >/dev/null || code=$?
  if [ "$code" -eq 2 ]; then
    state=missing
    break
  fi
  if [ "$code" -eq 0 ] && git fetch --depth 1 origin data; then
    state=fetched
    break
  fi
  if [ "$wait" -gt 0 ]; then
    echo "reaching the data branch failed, retrying in ${wait}s"
    sleep "$wait"
  fi
done

if [ "$state" = missing ]; then
  # A first deploy happens before any snapshot exists. Build anyway: the page says
  # it has no data rather than failing the deploy.
  echo "no data branch yet, building without a snapshot"
  mkdir -p frontend/public/data
elif [ "$state" != fetched ]; then
  echo "could not fetch the data branch; failing so the live site stays as it is" >&2
  exit 1
else
  rm -rf frontend/public/data
  mkdir -p frontend/public
  # git archive rather than git checkout, so the index is never touched. Harmless
  # here since nothing commits, but the same line in the refresh workflow put a whole
  # snapshot onto main, and having one form in both places keeps that from returning.
  git archive FETCH_HEAD data | tar -x
  mv data frontend/public/data
  if [ ! -f frontend/public/data/manifest.json ]; then
    echo "the data branch has no manifest.json; refusing to deploy without it" >&2
    exit 1
  fi
  echo "snapshot: $(find frontend/public/data -name '*.json' | wc -l) files"
fi

echo "--- building ---"
cd frontend
npm ci --no-audit --no-fund
npm run build
