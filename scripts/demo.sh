#!/usr/bin/env bash
# Phase 9 end-to-end demo orchestration.
#
# Runs the full intent → seed → test → reset → audit flow against the local
# stack. Budget: ≤90 seconds. Exits 0 on success and prints a link to the
# audit UI for the reviewer to open in a browser.
#
# Usage:
#   make demo              (preferred — make brings the stack up first)
#   ./scripts/demo.sh      (if the stack is already up)

set -euo pipefail
START_AT=$(date +%s)

cd "$(dirname "$0")/.."

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
: "${ATDM_API_URL:=http://localhost:18001}"
: "${ATDM_API_TOKEN:=dev-token-change-me}"
: "${ATDM_CLI_OUTPUT:=json}"
SCENARIO="${SCENARIO:-claim_denial_active_member}"
DEMO_BUDGET_SECONDS=90

export ATDM_API_URL ATDM_API_TOKEN ATDM_CLI_OUTPUT

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
sep() { printf "\n========== %s ==========\n" "$1"; }
err() { printf "demo: %s\n" "$1" >&2; exit 1; }

# Require jq for nicer output; fall back if missing.
have_jq() { command -v jq >/dev/null 2>&1; }
JQ_OR_CAT() { if have_jq; then jq .; else cat; fi; }

# ---------------------------------------------------------------------------
# 0. Stack must be up. We poll /health rather than running `make up` here so
#    the demo script remains idempotent and quick on warm stacks.
# ---------------------------------------------------------------------------
sep "0. stack health"
DEADLINE=$(( $(date +%s) + 30 ))
while true; do
  if curl -fsS "${ATDM_API_URL}/health" >/dev/null 2>&1; then
    echo "agent is up"
    break
  fi
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then
    err "stack is not healthy. Run 'make up' first."
  fi
  sleep 1
done

# ---------------------------------------------------------------------------
# 1. Request a scenario with both fixture flavours.
# ---------------------------------------------------------------------------
sep "1. atdm request ${SCENARIO}"
REQUEST_RESP=$(pdm run atdm request "${SCENARIO}" --playwright --pytest 2>&1)
echo "$REQUEST_RESP" | JQ_OR_CAT

if ! have_jq; then
  err "this demo prints JSON via jq for readability; install jq (or set ATDM_CLI_OUTPUT=human and re-parse)"
fi

RUN_ID=$(echo "$REQUEST_RESP" | jq -r .test_run_id)
TOKEN=$(echo "$REQUEST_RESP" | jq -r .cleanup.cleanup_token)
PYTEST_FIXTURE_CONTAINER=$(echo "$REQUEST_RESP" | jq -r .fixtures.pytest)
PLAYWRIGHT_FIXTURE_CONTAINER=$(echo "$REQUEST_RESP" | jq -r .fixtures.playwright)

# Translate /fixtures/<file> (container path) → automation/fixtures/<file> (host)
PYTEST_FIXTURE_HOST="automation/fixtures/$(basename "$PYTEST_FIXTURE_CONTAINER")"
PLAYWRIGHT_FIXTURE_HOST="automation/fixtures/$(basename "$PLAYWRIGHT_FIXTURE_CONTAINER")"

echo
echo "test_run_id:        ${RUN_ID}"
echo "cleanup_token:      ${TOKEN:0:16}..."
echo "pytest fixture:     ${PYTEST_FIXTURE_HOST}"
echo "playwright fixture: ${PLAYWRIGHT_FIXTURE_HOST}"

# ---------------------------------------------------------------------------
# 2. Run the example pytest against the just-emitted fixture.
# ---------------------------------------------------------------------------
sep "2. pytest automation/pytest-api/test_example_claim_denial.py"
ATDM_FIXTURE_FILE="${PYTEST_FIXTURE_HOST}" \
  PYTHONPATH=apps/test-data-agent/python \
  pdm run pytest \
  automation/pytest-api/test_example_claim_denial.py \
  -v --no-header -p no:cacheprovider

# ---------------------------------------------------------------------------
# 3. Reset the run (cleanup-token-gated).
# ---------------------------------------------------------------------------
sep "3. atdm reset ${RUN_ID}"
pdm run atdm reset "${RUN_ID}" --token "${TOKEN}" | JQ_OR_CAT

# ---------------------------------------------------------------------------
# 4. Print the audit trail (chronological actions only — full JSON in /metrics).
# ---------------------------------------------------------------------------
sep "4. atdm audit ${RUN_ID}"
pdm run atdm audit "${RUN_ID}" | jq '{
  run_id,
  scenario_id,
  reset_status,
  events: [.events[] | {action, status, timestamp}]
}'

# ---------------------------------------------------------------------------
# 5. Done — point the reviewer at the UI.
# ---------------------------------------------------------------------------
END_AT=$(date +%s)
ELAPSED=$((END_AT - START_AT))

sep "demo complete in ${ELAPSED}s"
echo "Open this URL in a browser to inspect the run as a reviewer would:"
echo "  ${ATDM_API_URL}/ui/audit/${RUN_ID}"
echo
echo "Other useful URLs:"
echo "  MinIO console: http://localhost:19001  (creds in .env.example)"
echo "  Agent Swagger: ${ATDM_API_URL}/docs"
echo "  SUT Swagger:   http://localhost:18000/docs"

if [ "${ELAPSED}" -gt "${DEMO_BUDGET_SECONDS}" ]; then
  echo
  echo "WARNING: demo took ${ELAPSED}s, exceeded the ${DEMO_BUDGET_SECONDS}s budget."
  exit 1
fi

exit 0
