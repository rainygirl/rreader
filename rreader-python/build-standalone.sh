#!/bin/sh

pyinstaller --onefile --strip --clean --name rreader \
  --add-data "src/rreader/feeds.json:rreader" \
  --collect-all asciimatics \
  --hidden-import feedparser \
  --hidden-import wcwidth \
  --hidden-import PIL \
  src/rreader/run.py
