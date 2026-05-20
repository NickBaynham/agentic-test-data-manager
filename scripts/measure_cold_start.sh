#!/usr/bin/env bash
# Measure docker compose stack cold-start time (5 runs) and report p95.
# Honors NFR-001: stack shall be ready within 60 seconds (p95) on the reference laptop.
#
# Usage: scripts/measure_cold_start.sh [N]
#   N: number of runs (default 5)
#
# This does NOT remove volumes between runs — the docker image layers and pip
# cache are preserved. That matches the "warm start" definition in PLAN.md
# Phase 1. To measure a true cold start (no caches), delete the pip cache
# volume and pull images fresh before running.

set -euo pipefail

cd "$(dirname "$0")/.."

RUNS="${1:-5}"
TIMES=()

echo "[measure_cold_start] $RUNS runs of (make down && make up --wait)"
echo

for i in $(seq 1 "$RUNS"); do
  # Tear down without removing volumes.
  docker compose -f infra/docker-compose.yml down >/dev/null 2>&1 || true

  # Time the next up.
  START=$(date +%s)
  docker compose -f infra/docker-compose.yml up -d --wait >/dev/null
  END=$(date +%s)
  ELAPSED=$((END - START))
  TIMES+=("$ELAPSED")
  echo "  run $i: ${ELAPSED}s"
done

echo
echo "[measure_cold_start] results:"
# Sort and pick p95 (= max for n=5)
SORTED=$(printf "%s\n" "${TIMES[@]}" | sort -n)
P50=$(echo "$SORTED" | awk 'NR==3')
P95=$(echo "$SORTED" | awk 'END{print $0}')

echo "  p50 (median): ${P50}s"
echo "  p95 (max):    ${P95}s"
echo "  NFR-001 budget: 60s p95"

if [ "$P95" -le 60 ]; then
  echo "  status: PASS"
else
  echo "  status: FAIL"
  exit 1
fi
