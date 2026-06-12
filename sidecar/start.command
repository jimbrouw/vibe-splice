#!/bin/bash
# Double-click this file on macOS to start the Vibe Splice sidecar in Terminal.
# The panel's Start button opens this file via uxp.shell.openPath().
set -e
cd "$(dirname "$0")"
if [ ! -f "../.venv/bin/uvicorn" ]; then
  echo "ERROR: .venv not found. Run from the repo root:"
  echo "  python3 -m venv .venv && .venv/bin/pip install -r sidecar/requirements.txt"
  read -r -p "Press Enter to close."
  exit 1
fi
echo "Starting Vibe Splice sidecar on http://127.0.0.1:8765 ..."
../.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765
