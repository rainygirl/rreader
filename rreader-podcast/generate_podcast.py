#!/usr/bin/env python3
"""
rreader-podcast: daily news-briefing podcast generator

Reads the "headline brief" (3 key stories per tab) that rreader-web's
generate.py already produces and caches at ../rreader-web/cache/briefs.json,
turns it into a script (just the headline sentences, Tech -> Top News ->
Economy, no filler), synthesizes it at 1.2x speed with Microsoft Edge's
free neural TTS (edge-tts, no API key needed), mixes it over an original
synth-beat loop (assets/background.wav, see make_music.py) the way a BBC
Newsbeat-style bulletin sits over a beat, and updates a podcast RSS feed
(feed.xml) that Apple Podcasts and Spotify can both subscribe to. Episodes
older than RETENTION_DAYS are pruned automatically.

Needs ffmpeg on PATH (for pydub's mp3 decode/encode) -- `brew install
ffmpeg` on macOS, `apt install ffmpeg` on the server.

Run once a day, after rreader-web/run.sh has refreshed briefs.json:
  uv run python generate_podcast.py

See DISTRIBUTION-GUIDE.md for how to host feed.xml/episodes/ publicly
and submit the feed to Apple Podcasts and Spotify.
"""

import asyncio
import datetime
import json
import os
import sys
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

import edge_tts
import numpy as np
from mutagen.mp3 import MP3
from pydub import AudioSegment

# ─── Configuration ────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
BRIEFS_FILE = BASE_DIR.parent / "rreader-web" / "cache" / "briefs.json"
OUTPUT_DIR = BASE_DIR / "output"
EPISODES_DIR = OUTPUT_DIR / "episodes"
MANIFEST_FILE = OUTPUT_DIR / "episodes.json"
FEED_FILE = OUTPUT_DIR / "feed.xml"
COVER_SRC = BASE_DIR / "assets" / "cover.jpg"
COVER_OUT = OUTPUT_DIR / "cover.jpg"
TIMEZONE = datetime.timezone(datetime.timedelta(hours=9))

# Change this if you host the feed somewhere else (see DISTRIBUTION-GUIDE.md).
BASE_URL = "https://news.coroke.net/podcast"

# Order requested: Tech(기술) -> Top News(국제) -> Economy(경제)
CATEGORY_ORDER = ["tech", "news", "economy"]

# ko-KR-SunHiNeural: female voice, reads well as a formal news announcer.
# Other free options: ko-KR-InJoonNeural (male), ko-KR-HyunsuMultilingualNeural (male).
VOICE = "ko-KR-SunHiNeural"
RATE = "+10%"  # 1.1x speaking rate (edge-tts's own prosody control, not a post-speedup)

# Background music: a short original synth-beat loop (see make_music.py, no
# licensing to worry about since we generated it ourselves) tiled under the
# narration, BBC-Newsbeat-style -- upbeat under a couple of seconds of
# lead-in/tail, ducked quieter while the narration is actually playing.
MUSIC_FILE = BASE_DIR / "assets" / "background.wav"
MUSIC_LEAD_IN_SEC = 3.0
MUSIC_TAIL_SEC = 3.5
MUSIC_BASE_DB = -6  # music's own level (music-only sections)
MUSIC_DUCK_DB = -9  # additional attenuation under the narration (was -16: too quiet to hear at all)
MUSIC_DUCK_RAMP_SEC = 0.4

PODCAST_TITLE = "news.coroke.net 뉴스 브리핑"
PODCAST_AUTHOR = "news.coroke.net"
PODCAST_OWNER_EMAIL = "rainygirl@gmail.com"
PODCAST_DESCRIPTION = "기술, 국제, 경제 세 분야의 핵심 뉴스를 매일 한국어로 요약해 전해드리는 짧은 뉴스 브리핑입니다."
CLOSING_LINE = "이상, 뉴스코로케 제공입니다."
PODCAST_LANGUAGE = "ko-kr"
MAX_FEED_ITEMS = 60  # extra safety cap on top of RETENTION_DAYS
RETENTION_DAYS = 14  # delete episodes (mp3 + feed entry) older than this

WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


# ─── Script building ──────────────────────────────────────────────────────────


def build_script(briefs, today):
    """
    Build the script text from today's cached briefs.

    No filler: no opening greeting/date announcement, no "먼저 기술 분야
    소식입니다" category transitions, no "첫 번째/두 번째" ordinal markers.
    Just every headline sentence read back to back in CATEGORY_ORDER
    (Tech -> Top News -> Economy), then one short sign-off line.
    """
    lines = []
    for cat_key in CATEGORY_ORDER:
        items = (briefs.get(cat_key) or {}).get("items") or []
        for item in items:
            summary = item.get("summary", "").strip()
            if summary:
                lines.append(summary)

    if not lines:
        return None

    lines.append(CLOSING_LINE)
    return "\n".join(lines)


# ─── TTS ──────────────────────────────────────────────────────────────────────


async def synthesize(text, out_path):
    communicate = edge_tts.Communicate(text, voice=VOICE, rate=RATE)
    await communicate.save(str(out_path))


# ─── Music mixing ─────────────────────────────────────────────────────────────


def _db_to_amp(db):
    return 10 ** (db / 20)


def _segment_to_array(seg):
    """pydub AudioSegment -> float64 numpy array, shape (n, channels), range [-1, 1]."""
    arr = np.array(seg.get_array_of_samples(), dtype=np.float64)
    arr = arr.reshape(-1, seg.channels)
    return arr / (2 ** (8 * seg.sample_width - 1))


def mix_with_music(voice_path, out_path):
    """
    Lay the narration over the tiled background loop: a couple of seconds of
    music alone at the start and end, ducked quieter under the narration
    itself so every word stays clearly intelligible.
    """
    sr = 44100
    voice = AudioSegment.from_file(voice_path).set_frame_rate(sr).set_channels(2)
    music = AudioSegment.from_wav(MUSIC_FILE).set_frame_rate(sr).set_channels(2)

    voice_arr = _segment_to_array(voice)
    music_loop = _segment_to_array(music)

    lead_in = int(MUSIC_LEAD_IN_SEC * sr)
    tail = int(MUSIC_TAIL_SEC * sr)
    total_len = lead_in + len(voice_arr) + tail

    reps = int(np.ceil(total_len / len(music_loop)))
    bed = np.tile(music_loop, (reps, 1))[:total_len] * _db_to_amp(MUSIC_BASE_DB)

    # Duck under the narration, with a short linear ramp in/out so the
    # volume change isn't an audible jump.
    ramp = int(MUSIC_DUCK_RAMP_SEC * sr)
    duck_gain = _db_to_amp(MUSIC_DUCK_DB)
    env = np.ones(total_len)
    voice_end = lead_in + len(voice_arr)
    env[lead_in:voice_end] = duck_gain
    r0 = max(0, lead_in - ramp)
    env[r0:lead_in] = np.linspace(1.0, duck_gain, lead_in - r0)
    r1 = min(total_len, voice_end + ramp)
    env[voice_end:r1] = np.linspace(duck_gain, 1.0, r1 - voice_end)
    bed *= env[:, None]

    # Fade the whole episode in/out.
    fade_in_n = int(0.8 * sr)
    fade_out_n = int(1.5 * sr)
    bed[:fade_in_n] *= np.linspace(0, 1, fade_in_n)[:, None]
    bed[-fade_out_n:] *= np.linspace(1, 0, fade_out_n)[:, None]

    mixed = bed.copy()
    mixed[lead_in:voice_end] += voice_arr

    peak = np.max(np.abs(mixed))
    if peak > 0.98:
        mixed = mixed / peak * 0.98

    pcm = np.clip(mixed * 32767, -32768, 32767).astype(np.int16)
    out_audio = AudioSegment(pcm.tobytes(), frame_rate=sr, sample_width=2, channels=2)
    # Export to a temp file then atomically rename into place: nginx's
    # open_file_cache can otherwise serve a half-written or previous-length
    # response if a listener requests the episode while it's being
    # overwritten in place (same class of bug as rreader-web's index.html).
    out_path = Path(out_path)
    tmp_path = out_path.with_suffix(".mp3.tmp")
    out_audio.export(str(tmp_path), format="mp3", bitrate="96k")
    os.replace(tmp_path, out_path)


# ─── RSS feed ─────────────────────────────────────────────────────────────────


def load_manifest():
    if MANIFEST_FILE.exists():
        with open(MANIFEST_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def atomic_write_text(path, text):
    """Write then os.replace, so a concurrent nginx request never sees a
    half-written or stale-length file (nginx's open_file_cache in particular
    can otherwise keep serving an old Content-Length for a moment)."""
    path = Path(path)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, path)


def save_manifest(manifest):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(MANIFEST_FILE, json.dumps(manifest, ensure_ascii=False, indent=2))


def prune_old_episodes(manifest, today):
    """Delete mp3 files (and their manifest/feed entries) older than RETENTION_DAYS."""
    cutoff = today - datetime.timedelta(days=RETENTION_DAYS)
    kept, dropped = [], []
    for ep in manifest:
        ep_date = datetime.date.fromisoformat(ep["date"])
        if ep_date < cutoff:
            dropped.append(ep)
        else:
            kept.append(ep)
    for ep in dropped:
        mp3_path = EPISODES_DIR / ep["filename"]
        try:
            mp3_path.unlink(missing_ok=True)
        except OSError as e:
            print(f"  [warn] could not delete {mp3_path}: {e}")
    if dropped:
        print(f"Pruned {len(dropped)} episode(s) older than {RETENTION_DAYS} days: "
              + ", ".join(ep["date"] for ep in dropped))
    return kept


def build_feed_xml(manifest):
    items_xml = ""
    for ep in manifest[:MAX_FEED_ITEMS]:
        pub_dt = datetime.datetime.fromisoformat(ep["published_at"])
        items_xml += f"""
    <item>
      <title>{escape(ep['title'])}</title>
      <description>{escape(ep['description'])}</description>
      <pubDate>{format_datetime(pub_dt)}</pubDate>
      <enclosure url="{escape(ep['url'])}" length="{ep['bytes']}" type="audio/mpeg"/>
      <guid isPermaLink="false">news-coroke-net-podcast-{escape(ep['date'])}</guid>
      <itunes:duration>{ep['duration_hms']}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
    </item>"""

    now = datetime.datetime.now(TIMEZONE)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escape(PODCAST_TITLE)}</title>
    <link>{escape(BASE_URL)}/</link>
    <atom:link href="{escape(BASE_URL)}/feed.xml" rel="self" type="application/rss+xml"/>
    <language>{PODCAST_LANGUAGE}</language>
    <lastBuildDate>{format_datetime(now)}</lastBuildDate>
    <description>{escape(PODCAST_DESCRIPTION)}</description>
    <itunes:author>{escape(PODCAST_AUTHOR)}</itunes:author>
    <itunes:summary>{escape(PODCAST_DESCRIPTION)}</itunes:summary>
    <itunes:owner>
      <itunes:name>{escape(PODCAST_AUTHOR)}</itunes:name>
      <itunes:email>{escape(PODCAST_OWNER_EMAIL)}</itunes:email>
    </itunes:owner>
    <itunes:image href="{escape(BASE_URL)}/cover.jpg"/>
    <image>
      <url>{escape(BASE_URL)}/cover.jpg</url>
      <title>{escape(PODCAST_TITLE)}</title>
      <link>{escape(BASE_URL)}/</link>
    </image>
    <itunes:category text="News"/>
    <itunes:explicit>false</itunes:explicit>
    <itunes:type>episodic</itunes:type>
{items_xml}
  </channel>
</rss>
"""


# ─── Main ─────────────────────────────────────────────────────────────────────


def main():
    force = "--force" in sys.argv

    if not BRIEFS_FILE.exists():
        sys.exit(
            f"[error] {BRIEFS_FILE} not found. Run rreader-web/run.sh first "
            "so today's headline briefs are cached."
        )
    with open(BRIEFS_FILE, encoding="utf-8") as f:
        briefs = json.load(f)

    today = datetime.datetime.now(TIMEZONE).date()
    date_str = today.isoformat()

    manifest = load_manifest()
    if any(ep["date"] == date_str for ep in manifest) and not force:
        print(f"[skip] Episode for {date_str} already exists. Use --force to regenerate.")
        return

    script = build_script(briefs, today)
    if not script:
        sys.exit("[error] No brief items found for any category; nothing to synthesize.")

    print(f"Script ({len(script)} chars):\n{script}\n")

    EPISODES_DIR.mkdir(parents=True, exist_ok=True)
    mp3_path = EPISODES_DIR / f"{date_str}.mp3"
    voice_tmp_path = EPISODES_DIR / f".voice-{date_str}.mp3"
    print(f"Synthesizing with {VOICE}...", end=" ", flush=True)
    asyncio.run(synthesize(script, voice_tmp_path))
    print("OK")

    print("Mixing with background music...", end=" ", flush=True)
    mix_with_music(voice_tmp_path, mp3_path)
    voice_tmp_path.unlink(missing_ok=True)
    print("OK")

    audio = MP3(mp3_path)
    duration_seconds = int(audio.info.length)
    h, rem = divmod(duration_seconds, 3600)
    m, s = divmod(rem, 60)
    duration_hms = f"{h:02d}:{m:02d}:{s:02d}"
    file_bytes = mp3_path.stat().st_size
    print(f"  {mp3_path.name}: {file_bytes / 1024:.0f} KB, {duration_hms}")

    # Publish the cover image alongside the episodes (served from output/).
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if COVER_SRC.exists():
        cover_tmp = COVER_OUT.with_suffix(".jpg.tmp")
        cover_tmp.write_bytes(COVER_SRC.read_bytes())
        os.replace(cover_tmp, COVER_OUT)

    weekday = WEEKDAY_KO[today.weekday()]
    episode = {
        "date": date_str,
        "title": f"{today.year}년 {today.month}월 {today.day}일 ({weekday}) 뉴스 브리핑",
        "description": PODCAST_DESCRIPTION,
        "filename": mp3_path.name,
        "url": f"{BASE_URL}/episodes/{mp3_path.name}",
        "bytes": file_bytes,
        "duration_seconds": duration_seconds,
        "duration_hms": duration_hms,
        "published_at": datetime.datetime.now(TIMEZONE).isoformat(),
    }
    # Replace any existing entry for today (in case of --force), newest first.
    manifest = [ep for ep in manifest if ep["date"] != date_str]
    manifest.insert(0, episode)
    manifest.sort(key=lambda e: e["date"], reverse=True)
    manifest = prune_old_episodes(manifest, today)
    save_manifest(manifest)

    atomic_write_text(FEED_FILE, build_feed_xml(manifest))
    print(f"Generated: {FEED_FILE}")
    print(f"Done at {datetime.datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M KST')}")


if __name__ == "__main__":
    main()
