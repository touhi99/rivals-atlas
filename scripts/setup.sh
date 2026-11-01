#!/usr/bin/env bash
# One command to install the backend (Python, with uv) and the front end (Node), and build the web app.
# Run it from anywhere: ./scripts/setup.sh   Afterwards: uv run rivals-atlas serve
set -euo pipefail
cd "$(dirname "$0")/.."

command -v uv >/dev/null || { echo "uv is missing: https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }
command -v npm >/dev/null || { echo "Node.js (npm) is missing: https://nodejs.org/ (version 20 or newer)"; exit 1; }

echo "== backend =="
uv sync

echo "== front end =="
(cd frontend && npm ci && npm run build)

echo
echo "Done. Start the app with:  uv run rivals-atlas serve   (http://127.0.0.1:8000)"
