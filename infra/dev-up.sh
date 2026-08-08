#!/usr/bin/env bash
# Bring the dev stack up, rebuilding any image that is behind the working tree.
#
# Why this exists: the compose images sat 38 hours behind source during M5, and
# the `astro` container served a /healthz that predated the fact endpoints
# entirely. Every symptom pointed at the code under test; the cause was a stale
# image. An hour went into that, so the check is now the machine's job.
#
#   ./infra/dev-up.sh          # rebuild what is stale, then up -d
#   ./infra/dev-up.sh --check  # report staleness, change nothing (exit 1 if stale)
#   ./infra/dev-up.sh --force  # rebuild everything
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE_FILE="infra/docker-compose.dev.yml"
LABEL="org.sitara.git-sha"
SERVICES=(api astro realtime)

MODE="${1:-up}"
HEAD_SHA="$(git rev-parse HEAD)"
DIRTY=""
if ! git diff --quiet HEAD -- services packages 2>/dev/null; then
  DIRTY="yes"
fi

image_sha() {
  docker image inspect "sitara-dev-$1:latest" \
    --format "{{index .Config.Labels \"$LABEL\"}}" 2>/dev/null || echo ""
}

stale=()
for svc in "${SERVICES[@]}"; do
  built="$(image_sha "$svc")"
  if [[ -z "$built" ]]; then
    printf '  %-9s no image (or unlabelled) — will build\n' "$svc"
    stale+=("$svc")
  elif [[ "$built" != "$HEAD_SHA" ]]; then
    printf '  %-9s STALE  built=%s  head=%s\n' "$svc" "${built:0:8}" "${HEAD_SHA:0:8}"
    stale+=("$svc")
  else
    printf '  %-9s ok     %s\n' "$svc" "${built:0:8}"
  fi
done

if [[ -n "$DIRTY" ]]; then
  # An image can only ever be as fresh as a commit. Uncommitted work in
  # services/ or packages/ is invisible to a build label, so say so rather
  # than let a green check imply the container matches what you are editing.
  echo
  echo "  NOTE: services/ or packages/ have uncommitted changes. An image built"
  echo "        now is labelled ${HEAD_SHA:0:8} but will NOT contain them."
  echo "        For live-reload development use the .claude/launch.json targets"
  echo "        (api :8001, astro :8003, web :3000) instead of containers."
fi

if [[ "$MODE" == "--check" ]]; then
  [[ ${#stale[@]} -eq 0 ]] && { echo; echo "stack images match HEAD"; exit 0; }
  echo
  echo "${#stale[@]} image(s) stale — run ./infra/dev-up.sh"
  exit 1
fi

if [[ "$MODE" == "--force" ]]; then
  stale=("${SERVICES[@]}")
fi

if [[ ${#stale[@]} -gt 0 ]]; then
  echo
  echo "rebuilding: ${stale[*]}"
  docker compose -f "$COMPOSE_FILE" build \
    --build-arg "GIT_SHA=$HEAD_SHA" "${stale[@]}"
fi

docker compose -f "$COMPOSE_FILE" up -d
echo
docker compose -f "$COMPOSE_FILE" ps --format "  {{.Service}}: {{.Status}}"
