#!/bin/sh

uv sync --extra gemini --extra dev

uv run pyinstaller --onefile --strip --clean --name rreader \
  --add-data "src/rreader/feeds.json:rreader" \
  --collect-all asciimatics \
  --hidden-import feedparser \
  --hidden-import wcwidth \
  --hidden-import PIL \
  --hidden-import google.genai \
  --hidden-import requests \
  --hidden-import bs4 \
  src/rreader/run.py
