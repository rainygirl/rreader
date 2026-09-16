#!/bin/bash
# Generate today's podcast episode (skips if already done today; --force to redo).
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"  # uv lives here under cron/sudo
uv run python generate_podcast.py "$@"
