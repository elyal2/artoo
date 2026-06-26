#!/bin/bash
set -o errexit

PORT="${OPENCODE_PORT:-19826}"
HOSTNAME="${OPENCODE_HOSTNAME:-127.0.0.1}"
PROJECT_ROOT="$(pwd)"
STATE_DIR="${PROJECT_ROOT}/.opencode"
SESSION_FILE="${STATE_DIR}/session"
PORT_FILE="${STATE_DIR}/port"
REGENERATE_SESSION=0
SESSION_ID=""

usage() {
  printf 'Usage: %s [session_id] [--new]\n' "$0"
  printf '  session_id  use and persist an explicit session id for this project\n'
  printf '  --new       generate a new session id for this project\n'
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --new)
      REGENERATE_SESSION=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    ses_*)
      if [ -n "$SESSION_ID" ]; then
        printf 'Only one session id can be provided\n' >&2
        exit 1
      fi
      SESSION_ID="$1"
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

mkdir -p "$STATE_DIR"

if [ -f "$PORT_FILE" ]; then
  PORT="$(tr -d '\n' < "$PORT_FILE")"
else
  PROJECT_HASH="$(printf '%s' "$PROJECT_ROOT" | shasum | cut -c1-8)"
  PORT="$((20000 + (0x$PROJECT_HASH % 20000)))"
  printf '%s\n' "$PORT" > "$PORT_FILE"
fi

URL="http://${HOSTNAME}:${PORT}"

if [ -n "$SESSION_ID" ]; then
  printf '%s\n' "$SESSION_ID" > "$SESSION_FILE"
elif [ "$REGENERATE_SESSION" -eq 1 ] || [ ! -f "$SESSION_FILE" ]; then
  SESSION_ID="ses_$(LC_ALL=C tr -dc 'a-z0-9' </dev/urandom | head -c 24)"
  printf '%s\n' "$SESSION_ID" > "$SESSION_FILE"
else
  SESSION_ID="$(tr -d '\n' < "$SESSION_FILE")"
fi

printf 'Project session: %s\n' "$SESSION_ID"
printf 'Endpoint: %s\n' "$URL"

server_running() {
  curl -fsS "$URL/global/health" >/dev/null 2>&1
}

if ! server_running; then
  printf 'Starting OpenCode server on port %s...\n' "$PORT"
  exec opencode --hostname "$HOSTNAME" --port "$PORT" -s "$SESSION_ID" "$PROJECT_ROOT"
fi

printf 'Using session: %s\n' "$SESSION_ID"
exec opencode attach "$URL" -s "$SESSION_ID"
