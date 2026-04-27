#!/usr/bin/env bash
# local-dev.sh — Build, start, and smoke-test the full stack locally.
#
# Usage:
#   ./scripts/local-dev.sh         bring the stack up and run smoke tests
#   ./scripts/local-dev.sh --down  tear everything down and remove volumes

set -euo pipefail

# Change to the project root no matter where this script is called from.
# $(dirname "$0") is the directory containing this script (scripts/).
# The ".." steps up one level to the project root.
cd "$(dirname "$0")/.."

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

info()  { echo ""; echo "==> $*"; }
pass()  { echo "  PASS  $*"; }
fail()  { echo "  FAIL  $*"; exit 1; }

# --------------------------------------------------------------------------
# Teardown mode
# --------------------------------------------------------------------------

if [[ "${1:-}" == "--down" ]]; then
    info "Tearing down stack and removing volumes..."
    # -v removes the named volumes (postgres_data, redis_data).
    # Without -v, volumes persist and postgres keeps its data across restarts.
    docker compose down -v
    echo "Done."
    exit 0
fi

# --------------------------------------------------------------------------
# Pre-flight checks
# --------------------------------------------------------------------------

info "Pre-flight checks"

# Create .env from the template if it doesn't already exist.
# The real .env is git-ignored so credentials never get committed.
if [[ ! -f ".env" ]]; then
    cp .env.example .env
    echo "  Created .env from .env.example — review passwords before use."
fi

# Refuse to start if port 80 is already bound. Nginx will fail to start
# silently if something else owns port 80, which is hard to diagnose.
if ss -tlnp | grep -q ":80 "; then
    echo "ERROR: Port 80 is already in use. Something is already listening:"
    ss -tlnp | grep ":80 "
    echo "Stop that service first, then re-run this script."
    exit 1
fi
echo "  Port 80 is free."

# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------

info "Building all images..."
docker compose build

# --------------------------------------------------------------------------
# Start
# --------------------------------------------------------------------------

info "Starting stack in detached mode..."
# -d means containers run in the background — control returns to this script.
docker compose up -d

# --------------------------------------------------------------------------
# Wait for healthy
# --------------------------------------------------------------------------

info "Waiting for all services to be healthy (max 120s)..."

TIMEOUT=120
ELAPSED=0
INTERVAL=5

while [[ $ELAPSED -lt $TIMEOUT ]]; do
    # docker compose ps header row starts with NAME — skip it with tail -n +2.
    # Docker Compose v2 STATUS column reads "Up X seconds" not "running".
    UP=$(docker compose ps 2>/dev/null | tail -n +2 | grep -c " Up " || true)
    NOT_READY=$(docker compose ps 2>/dev/null | \
        grep -cE "(health: starting|unhealthy|Exit|Restarting)" || true)

    if [[ $NOT_READY -eq 0 ]] && [[ $UP -eq 6 ]]; then
        echo "  All 6 services are running."
        break
    fi

    printf "  %3ds elapsed — %d/6 running, %d not yet ready\n" \
        "$ELAPSED" "$UP" "$NOT_READY"
    sleep "$INTERVAL"
    ELAPSED=$((ELAPSED + INTERVAL))
done

if [[ $ELAPSED -ge $TIMEOUT ]]; then
    echo ""
    echo "ERROR: Not all services became healthy within ${TIMEOUT}s."
    echo "Current state:"
    docker compose ps
    exit 1
fi

# --------------------------------------------------------------------------
# Smoke tests
# --------------------------------------------------------------------------

info "Running smoke tests..."

# The API runs init_db() at startup. Give it a moment to finish before
# we hit it with requests.
sleep 2

# --- Test 1: POST /shorten ------------------------------------------------
# curl -w appends a newline then the HTTP status code after the response body.
# We split on the last line to separate body from status.
SHORTEN_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST http://localhost/shorten \
    -H "Content-Type: application/json" \
    -d '{"url": "https://example.com/smoke-test"}')

SHORTEN_BODY=$(echo "$SHORTEN_RESPONSE" | head -n 1)
SHORTEN_STATUS=$(echo "$SHORTEN_RESPONSE" | tail -n 1)

if [[ "$SHORTEN_STATUS" != "201" ]]; then
    fail "POST /shorten → HTTP $SHORTEN_STATUS (expected 201). Body: $SHORTEN_BODY"
fi
pass "POST /shorten → 201"

# --- Test 2: GET /<short_code> ---------------------------------------------
# Extract the short_url field from the JSON response using Python's stdlib.
# We use python3 here because jq isn't guaranteed to be installed.
SHORT_URL=$(echo "$SHORTEN_BODY" | \
    python3 -c "import sys, json; print(json.load(sys.stdin)['short_url'])")

# --max-redirs 0 tells curl not to follow the redirect.
# Without this flag, curl would follow the 302 and we'd see a 200 from
# example.com instead of the 302 from our API.
REDIRECT_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    --max-redirs 0 "$SHORT_URL")

if [[ "$REDIRECT_STATUS" != "302" ]]; then
    fail "GET $SHORT_URL → HTTP $REDIRECT_STATUS (expected 302)"
fi
pass "GET  $SHORT_URL → 302"

# --------------------------------------------------------------------------
# Done
# --------------------------------------------------------------------------

VM_IP=$(hostname -I | awk '{print $1}')

echo ""
echo "All smoke tests passed."
echo ""
echo "Stack is up. Useful commands:"
printf "  %-40s %s\n" "docker compose logs -f"       "tail all service logs"
printf "  %-40s %s\n" "docker compose logs -f api"   "tail one service"
printf "  %-40s %s\n" "docker compose ps"            "check service status"
echo ""
echo "Open in a browser:"
printf "  %-40s %s\n" "http://${VM_IP}"        "URL shortener UI"
printf "  %-40s %s\n" "http://${VM_IP}:15672"  "RabbitMQ management UI (guest/guest)"
echo ""
echo "To tear down:  ./scripts/local-dev.sh --down"
