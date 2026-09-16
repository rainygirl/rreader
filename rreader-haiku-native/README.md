# rreader-haiku-native

A native Haiku OS app (BApplication/BWindow, Interface Kit + Translation
Kit + libcurl) that fetches the live [news.coroke.net](https://news.coroke.net)
page and redraws it natively -- same design as rreader-web, but as a real
Haiku GUI app instead of a browser tab.

Built and run on Haiku R1/beta6 (x86_gcc2 hybrid, built with the `x86`
secondary architecture's GCC 13).

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
- Keyboard: arrow keys move the focus between links by on-screen position
  (up/down within a column, left/right to the neighboring column), scrolling
  it into view; Enter/Space opens it. Up from the top link moves the focus
  to the tab bar, where Left/Right switch categories and Down returns.
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
- The web version's AdSense card slot and card/list view toggle aren't
  ported -- this app is specifically about redrawing the news content,
  not the whole page chrome.

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
  BriefView.h / .cpp         the "핵심 뉴스 3줄" box above the grid
  LinkSource.h                link interface used for keyboard navigation
  NewsFetcher.h / .cpp       async page fetch -> BMessage
  NewsParser.h / .cpp        HTML -> Category/SourceCard data
  NewsData.h                  plain data structs
  ImageLoader.h / .cpp         async image fetch + decode -> BBitmap
  HttpFetch.h / .cpp            shared blocking-GET helper (libcurl)
  UrlOpener.h / .cpp             open a URL in the default browser
  Colors.h                        colors/metrics ported from generate.py
resources/
  App.rdef             app signature/version resource (see Makefile)
third_party/curl/      vendored libcurl public headers
Makefile
```

## Build

On a Haiku machine (or Haiku VM/cross-toolchain):

```
cd rreader-haiku-native
make
make install   # -> /boot/home/config/non-packaged/apps/news.coroke.net
```

`make` compiles every `src/*.cpp` and links against `libbe`,
`libtranslation` and `libcurl`. On an x86_gcc2 hybrid install it builds
through `setarch x86` so the modern GCC is used. libcurl's headers are
vendored under `third_party/curl` because HaikuPorts' `curl_x86_devel`
package isn't always installable, and it links `libcurl.so.4` directly
since the unversioned symlink ships in that same devel package. Haiku's
own `BUrlRequest` API is not used: it lives in private headers and its
symbols aren't exported by any library a third-party app can link.

`rc`/`xres` embed `resources/App.rdef` so Tracker/Deskbar show
"news.coroke.net" as the app name. No app icon is embedded -- add one
with Icon-O-Matic if you want a custom icon.

## Known gaps

1. No automated tests -- verify by eye against https://news.coroke.net/
   for a couple of categories, including one with a thumbnail-less card
   and one with 6 sub-articles (longest card), to sanity-check
   `CardView::RecomputeHeight()`'s wrapping/height math.
2. No app icon.
3. No pull-to-refresh / manual refresh button yet -- currently only
   fetches once on startup. Would be a small addition to `MainWindow`
   (a toolbar button or a keyboard shortcut calling `StartFetch()` again).
