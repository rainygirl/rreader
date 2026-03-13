#!/usr/bin/env python3
"""
rreader-web: Static HTML news feed generator

Fetches Tech and Top News RSS feeds, translates titles to Korean via Gemini,
and generates static HTML pages (card view + list view).

Run hourly via cron:
  0 * * * * cd /path/to/rreader-web && python generate.py

Dependencies: feedparser, google-genai (same as rreader-python)
"""

import datetime
import feedparser
import html
import json
import os
import re
import sys
import time
from pathlib import Path

# ─── Configuration ────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
CACHE_FILE = BASE_DIR / "cache" / "translations.json"
OG_CACHE_FILE = BASE_DIR / "cache" / "og_images.json"
OUTPUT_DIR = BASE_DIR / "output"
FEEDS_FILE = BASE_DIR / "feeds.json"
GEMINI_CONFIG_FILE = Path.home() / ".rreader_gemini_config.json"

CATEGORIES = ["tech", "news"]
CARD_PER_SOURCE = 4   # articles per source in card view
LIST_MAX = 50         # total articles in list view
TIMEZONE = datetime.timezone(datetime.timedelta(hours=9))

# ─── API Key ──────────────────────────────────────────────────────────────────

def get_gemini_api_key():
    if GEMINI_CONFIG_FILE.exists():
        with open(GEMINI_CONFIG_FILE, encoding="utf-8") as f:
            key = json.load(f).get("GEMINI_API_KEY")
            if key:
                return key
    return os.environ.get("GEMINI_API_KEY")

# ─── Cache ────────────────────────────────────────────────────────────────────

def load_cache():
    if CACHE_FILE.exists():
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_cache(cache):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def load_og_cache():
    if OG_CACHE_FILE.exists():
        with open(OG_CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_og_cache(cache):
    OG_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OG_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

# ─── RSS Fetching ─────────────────────────────────────────────────────────────

def fetch_category(feeds_config):
    """Fetch RSS feeds and return entries sorted newest first."""
    entries = {}
    for source, url in feeds_config.items():
        print(f"  Fetching {source}...", end=" ", flush=True)
        try:
            d = feedparser.parse(url)
        except Exception as e:
            print(f"FAIL ({e})")
            continue
        print(f"OK ({len(d.entries)} items)")

        for feed in d.entries:
            try:
                parsed_time = (
                    getattr(feed, "published_parsed", None)
                    or getattr(feed, "updated_parsed", None)
                )
                if not parsed_time:
                    continue
                at = (
                    datetime.datetime(*parsed_time[:6])
                    .replace(tzinfo=datetime.timezone.utc)
                    .astimezone(TIMEZONE)
                )
            except Exception:
                continue

            pub_date = at.strftime(
                "%H:%M" if at.date() == datetime.date.today() else "%b %d, %H:%M"
            )
            ts = int(time.mktime(parsed_time))

            # Try to extract thumbnail from various feed formats
            thumbnail = None
            if hasattr(feed, "media_thumbnail") and feed.media_thumbnail:
                thumbnail = feed.media_thumbnail[0].get("url")
            elif hasattr(feed, "media_content") and feed.media_content:
                for m in feed.media_content:
                    if m.get("medium") == "image" or m.get("type", "").startswith("image/"):
                        thumbnail = m.get("url")
                        break
            elif hasattr(feed, "links"):
                for link in feed.links:
                    if link.get("type", "").startswith("image/"):
                        thumbnail = link.get("href")
                        break

            clean_title = re.sub(r'<[^>]+>', '', html.unescape(feed.title)).strip()
            if '퀴즈' in clean_title:
                continue

            entries[ts] = {
                "url": getattr(feed, "link", ""),
                "title": clean_title,
                "source": source,
                "pubDate": pub_date,
                "timestamp": ts,
                "thumbnail": thumbnail,
            }

    return sorted(entries.values(), key=lambda x: x["timestamp"], reverse=True)

# ─── OG Image ─────────────────────────────────────────────────────────────────

def _fetch_og_image(url):
    """Fetch og:image from a URL. Returns image URL string or None."""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            chunk = resp.read(32768).decode("utf-8", errors="ignore")
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', chunk)
        if not m:
            m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', chunk)
        return m.group(1).strip() if m else None
    except Exception:
        return None

def fetch_og_images(entries, og_cache):
    """
    For entries without a thumbnail, fetch og:image from the permalink.
    Only fetches URLs not already in og_cache. Uses threads for concurrency.
    og_cache: {url: image_url_or_empty_string}  (empty string = tried, found nothing)
    """
    import concurrent.futures

    need = [e for e in entries if not e.get("thumbnail") and e["url"] and e["url"] not in og_cache]
    if not need:
        # Apply cached values
        for e in entries:
            if not e.get("thumbnail") and e["url"] in og_cache and og_cache[e["url"]]:
                e["thumbnail"] = og_cache[e["url"]]
        return

    print(f"  Fetching og:image for {len(need)} entries...", end=" ", flush=True)

    def fetch_one(entry):
        img = _fetch_og_image(entry["url"])
        return entry["url"], img

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        for url, img in ex.map(fetch_one, need):
            og_cache[url] = img or ""

    # Apply all cached values
    for e in entries:
        if not e.get("thumbnail") and e["url"] in og_cache and og_cache[e["url"]]:
            e["thumbnail"] = og_cache[e["url"]]

    found = sum(1 for e in need if og_cache.get(e["url"]))
    print(f"OK ({found}/{len(need)} found)")

# ─── Translation ──────────────────────────────────────────────────────────────

def translate_entries(entries, api_key, url_cache):
    """
    Translate entry titles to Korean.
    url_cache is keyed by article URL (permalink) -> translated title.
    """
    # Collect URLs that need translation
    need_translation = []
    for entry in entries:
        if entry["url"] and entry["url"] not in url_cache:
            need_translation.append(entry)

    if need_translation and api_key:
        titles = [e["title"] for e in need_translation]
        print(f"  Translating {len(titles)} new titles...", end=" ", flush=True)
        translations = _translate_batch(titles, api_key)
        print("OK" if translations else "FAIL")
        for entry in need_translation:
            translated = translations.get(entry["title"])
            if translated:
                url_cache[entry["url"]] = translated

    # Apply translations
    for entry in entries:
        entry["title_ko"] = url_cache.get(entry["url"], entry["title"])

def _translate_batch(titles, api_key):
    """Call Gemini to translate a list of titles. Returns {original: translated}."""
    try:
        from google.genai import Client
        client = Client(api_key=api_key)
        payload = json.dumps({"titles": titles}, ensure_ascii=False)
        prompt = (
            "Translate the 'titles' in the following JSON to Korean. "
            "Each title may be in English, Japanese, or other languages — translate all of them to Korean. "
            "Return a JSON object where each original title is a key and its Korean translation is the value. "
            "Respond with ONLY the JSON object, no markdown.\n\n" + payload
        )
        response = client.models.generate_content(
            model="models/gemini-2.5-flash-lite",
            contents=prompt,
        )
        cleaned = response.text.strip()
        # Strip markdown code fences if present
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return json.loads(cleaned)
    except Exception as e:
        print(f"\n  [warn] Translation error: {e}", file=sys.stderr)
        return {}

# ─── HTML Generation ──────────────────────────────────────────────────────────

ACCENT = "#ec8c6f"

ADSENSE_UNIT = """<ins class="adsbygoogle"
     style="display:block"
     data-ad-client="ca-pub-2939993747600082"
     data-ad-slot="7719574153"
     data-ad-format="auto"
     data-full-width-responsive="true"></ins>"""

def esc(s):
    return html.escape(str(s) if s else "")

def generate_html(all_data, generated_at):
    """Generate a single index.html with both card and list views, toggled in-page."""
    cat_labels = {"tech": "Tech", "news": "Top News"}

    # Build tab-nav links
    tabs_html = ""
    for i, (cat_key, cat_title, _) in enumerate(all_data):
        active = ' class="active"' if i == 0 else ""
        tabs_html += f'<a href="#"{active} data-cat="{cat_key}">{cat_title}</a>'

    # Build sections for card and list views
    sections = ""
    for cat_key, cat_title, entries in all_data:
        # --- Card view section (grouped by source) ---
        # Group entries by source, preserving first-appearance order, max CARD_PER_SOURCE each
        groups = {}
        for e in entries:
            src = e["source"]
            if src not in groups:
                groups[src] = []
            if len(groups[src]) < CARD_PER_SOURCE:
                groups[src].append(e)

        cards = ""
        for card_idx, (src, src_entries) in enumerate(groups.items()):
            # Thumbnail from the first article that has one
            thumb = next((e["thumbnail"] for e in src_entries if e.get("thumbnail")), None)
            thumb_html = ""
            if thumb:
                thumb_html = f'<img class="group-thumb" src="{esc(thumb)}" alt="" loading="lazy" onerror="this.style.display=\'none\'">'
            # First article link opens the top story; rest shown as sub-items
            top = src_entries[0]
            sub_items = ""
            for e in src_entries[1:]:  # remaining articles after the top one
                sub_items += f"""
            <a class="group-sub" href="{esc(e['url'])}" target="_blank" rel="noopener">
              {esc(e['title_ko'])}
            </a>"""
            # Extract domain for favicon
            try:
                from urllib.parse import urlparse
                domain = urlparse(top['url']).netloc
            except Exception:
                domain = ""
            favicon_html = f'<img class="group-favicon" src="https://www.google.com/s2/favicons?domain={domain}&sz=32" alt="" onerror="this.style.display=\'none\'">' if domain else ""
            if card_idx == 5:
                cards += f'\n        <div class="ad-card">{ADSENSE_UNIT}</div>'
            cards += f"""
        <div class="group-card">
          <div class="group-header">
            {favicon_html}
            <span class="group-source">{esc(src)}</span>
            <span class="group-date">{esc(top['pubDate'])}</span>
          </div>
          <a class="group-top" href="{esc(top['url'])}" target="_blank" rel="noopener">
            <div class="group-top-inner">
              {thumb_html}
              <span class="group-top-title{'  has-thumb' if thumb else ''}">{esc(top['title_ko'])}</span>
            </div>
          </a>{sub_items}
        </div>"""
        sections += f"""
    <section data-cat="{cat_key}" data-view="card" class="pane" style="display:none">
      <div class="cards">{cards}
      </div>
    </section>"""

        # --- List view section (time-sorted, capped at LIST_MAX) ---
        rows = ""
        for i, e in enumerate(entries[:LIST_MAX], 1):
            try:
                from urllib.parse import urlparse
                ldomain = urlparse(e['url']).netloc
            except Exception:
                ldomain = ""
            lfavicon = f'<img class="list-favicon" src="https://www.google.com/s2/favicons?domain={ldomain}&sz=32" alt="" onerror="this.style.display=\'none\'">' if ldomain else ""
            if i in (6, 12):
                rows += '\n        <div class="ad-list"><ins class="adsbygoogle" style="display:block" data-ad-format="fluid" data-ad-layout-key="-fb+5w+4e-db+86" data-ad-client="ca-pub-2939993747600082" data-ad-slot="1893036982"></ins></div>'
            rows += f"""
        <a class="list-row" href="{esc(e['url'])}" target="_blank" rel="noopener">
          <span class="list-num">{i}</span>
          <span class="list-source">{lfavicon}{esc(e['source'])}</span>
          <span class="list-date">{esc(e['pubDate'])}</span>
          <span class="list-title">{esc(e['title_ko'])}</span>
        </a>"""
        sections += f"""
    <section data-cat="{cat_key}" data-view="list" class="pane" style="display:none">
      <div class="list">{rows}
      </div>
    </section>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>news.coroke.net</title>
  <link rel="icon" type="image/svg+xml" href="favicon.svg">
  <meta property="og:title" content="news.coroke.net" />
  <meta property="og:site_name" content="news.coroke.net" />
  <meta property="og:description" content="전세계 IT, AI, 기술, 국제뉴스를 한국어로" />
  <meta property="og:type" content="website" />
  <meta property="og:image" content="og-image.jpg" />
  <!-- news.coroke.net용 코드이니 재활용시 삭제하세요 -->
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-V5TYZ73NS2"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', 'G-V5TYZ73NS2');
  </script>
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2939993747600082" crossorigin="anonymous"></script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    a {{ letter-spacing: -0.5px; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif;
      background: #f4f5f7;
      color: #222;
      min-height: 100vh;
    }}

    /* ── Header ── */
    header {{
      background: {ACCENT};
      position: sticky;
      top: 0;
      z-index: 100;
      box-shadow: 0 2px 8px rgba(0,0,0,0.12);
    }}
    .header-inner {{
      max-width: 1200px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 0 16px;
      height: 54px;
    }}
    .logo {{
      color: #fff;
      font-size: 18px;
      font-weight: 800;
      letter-spacing: -0.5px;
      flex-shrink: 0;
    }}
    .tab-nav {{
      display: flex;
      gap: 2px;
      flex: 1;
    }}
    .tab-nav a {{
      color: rgba(255,255,255,0.75);
      text-decoration: none;
      font-size: 14px;
      font-weight: 600;
      padding: 6px 14px;
      border-radius: 4px;
      transition: color 0.15s, background 0.15s;
    }}
    .tab-nav a:hover {{ color: #fff; background: rgba(255,255,255,0.15); }}
    .tab-nav a.active {{
      color: #fff;
      border-bottom: 2px solid rgba(255,255,255,0.9);
      border-radius: 0;
    }}

    .header-credit {{
      font-size: 12px;
      color: rgba(255,255,255,0.6);
      flex-shrink: 0;
    }}
    .header-credit a {{
      color: rgba(255,255,255,0.6);
      text-decoration: none;
    }}
    .header-credit a:hover {{
      color: rgba(255,255,255,0.9);
    }}
    .mobile-credit {{
      display: none;
      text-align: right;
      font-size: 12px;
      color: #aaa;
      padding: 0 16px;
      margin-top: 6px;
      background: #f4f5f7;
    }}
    .mobile-credit a {{
      color: #aaa;
      text-decoration: none;
    }}
    .mobile-credit a:hover {{ color: #666; }}
    @media (max-width: 600px) {{
      .header-credit {{ display: none; }}
      .mobile-credit {{ display: block; }}
      #logo {{ display: none; }}
    }}

    /* ── Pill toggle ── */
    .view-pill {{
      position: relative;
      display: flex;
      align-items: center;
      background: transparent;
      border-radius: 999px;
      padding: 3px;
      flex-shrink: 0;
      border: 1px solid #fff;
    }}
    /* sliding white background */
    .view-pill::before {{
      content: '';
      position: absolute;
      top: 3px;
      left: 3px;
      height: calc(100% - 6px);
      border-radius: 999px;
      background: #fff;
      transition: transform 0.22s cubic-bezier(0.4, 0, 0.2, 1),
                  width 0.22s cubic-bezier(0.4, 0, 0.2, 1);
      z-index: 0;
    }}
    .view-pill[data-active="card"]::before {{
      width: var(--pill-card-w, 50%);
      transform: translateX(0);
    }}
    .view-pill[data-active="list"]::before {{
      width: var(--pill-list-w, 50%);
      transform: translateX(var(--pill-card-w, 50%));
    }}
    .view-pill button {{
      position: relative;
      z-index: 1;
      border: none;
      background: transparent;
      font-size: 13px;
      font-weight: 600;
      padding: 5px 16px;
      border-radius: 999px;
      cursor: pointer;
      font-family: inherit;
      line-height: 1;
      white-space: nowrap;
      transition: color 0.22s;
      color: rgba(255,255,255,0.85);
    }}
    .view-pill button.active {{
      color: {ACCENT};
    }}

    /* ── Main layout ── */
    main {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 12px 0;
    }}

    /* ── Card view (publisher groups) ── */
    .cards {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 20px 12px;
      padding: 12px 16px 24px;
      align-items: start;
    }}
    @media (max-width: 900px) {{ .cards {{ grid-template-columns: repeat(2, 1fr); }} }}
    @media (max-width: 600px) {{ .cards {{ grid-template-columns: 1fr; gap: 14px 8px; padding: 8px 8px 16px; }} }}
    .ad-card {{ overflow: hidden; min-width: 0; }}
    .ad-card ins {{ max-width: 100% !important; }}
    .ad-list {{ padding: 8px 16px; }}

    .group-card {{
      background: #fff;
      border: 1px solid #e8e8e8;
      border-radius: 10px;
      overflow: hidden;
      padding-bottom: 10px;
      transition: box-shadow 0.15s, border-color 0.15s;
      min-width: 0;
    }}
    .group-card:hover {{ box-shadow: 0 3px 14px rgba(0,0,0,0.09); border-color: #d5d5d5; }}

    .group-header {{
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 12px 14px 10px;
    }}
    .group-favicon {{
      width: 16px;
      height: 16px;
      border-radius: 3px;
      flex-shrink: 0;
    }}
    .group-source {{
      font-size: 14px;
      font-weight: 700;
      color: #1a1a1a;
    }}
    .group-date {{
      font-size: 11px;
      color: #bbb;
    }}
    .group-top {{
      display: block;
      text-decoration: none;
      color: inherit;
      padding: 14px 0 14px 12px;
      transition: background 0.1s;
    }}
    .group-top:hover {{ background: #fdf6f4; }}
    .group-top-inner {{
      display: flex;
      gap: 10px;
      align-items: center;
    }}
    .group-top-title {{
      flex: 1;
      min-width: 0;
      font-size: 14px;
      font-weight: 600;
      line-height: 1.55;
      color: #1a1a1a;
      padding-right: 14px;
      word-break: break-word;
      letter-spacing: -0.5px;
    }}
    .group-top-title.has-thumb {{
      font-size: 16px;
      font-weight: 700;
    }}
    .group-thumb {{
      width: 68px;
      height: 68px;
      object-fit: cover;
      border-radius: 6px;
      flex-shrink: 0;
    }}
    .group-sub {{
      display: block;
      text-decoration: none;
      font-size: 14px;
      color: #444;
      line-height: 1.45;
      padding: 7px 14px;
      letter-spacing: -0.5px;
      white-space: nowrap;
      text-overflow: ellipsis;
      overflow: hidden;
      border-top: 1px solid #f2f2f2;
      transition: background 0.1s;
      word-break: break-word;
    }}
    .group-sub:hover {{ background: #fdf6f4; color: #1a1a1a; }}
    .group-sub-date {{
      font-size: 11px;
      color: #bbb;
      margin-right: 6px;
      flex-shrink: 0;
    }}

    /* ── List view ── */
    .list {{ display: flex; flex-direction: column; }}
    .list-row {{
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 16px;
      border-bottom: 1px solid #efefef;
      text-decoration: none;
      color: inherit;
      transition: background 0.1s;
    }}
    .list-row:hover {{ background: #f7f5f4; }}
    .list-row:hover .list-title {{ color: {ACCENT}; }}
    .list-num {{
      font-size: 12px;
      color: #ccc;
      min-width: 22px;
      text-align: right;
      flex-shrink: 0;
    }}
    .list-favicon {{
      width: 16px;
      height: 16px;
      border-radius: 2px;
      flex-shrink: 0;
      margin-right: 6px;
    }}
    .list-source {{
      display: flex;
      align-items: center;
      font-size: 12px;
      color: {ACCENT};
      min-width: 110px;
      flex-shrink: 0;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      font-weight: 600;
    }}
    .list-date {{
      font-size: 12px;
      color: #bbb;
      min-width: 72px;
      flex-shrink: 0;
    }}
    .list-title {{
      font-size: 16px;
      color: #1a1a1a;
      line-height: 1.5;
      letter-spacing: -0.5px;
    }}
    @media (max-width: 600px) {{
      .list-row {{ flex-wrap: wrap; gap: 4px; padding: 10px 12px; }}
      .list-source {{ min-width: 70px; }}
      .list-date {{ min-width: 60px; }}
      .list-title {{ width: 100%; margin-top: 2px; padding-left: 32px; }}
    }}

    footer {{
      text-align: center;
      padding: 24px;
      font-size: 12px;
      color: #888;
      line-height: 2em;
    }}
    footer a {{
      color: #666;
    }}
  </style>
</head>
<body>
  <header>
    <div class="header-inner">
      <span class="logo" id="logo" style="cursor:pointer">news.coroke.net</span>
      <nav class="tab-nav">{tabs_html}</nav>
      <span class="header-credit">개발: <a href="https://rainygirl.com" target="_blank" rel="noopener">rainygirl.com w/Claude</a></span>
      <div class="view-pill">
        <button data-view="card" class="active">카드</button>
        <button data-view="list">목록</button>
      </div>
    </div>
  </header>
  <div class="mobile-credit">개발: <a href="https://rainygirl.com" target="_blank" rel="noopener">rainygirl.com w/Claude</a></div>
  <main>{sections}
  </main>
  <footer>데이터 소스: 각 매체 공개 RSS / 한국어 번역: Gemini<br><br><a href="https://python.org/" target="_blank" rel="noopener">Powered by Python</a><br>소스코드: <a href="https://github.com/rainygirl/rreader" target="_blank" rel="noopener">github.com/rainygirl/rreader</a><br><br>개발: <a href="https://rainygirl.com" target="_blank" rel="noopener">rainygirl.com w/Claude</a></footer>
  <script>
(function() {{
  var currentCat = '{all_data[0][0]}';
  var currentView = 'card';

  function showPane() {{
    document.querySelectorAll('.pane').forEach(function(el) {{
      var visible = el.dataset.cat === currentCat && el.dataset.view === currentView;
      el.style.display = visible ? '' : 'none';
      if (visible) {{
        var pane = el;
        requestAnimationFrame(function() {{
          pane.querySelectorAll('ins.adsbygoogle').forEach(function(ins) {{
            if (!ins.dataset.adsbygoogleStatus) {{
              (window.adsbygoogle = window.adsbygoogle || []).push({{}});
            }}
          }});
        }});
      }}
    }});
  }}

  // Logo → card view of first tab
  document.getElementById('logo').addEventListener('click', function() {{
    currentCat = '{all_data[0][0]}';
    currentView = 'card';
    document.querySelectorAll('.tab-nav a').forEach(function(x) {{ x.classList.remove('active'); }});
    document.querySelector('.tab-nav a[data-cat="{all_data[0][0]}"]').classList.add('active');
    updatePill();
    showPane();
    window.scrollTo(0, 0);
  }});

  // Tab nav
  document.querySelectorAll('.tab-nav a').forEach(function(a) {{
    a.addEventListener('click', function(e) {{
      e.preventDefault();
      currentCat = this.dataset.cat;
      document.querySelectorAll('.tab-nav a').forEach(function(x) {{ x.classList.remove('active'); }});
      this.classList.add('active');
      showPane();
      window.scrollTo(0, 0);
    }});
  }});

  // View pill — sliding animation
  var pill = document.querySelector('.view-pill');
  var pillBtns = pill.querySelectorAll('button');
  function updatePill() {{
    // Measure each button's width and store as CSS vars
    var cardBtn = pill.querySelector('[data-view="card"]');
    var listBtn = pill.querySelector('[data-view="list"]');
    pill.style.setProperty('--pill-card-w', cardBtn.offsetWidth + 'px');
    pill.style.setProperty('--pill-list-w', listBtn.offsetWidth + 'px');
    pill.dataset.active = currentView;
    pillBtns.forEach(function(b) {{
      b.classList.toggle('active', b.dataset.view === currentView);
    }});
  }}
  pillBtns.forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      currentView = this.dataset.view;
      updatePill();
      showPane();
      window.scrollTo(0, 0);
    }});
  }});
  // Init pill on load and resize
  updatePill();
  window.addEventListener('resize', updatePill);

  showPane();
}})();
  </script>
</body>
</html>"""

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load feeds config
    if not FEEDS_FILE.exists():
        sys.exit(f"feeds.json not found: {FEEDS_FILE}")
    with open(FEEDS_FILE, encoding="utf-8") as f:
        feeds_config = json.load(f)

    api_key = get_gemini_api_key()
    if not api_key:
        print("[warn] No Gemini API key found. Titles will not be translated.")
        print("       Save key to ~/.rreader_gemini_config.json or set GEMINI_API_KEY env var.")

    url_cache = load_cache()
    og_cache = load_og_cache()
    all_data = []

    for cat_key in CATEGORIES:
        cat_config = feeds_config.get(cat_key)
        if not cat_config:
            print(f"[warn] Category '{cat_key}' not found in feeds.json, skipping.")
            continue
        cat_title = cat_config["title"]
        print(f"\n[{cat_title}]")
        entries = fetch_category(cat_config["feeds"])
        print(f"  → {len(entries)} entries fetched")
        translate_entries(entries, api_key, url_cache)
        fetch_og_images(entries, og_cache)
        all_data.append((cat_key, cat_title, entries))

    save_cache(url_cache)
    save_og_cache(og_cache)
    print(f"\nCache saved ({len(url_cache)} translations, {len(og_cache)} og:images)")

    now = datetime.datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M KST")
    index_html = generate_html(all_data, now)
    (OUTPUT_DIR / "index.html").write_text(index_html, encoding="utf-8")

    print(f"Generated: output/index.html")
    print(f"Done at {now}")

if __name__ == "__main__":
    main()
