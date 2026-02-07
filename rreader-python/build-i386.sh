#!/bin/bash

set -e

echo "=== rreader Python build for i386 (static, no glibc) ==="
echo "Requires Docker"
echo ""

docker run --rm -v "$(pwd)":/app -w /app --platform linux/386 alpine:3.19 sh -c '
  apk add --no-cache \
    python3 python3-dev py3-pip \
    gcc musl-dev linux-headers \
    jpeg-dev zlib-dev freetype-dev \
    ncurses ncurses-dev ncurses-libs \
    binutils &&
  python3 -m venv /tmp/build-venv &&
  . /tmp/build-venv/bin/activate &&
  pip install --upgrade pip &&
  pip install pyinstaller &&
  pip install . &&
  pyinstaller \
    --onefile \
    --strip \
    --name rreader \
    --add-data "src/rreader/feeds.json:rreader" \
    --collect-all asciimatics \
    --hidden-import feedparser \
    --hidden-import wcwidth \
    --hidden-import PIL \
    src/rreader/run.py &&
  cp dist/rreader /app/rreader-i386
'

echo ""
echo "Build complete!"
echo "Binary location: rreader-i386"
