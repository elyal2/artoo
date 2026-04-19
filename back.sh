#!/bin/bash
set -o errexit

SESSION_ID="${1:-ses_26270520affePS615CCiIlOZut}"
PORT=19826
URL="http://localhost:$PORT"

echo "Checking if port $PORT is already in use..."

if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "Port $PORT is already in use. Attaching to existing session..."
    opencode attach "$URL" -s "$SESSION_ID"
else
    echo "Opening opencode session: $SESSION_ID"
    echo "Open Code will be available at $URL"
    opencode --port $PORT -s "$SESSION_ID"
fi