# rreader-haiku-native

A native Haiku OS app (BApplication/BWindow, Interface Kit + Network Kit +
Translation Kit) that fetches the live [news.coroke.net](https://news.coroke.net)
page and redraws it natively -- same design as rreader-web, but as a real
Haiku GUI app instead of a browser tab.

**⚠️ Not yet built or run.** This was written in a session with no Haiku
machine/VM/cross-toolchain available (macOS sandbox, no `libbe`/Haiku
headers), so none of this has been compiled or tested against a real Haiku
SDK. It's written carefully against well-established Haiku API signatures,
but the Network Kit listener interface in particular (`BUrlProtocolListener`)
has shifted slightly across Haiku releases -- see the `NOTE` comment in
`src/HttpFetch.cpp` if it doesn't compile as-is. Build it on a real Haiku
box (or in a Haiku VM/container) and fix up whatever doesn't match your
SDK version before trusting it.

## What it does

- Fetches `https://news.coroke.net/` (the actual live page rreader-web
  generates) on a background thread.
- Parses out the Tech / Top News / Economy tabs and each source's card
  (favicon, source name, date, top story + thumbnail, sub-article list) --
  see `src/NewsParser.cpp`. It only understands the specific markup
  `rreader-web/generate.py` emits for the card view (`.group-card` etc),
  not arbitrary HTML, so if that markup changes this parser needs a
  matching update.
- Redraws it with the same visual design as the web version (colors,
  spacing, typography sizes -- see `src/Colors.h`, ported straight from
  `rreader-web/generate.py`'s CSS).
- Cards are a **fixed width** (`NewsMetrics::kCardWidth`, 360px) and the
  grid reflows into however many columns fit the window
  (`src/FlowLayoutView.cpp`) -- 2 columns in a narrow window, 3, 4, more in
  a wide one, recalculated live on resize. This is actually *more*
  flexible than the web version, which caps at 3 columns inside a
  1200px-max-width container.
- Every link (top story, sub-articles) opens in the system's default
  browser (`src/UrlOpener.cpp`, via `be_roster->Launch()`), never inside
  the app.
- Thumbnails and favicons load asynchronously and are decoded through the
  Translation Kit (`src/ImageLoader.cpp`), so a slow/missing image never
  blocks the rest of the UI.

## Design fidelity

Every color, spacing, and font-size constant in `src/Colors.h` is copied
directly from `rreader-web/generate.py`'s inline CSS (search that file for
the same value to cross-check if the web design changes). A few things
don't have a clean 1:1 native equivalent and were approximated:

- CSS `font-weight: 600` (title without a thumbnail) has no exact match in
  Haiku's `BFont` face flags (regular/bold/heavy only) -- it uses regular
  weight, `700` uses bold.
- Card hover shadow (`box-shadow` on `.group-card:hover`) is approximated
  with just a border-color change (`kCardBorderHover`), since `BView`
  doesn't have a built-in soft drop-shadow primitive.
- The web version's AdSense card slot, "핵심 뉴스 3줄" brief box, and
  card/list view toggle aren't ported -- this app is specifically about
  redrawing the news card grid, not the whole page chrome.

## Layout

```
src/
  main.cpp            entry point
  App.h / .cpp          BApplication
  MainWindow.h / .cpp     BWindow: header + scrollable card grid, owns the
                           fetch -> parse -> render pipeline
  HeaderView.h / .cpp      accent-colored header bar: logo + tabs
  FlowLayoutView.h / .cpp   reflowing fixed-width-card grid container
  CardView.h / .cpp         draws one source's card, handles clicks
  NewsFetcher.h / .cpp       async page fetch -> BMessage
  NewsParser.h / .cpp        HTML -> Category/SourceCard data
  NewsData.h                  plain data structs
  ImageLoader.h / .cpp         async image fetch + decode -> BBitmap
  HttpFetch.h / .cpp            shared blocking-GET helper (Network Kit)
  UrlOpener.h / .cpp             open a URL in the default browser
  Colors.h                        colors/metrics ported from generate.py
resources/
  App.rdef             app signature/version resource (see Makefile)
Makefile
```

## Build

On a Haiku machine (or Haiku VM/cross-toolchain):

```
cd rreader-haiku-native
make
./NewsCoroke
```

`make` compiles every `src/*.cpp`, links against `libbe`, `libnetwork`,
`libtranslation`, and (if `rc`/`xres` are available, i.e. you're actually
building on Haiku) embeds `resources/App.rdef` and runs `mimeset` so
Tracker/Deskbar show "news.coroke.net" as the app name. No app icon is
embedded (see `resources/App.rdef`'s comment) -- add one with
Icon-O-Matic if you want a custom icon.

## Known gaps / next steps for whoever builds this first

1. **Actually compile it** and fix any Network Kit / Interface Kit API
   drift against the exact Haiku version you're on (see the warning at
   the top of this file).
2. No automated tests -- verify by eye against https://news.coroke.net/
   for a couple of categories, including one with a thumbnail-less card
   and one with 6 sub-articles (longest card), to sanity-check
   `CardView::RecomputeHeight()`'s wrapping/height math.
3. No app icon.
4. No pull-to-refresh / manual refresh button yet -- currently only
   fetches once on startup. Would be a small addition to `MainWindow`
   (a toolbar button or a keyboard shortcut calling `StartFetch()` again).
