#!/usr/bin/env bash
set -euo pipefail

echo "Installing Python dev dependencies..."
pip install --quiet -e ./controller[dev]

echo "NOTE: docker compose stack removed; skipping image pull."

echo "Setup complete. auto-browser will start automatically."
