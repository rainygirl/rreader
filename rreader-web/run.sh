#!/bin/bash
# Regenerate output/index.html. Static files only; no web server reload needed.
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"  # uv lives here on the server (root cron / sudo strip it from PATH)
uv run python generate.py
