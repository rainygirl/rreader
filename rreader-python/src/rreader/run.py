# -*- coding:utf-8 -*-

import curses
import json
import os
import re
import sys
import signal
import time
import unicodedata
import webbrowser
import threading

from wcwidth import wcwidth as _wcwidth
from asciimatics.screen import Screen
from asciimatics.effects import Print
from asciimatics.scene import Scene
from asciimatics.renderers import ColourImageFile, SpeechBubble
from asciimatics.event import KeyboardEvent

try:
    from .common import p, FEEDS_FILE_NAME
    from .get_rss import do as get_feeds_from_rss
except ImportError:
    from rreader.common import p, FEEDS_FILE_NAME
    from rreader.get_rss import do as get_feeds_from_rss

try:
    from .gemini import summarize_with_gemini, translate_titles_batch
    GEMINI_AVAILABLE = True
except ImportError:
    try:
        from rreader.gemini import summarize_with_gemini, translate_titles_batch
        GEMINI_AVAILABLE = True
    except ImportError:
        GEMINI_AVAILABLE = False


KEY = {
    "up": -204,
    "down": -206,
    "shiftUp": 337,
    "shiftDown": 336,
    "enter": 10,
    "space": 32,
    "tab": -301,
    "shiftTab": -302,
    "backspace": -300,
    "esc": -1,
    ":": ord(":"),
    "h": [ord("h"), ord("H")],
    "?": ord("?"),
    "r": [ord("r"), ord("R")],
    "s": [ord("s"), ord("S")],
    "w": [ord("w"), ord("W")],
    "j": [ord("j"), ord("J")],
    "k": [ord("k"), ord("K")],
    "o": [ord("o"), ord("O")],
    "q": [ord("q"), ord("Q")],
}

KEYLIST = {
    "arrow": [KEY["up"], KEY["down"], KEY["shiftUp"], KEY["shiftDown"], KEY["esc"]]
    + KEY["s"]
    + KEY["w"]
    + KEY["j"]
    + KEY["k"],
    "number": range(48, 58),
}

CONFIG = {
    "color": 16,
    "mode": "list",
    "rowlimit": -1,
    "marqueeFields": ["title", "text"],
    "marqueeSpeed": 20,
    "marqueeSpeedReturn": 400,
    "marqueeDelay": 40,
    "marqueeDelayReturn": 120,
    "refresh": 120,  # RSS pooling interval (seconds)
    "categories": (),
}

if "256" in os.environ.get("TERM", ""):
    CONFIG["color"] = 256

COLOR = {
    "default": 7,
    "number": 7,
    "numberselected": 15,
    "source": 11,
    "bluesource": 3,
    "time": 8,
    "selected": 7,
    "alertfg": 15,
    "alertbg": 4,
    "categoryfg": 3,
    "categorybg": 0,
    "categoryfgS": 0,
    "categorybgS": 3,
}


if CONFIG["color"] == 256:
    COLOR = {
        "default": 7,
        "number": 8,
        "numberselected": 15,
        "source": 2,
        "bluesource": 105,
        "RTheaderS": 6,
        "time": 8,
        "selected": 15,
        "alertfg": 15,
        "alertbg": 12,
        "categoryfg": 223,
        "categorybg": 235,
        "categoryfgS": 235,
        "categorybgS": 223,
    }

# FIELDS syntax : (column, field, color key, space fill)

FIELDS = {
    "default": [
        (1, "sourceName", "source", True),
        (20, "title"),
        (-1, "pubDate", "time"),
    ]
}

data, CURRENT, NEEDS_REDRAW, TRANSLATING_IN_PROGRESS, LOADING_STATUS = {}, {}, False, False, None

os.environ.setdefault("ESCDELAY", "10")


def get_feed(category="news"):
    try:
        with open(p["path_data"] + "rss_%s.json" % category, "r") as c:
            d = json.load(c)
    except:
        d = get_feeds_from_rss(category)
        if not d:
            sys.exit("oops")
    return d

    return None

GEMINI_CONFIG_FILE = os.path.join(os.path.expanduser('~'), ".rreader_gemini_config.json")

TRANSLATION_CACHE_FILE = os.path.join(os.path.expanduser('~'), ".rreader_translation_cache.json")

def load_translation_cache():
    if os.path.exists(TRANSLATION_CACHE_FILE):
        with open(TRANSLATION_CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_translation_cache(cache):
    with open(TRANSLATION_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=4)

def get_gemini_api_key():
    api_key = None
    if os.path.exists(GEMINI_CONFIG_FILE):
        with open(GEMINI_CONFIG_FILE, "r") as f:
            config = json.load(f)
            api_key = config.get("GEMINI_API_KEY")

    if not api_key:
        print("Gemini API Key not found.")
        print("Please visit https://makersuite.google.com/app/apikey to get an API key.")
        print("Opening browser now...")
        time.sleep(2)
        webbrowser.open("https://makersuite.google.com/app/apikey")

        api_key = input("Paste your Gemini API key here and press Enter: ").strip()
        if api_key:
            with open(GEMINI_CONFIG_FILE, "w") as f:
                json.dump({"GEMINI_API_KEY": api_key}, f)
            print("API Key saved successfully!")
            time.sleep(1)
        else:
            print("No API Key entered. Gemini summarization will not work.")
            time.sleep(2)
    return api_key

def apply_cached_translations(category):
    """Apply cached translations synchronously to entries."""
    cache = load_translation_cache()
    if category not in data:
        return
    for entry in data[category]["entries"]:
        title = entry.get("title", "")
        if title and title in cache:
            entry["title_original"] = title
            entry["title"] = cache[title]

# Asynchronous title translation
def translate_all_titles_async(api_key, category, entries):
    global TRANSLATING_IN_PROGRESS, NEEDS_REDRAW
    TRANSLATING_IN_PROGRESS = True

    try:
        cache = load_translation_cache()
        original_titles = [entry.get("title_original", entry.get("title")) for entry in entries if entry.get("title")]

        translated_titles = translate_titles_batch(original_titles, api_key, cache)
        save_translation_cache(cache)

        if category in data:
            for entry in data[category]["entries"]:
                original_title = entry.get("title_original", entry.get("title"))
                if original_title and original_title in translated_titles:
                    entry["title_original"] = original_title
                    entry["title"] = translated_titles[original_title]
            NEEDS_REDRAW = True
    finally:
        TRANSLATING_IN_PROGRESS = False

def layout(screen):
    global data, CURRENT, gemini_api_key, TRANSLATING_IN_PROGRESS, TRANSLATING_IN_PROGRESS

    translation_cache = load_translation_cache()
    threads = [] # To keep track of translation threads

    def reload_data():

        global data, CURRENT, translation_cache, NEEDS_REDRAW, LOADING_STATUS

        while True:

            time.sleep(1)

            c_category = CURRENT.get("category")

            if (
                c_category in data
                and data[c_category].get("created_at")
                and int(data[c_category].get("created_at")) + CONFIG["refresh"]
                < int(time.time())
                and not CONFIG.get("loading")
            ):

                CONFIG["loading"] = True

                LOADING_STATUS = "UPDATING"
                NEEDS_REDRAW = True

                d = get_feeds_from_rss(CURRENT["category"])

                CONFIG["loading"] = False

                if not d:
                    LOADING_STATUS = "Update failed"
                    NEEDS_REDRAW = True
                    time.sleep(0.5)
                    LOADING_STATUS = None
                    data[c_category]["created_at"] = int(time.time())
                    return

                data[c_category] = d
                apply_cached_translations(c_category)

                if c_category != CURRENT["category"]:
                    return

                if CURRENT["line"] > -1:
                    i = -1
                    for entry in data[c_category]["entries"]:
                        i += 1
                        if entry["id"] == CURRENT["id"]:
                            CURRENT["line"] = i
                            break
                    CURRENT["line"] = i

                # Initiate batch translation for new/updated feeds
                if GEMINI_AVAILABLE and gemini_api_key:
                    thread = threading.Thread(target=translate_all_titles_async, args=(gemini_api_key, c_category, data[c_category]["entries"]))
                    thread.daemon = True
                    threads.append(thread)
                    thread.start()

                LOADING_STATUS = None
                NEEDS_REDRAW = True

    def _char_width(c):
        """Return display width of a character, matching asciimatics print_at logic exactly."""
        if ord(c) >= 256:
            w = _wcwidth(c)
            if w > 0:
                return w
            if w == 0:
                return 0
        return 1

    def is_double_char(c):
        return _char_width(c) == 2

    def text_length(s):
        return sum(_char_width(d) for d in s)

    def wrap_text_for_display(text, width):
        wrapped_lines = []
        current_line = []
        current_width = 0

        words = text.split(' ') # Split by space, adjust if more sophisticated tokenization is needed

        for word in words:
            word_width = text_length(word)
            
            # Check if the word itself is wider than the line
            if word_width > width:
                # If so, break the word
                if current_line: # Add any existing part of the line before breaking the word
                    wrapped_lines.append(" ".join(current_line))
                current_line = []
                current_width = 0

                temp_word = ""
                temp_word_width = 0
                for char in word:
                    char_width = text_length(char)
                    if temp_word_width + char_width > width:
                        wrapped_lines.append(temp_word)
                        temp_word = char
                        temp_word_width = char_width
                    else:
                        temp_word += char
                        temp_word_width += char_width
                if temp_word:
                    current_line.append(temp_word)
                    current_width = temp_word_width
                continue

            if current_width + (text_length(" ") if current_line else 0) + word_width > width:
                wrapped_lines.append(" ".join(current_line))
                current_line = [word]
                current_width = word_width
            else:
                if current_line:
                    current_width += text_length(" ")
                current_line.append(word)
                current_width += word_width
        
        if current_line:
            wrapped_lines.append(" ".join(current_line))
        
        return wrapped_lines


    def alert(screen, text):

        space = 3
        length = text_length(text) + space * 2
        text = " " * space + text + " " * space
        pos = (screen.width - len(text), 0)

        screen.print_at(
            text, pos[0], pos[1], colour=COLOR["alertfg"], bg=COLOR["alertbg"]
        )
        screen.refresh()

    def display_translating_status(screen):
        if TRANSLATING_IN_PROGRESS:
            status_text = "Translating..."
            status_width = text_length(status_text)
            status_x = screen.width - status_width - 1 # 1 for padding
            screen.print_at(status_text, status_x, 0, colour=COLOR["alertfg"], bg=COLOR["alertbg"])
        else:
            # Clear the area if not translating
            status_text = " " * (text_length("Translating...") + 1)
            status_x = screen.width - text_length("Translating...") - 1
            screen.print_at(status_text, status_x, 0, colour=0, bg=0)

    def slice_text(s, l, max_width=80, shift=0):
        rslt = ""

        string_length = text_length(s)

        over = string_length > max_width

        if over:  # to show a marquee
            if (
                string_length - shift + CONFIG["marqueeDelayReturn"] < max_width
                or shift == -1
            ):
                if CURRENT.get("direction", "left") == "left":
                    CURRENT["direction"] = "right"
                else:
                    CURRENT["direction"] = "left"

            if CURRENT.get("direction", "left") == "left":
                if shift < CONFIG["marqueeDelay"]:
                    shift = 0
                else:
                    shift -= CONFIG["marqueeDelay"]

            if string_length - shift + max_width / 4 < max_width:
                shift = string_length - max_width + max_width / 4

        m = 0
        for d in s:
            cw = _char_width(d)
            if not over:
                if m + cw > l:
                    break
                rslt += d
                m += cw
            else:
                m += cw
                if m == shift and cw == 2:
                    rslt += " "
                elif m >= shift:
                    # Check if adding this char would overshoot visible width
                    if m > l + shift and cw == 2:
                        rslt += " "
                    else:
                        rslt += d

                if m >= l + shift or m >= max_width + shift:
                    break

        # Pad to fill the visible width so no gap remains
        rslt_width = text_length(rslt)
        if rslt_width < l:
            rslt += " " * (l - rslt_width)

        return rslt

    def draw_categories():

        screen.print_at(
            "." * screen.width, 0, 0, colour=COLOR["categorybg"], bg=COLOR["categorybg"]
        )

        x = 1
        for category in CONFIG["categories"]:
            s = " %s " % category[1]
            if category[0] == CURRENT["category"]:
                screen.print_at(
                    s, x, 0, colour=COLOR["categoryfgS"], bg=COLOR["categorybgS"]
                )
            else:
                screen.print_at(
                    s, x, 0, colour=COLOR["categoryfg"], bg=COLOR["categorybg"]
                )

            x += len(s) + 2

        display_translating_status(screen)

    def draw_entries(clearline=False, force=False, lines=False):

        category_ = CURRENT["category"]

        if category_ not in FIELDS:
            category_ = "default"

        line_range = range(0, CONFIG["rowlimit"])

        if lines:
            line_range = range(0, lines)

        elif CURRENT["line"] > -1 and not force:
            line_range = [CURRENT["line"]]
            if CURRENT["oline"] != CURRENT["line"] and CURRENT["oline"] != -1:
                line_range = [CURRENT["oline"], CURRENT["line"]]

        for i in line_range:
            is_selected = (i == CURRENT["line"]) and not CURRENT.get("input", False)
            row = i + 1

            if is_selected:
                screen.print_at(
                    " " * screen.width,
                    0,
                    row,
                    colour=COLOR["selected"],
                    bg=COLOR["selected"],
                )
            else:
                screen.print_at(" " * screen.width, 0, row, colour=0, bg=0)

            if CURRENT["line"] > -1 and clearline and not force and not is_selected:
                screen.refresh()

            for f in FIELDS[category_]:
                kColor = 2 if len(f) > 2 else 1

                txt = data[CURRENT["category"]]["entries"][i].get(f[1], "")

                if (
                    is_selected
                    and f[1] + "S" in data[CURRENT["category"]]["entries"][i]
                ):
                    txt = data[CURRENT["category"]]["entries"][i][f[1] + "S"]
                    if f[1] in data[CURRENT["category"]]["entries"][i] and text_length(
                        data[CURRENT["category"]]["entries"][i][f[1]]
                    ) > text_length(txt):

                        txt += " " * (
                            text_length(data[CURRENT["category"]]["entries"][i][f[1]])
                            - text_length(txt)
                        )

                if txt == "":
                    continue

                col = f[0]

                if col < 0:
                    col = screen.width + col - text_length(txt)
                elif CURRENT.get("input", False):
                    col += 4

                fg = COLOR.get(f[kColor], COLOR["default"])
                bg = 0

                if i == CURRENT["line"] and not CURRENT.get("input", False):
                    fg = 0
                    bg = COLOR["selected"]
                    if COLOR.get("%sS" % f[kColor], None):
                        fg = COLOR["%sS" % f[kColor]]

                if is_selected and f[1] in CONFIG["marqueeFields"]:
                    txt = slice_text(
                        txt,
                        screen.width - col - 3,
                        max_width=screen.width - col - 2,
                        shift=CURRENT["shift"],
                    )

                if col > 1:
                    col -= 1
                    txt = " %s " % txt

                if len(f) > 3:
                    txt += " " * 20

                # For selected rows, extend right-aligned fields (date) with
                # a 2-space safe-gap on the left so no dark gap can appear
                if is_selected and f[0] < 0:
                    txt = "  " + txt
                    col -= 2

                try:
                    screen.print_at(txt, col, row, colour=fg, bg=bg)
                except:
                    pass

            if CURRENT["line"] > -1 and clearline and not force and not is_selected:
                screen.refresh()

        if force and line_range[-1] + 1 < screen.height - 1:
            for i in range(line_range[-1] + 2, screen.height):
                screen.print_at(" " * screen.width, 0, i, colour=0, bg=0)

            screen.refresh()

    def do_timer():
        if CURRENT["line"] > -1:
            CURRENT["shift"] = CURRENT.get("shift", 0) + (
                1 if CURRENT.get("direction", "left") == "left" else -1
            )
            draw_entries()
            screen.refresh()

    def reset_list_arrow_key():
        CURRENT["shift"] = 0
        CURRENT["oline"] = CURRENT["line"]

    def show_current_input_number():

        line_range = range(0, CONFIG["rowlimit"])

        try:
            current_number = int(CURRENT["inputnumber"])
        except:
            current_number = ""

        for i in line_range:
            fg = COLOR["number"]
            if i + 1 == current_number:
                fg = COLOR["numberselected"]
            screen.print_at(("%3s" % (i + 1)).rjust(3), 1, i + 1, colour=fg, bg=0)

        screen.refresh()

    def off_number_mode():
        CURRENT["shift"] = 0
        CURRENT["input"] = False
        CURRENT["inputnumber"] = ""

        draw_entries(clearline=True, force=True)
        screen.refresh()

    def open_url(cn):
        url = None
        if "link" in cn:
            url = cn["link"]
        elif "url" in cn:
            url = cn["url"]
        elif "links" in cn and cn["links"]:
            url = cn["links"][0]
        elif "permalink" in cn:
            url = cn["permalink"]

        if not url:
            return False

        if GEMINI_AVAILABLE and gemini_api_key:
            alert(screen, "SUMMARIZING WITH GEMINI...")
            result = summarize_with_gemini(url, gemini_api_key)
            if isinstance(result, tuple) and result[0] == "fetch_error":
                show_summary_modal("HTTP Fetch 실패 (%s)" % result[1], url=url)
            elif result:
                show_summary_modal(result, url=url)
            else:
                webbrowser.open(url, new=2)
        else:
            webbrowser.open(url, new=2)
        return True

    def show_summary_modal(summary_text, url=None):
        scroll_pos = 0
        prev_width = -1
        prev_height = -1
        wrapped_text = []

        while True:
            # Recalculate layout on resize or first run
            if screen.width != prev_width or screen.height != prev_height:
                prev_width = screen.width
                prev_height = screen.height
                modal_width = int(screen.width * 0.8)
                modal_height = int(screen.height * 0.8)
                start_x = (screen.width - modal_width) // 2
                start_y = (screen.height - modal_height) // 2
                content_width = modal_width - 4  # 2 chars padding on each side

                wrapped_text = []
                for paragraph in summary_text.split('\n'):
                    if paragraph.strip() == '':
                        wrapped_text.append('')
                    else:
                        wrapped_text.extend(wrap_text_for_display(paragraph, content_width))

                scroll_pos = min(scroll_pos, max(0, len(wrapped_text) - (modal_height - 4)))
                screen.clear()

            if screen.has_resized():
                break

            # Fill the entire modal area with background
            fill_line = " " * modal_width
            for y in range(modal_height):
                screen.print_at(fill_line, start_x, start_y + y, colour=COLOR["categoryfg"], bg=COLOR["categorybg"])

            # Draw the border
            border_h = "-" * modal_width
            screen.print_at(border_h, start_x, start_y, colour=COLOR["categoryfgS"], bg=COLOR["categorybg"])
            screen.print_at(border_h, start_x, start_y + modal_height - 1, colour=COLOR["categoryfgS"], bg=COLOR["categorybg"])
            for y in range(start_y + 1, start_y + modal_height - 1):
                screen.print_at("|", start_x, y, colour=COLOR["categoryfgS"], bg=COLOR["categorybg"])
                screen.print_at("|", start_x + modal_width - 1, y, colour=COLOR["categoryfgS"], bg=COLOR["categorybg"])

            # Display the text - pad each line to fill content width
            for i, line in enumerate(wrapped_text[scroll_pos:]):
                if i >= modal_height - 4:
                    break
                padding = max(0, content_width - text_length(line))
                padded_line = line + " " * padding
                screen.print_at(padded_line, start_x + 2, start_y + 1 + i, colour=COLOR["categoryfg"], bg=COLOR["categorybg"])

            # Add bottom labels
            bottom_label = "[ESC] Close   [O] Open URL"
            bottom_label_width = text_length(bottom_label)
            bottom_label_x = start_x + (modal_width - bottom_label_width) // 2
            screen.print_at(bottom_label, bottom_label_x, start_y + modal_height - 2, colour=COLOR["categoryfgS"], bg=COLOR["categorybgS"])

            screen.refresh()

            # Wait for keypress
            keycode = screen.get_key()
            if keycode == KEY["esc"]:
                break
            elif keycode in KEY["o"]:
                if url:
                    webbrowser.open(url, new=2)
                break
            elif keycode == KEY["down"]:
                if scroll_pos < len(wrapped_text) - (modal_height - 4):
                    scroll_pos += 1
            elif keycode == KEY["up"]:
                if scroll_pos > 0:
                    scroll_pos -= 1

        # Redraw the main screen after closing the modal
        draw_categories()
        draw_entries(force=True)
        screen.refresh()


    def show_help():
        s = """
            [Up], [Down], [W], [S], [J], [K] : Select from list
[Shift]+[Up], [Shift]+[Down], [PgUp], [PgDn] : Quickly select from list
                                         [O] : Open canonical link
                                         [:] : Select by typing a number from list
                        [Tab], [Shift]+[Tab] : Change the category tab
                             [Q], [Ctrl]+[C] : Quit
"""

        s = s.split("\n")
        lines = len(s)
        width = max([len(d) for d in s]) + 2

        screen.clear()
        top = int(screen.height / 2 - lines / 2)
        left = int(screen.width / 2 - width / 2)
        for i, d in enumerate(s):
            screen.print_at(
                " " * width,
                left - 1,
                top + i,
                colour=COLOR["alertfg"],
                bg=COLOR["alertbg"],
            )
            screen.print_at(
                d, left, top + i, colour=COLOR["alertfg"], bg=COLOR["alertbg"]
            )

        screen.refresh()
        while True:
            if screen.has_resized():
                return
            if screen.get_key():
                return
            time.sleep(0.5)

    reload_loop = threading.Thread(target=reload_data, args=[])
    reload_loop.daemon = True
    reload_loop.start()

    CURRENT = {"line": -1, "column": -1, "category": "news"}

    data[CURRENT["category"]] = get_feed(CURRENT["category"])
    apply_cached_translations(CURRENT["category"])

    CONFIG["rowlimit"] = screen.height - 2

    if len(data[CURRENT["category"]]["entries"]) < CONFIG["rowlimit"]:
        CONFIG["rowlimit"] = len(data[CURRENT["category"]]["entries"])

    if CONFIG["rowlimit"] > 999:
        CONFIG["rowlimit"] = 999

    screen.clear()
    draw_categories()
    draw_entries(force=True)
    screen.refresh()

    # Start async translation after display
    if GEMINI_AVAILABLE and gemini_api_key:
        thread = threading.Thread(target=translate_all_titles_async, args=(gemini_api_key, CURRENT["category"], data[CURRENT["category"]]["entries"]))
        thread.daemon = True
        thread.start()

    current_time = int(time.time() * CONFIG["marqueeSpeed"])

    while True:

        time.sleep(0.02)

        keycode = screen.get_key()

        if keycode:

            if keycode == KEY["esc"] or keycode in KEY["q"]:
                screen.clear()
                screen.refresh()
                return True

            elif CURRENT.get("input"):
                if keycode == KEY["enter"] or keycode == KEY[":"]:

                    if (
                        keycode == KEY["enter"]
                        and CURRENT["inputnumber"] != ""
                        and int(CURRENT["inputnumber"]) <= CONFIG["rowlimit"]
                    ):
                        CURRENT["line"] = int(CURRENT["inputnumber"]) - 1
                    else:
                        CURRENT["line"] = CURRENT["oline"]

                    off_number_mode()
                    continue

                elif keycode in KEYLIST["number"]:
                    if len(CURRENT["inputnumber"]) < 3:
                        CURRENT["inputnumber"] += str(keycode - KEYLIST["number"][0])

                elif keycode == KEY["backspace"]:
                    if CURRENT["inputnumber"] != "":
                        CURRENT["inputnumber"] = CURRENT["inputnumber"][:-1]
                    else:
                        CURRENT["line"] = CURRENT["oline"]
                        off_number_mode()
                        continue

                show_current_input_number()

                continue

            elif keycode in KEY["r"]:
                CURRENT["line"] = -1
                data[CURRENT["category"]] = get_feed(CURRENT["category"])
                CONFIG["rowlimit"] = screen.height - 2
                if len(data[CURRENT["category"]]["entries"]) < CONFIG["rowlimit"]:
                    CONFIG["rowlimit"] = len(data[CURRENT["category"]]["entries"])
                draw_entries()
                screen.refresh()

            elif keycode == KEY["esc"]:
                reset_list_arrow_key()
                CURRENT["line"] = -1

            elif keycode == KEY["down"] or keycode in KEY["j"] + KEY["s"]:
                reset_list_arrow_key()
                CURRENT["line"] += 1
                if CURRENT["line"] >= CONFIG["rowlimit"]:
                    CURRENT["line"] = 0

            elif keycode == KEY["up"] or keycode in KEY["k"] + KEY["w"]:
                reset_list_arrow_key()
                CURRENT["line"] -= 1
                if CURRENT["line"] < 0:
                    CURRENT["line"] = CONFIG["rowlimit"] - 1

            elif keycode == KEY["shiftUp"]:
                reset_list_arrow_key()
                CURRENT["line"] -= 10
                if CURRENT["line"] < 0:
                    CURRENT["line"] = CONFIG["rowlimit"] - 1

            elif keycode == KEY["shiftDown"]:
                CURRENT["shift"] = 0
                CURRENT["oline"] = CURRENT["line"]
                CURRENT["line"] += 10
                if CURRENT["line"] >= CONFIG["rowlimit"]:
                    CURRENT["line"] = 0

            elif keycode in KEY["o"] or keycode == KEY["space"] or keycode == KEY["enter"]:
                if CURRENT["line"] != -1:
                    open_url(data[CURRENT["category"]]["entries"][CURRENT["line"]])


            elif keycode == KEY[":"]:
                CURRENT["input"] = True
                CURRENT["oline"] = CURRENT["line"]
                CURRENT["line"] = -1
                CURRENT["inputnumber"] = ""

                draw_entries(clearline=True, force=True)
                show_current_input_number()
                screen.refresh()

            elif keycode in KEY["h"] or keycode == KEY["?"]:
                show_help()
                draw_categories()
                draw_entries(clearline=True, force=True)
                screen.refresh()

            elif keycode in [KEY["tab"], KEY["shiftTab"]]:
                for idx, d in enumerate(CONFIG["categories"]):
                    if CURRENT["category"] == d[0]:
                        try:
                            CURRENT["category"] = CONFIG["categories"][
                                idx + (1 if keycode == KEY["tab"] else -1)
                            ][0]
                        except:
                            CURRENT["category"] = CONFIG["categories"][
                                0 if keycode == KEY["tab"] else -1
                            ][0]
                        break

                draw_categories()
                alert(screen, "LOADING")

                data[CURRENT["category"]] = get_feed(CURRENT["category"])
                apply_cached_translations(CURRENT["category"])

                CURRENT["line"] = -1
                CURRENT["oline"] = -1
                CONFIG["rowlimit"] = screen.height - 2
                if (
                    CURRENT["category"] in data
                    and len(data[CURRENT["category"]]["entries"]) < CONFIG["rowlimit"]
                ):
                    CONFIG["rowlimit"] = len(data[CURRENT["category"]]["entries"])

                draw_categories()
                draw_entries(force=True)
                screen.refresh()

                # Start async translation after display
                if GEMINI_AVAILABLE and gemini_api_key:
                    thread = threading.Thread(target=translate_all_titles_async, args=(gemini_api_key, CURRENT["category"], data[CURRENT["category"]]["entries"]))
                    thread.daemon = True
                    thread.start()

            if CURRENT["line"] > -1:
                CURRENT["id"] = data[CURRENT["category"]]["entries"][
                    CURRENT["line"]
                ].get("id", "")

            if keycode in KEYLIST["arrow"]:
                draw_entries(clearline=True)
                screen.refresh()

            """  
            # for keycode debug
            screen.print_at('%s   ' % keycode, screen.width - 15, screen.height - 2, colour=0, bg=15)
            screen.refresh()
            #"""

        if CURRENT["line"] > -1:
            o_current_time = current_time
            current_time = int(
                time.time()
                * (
                    CONFIG[
                        "marqueeSpeed"
                        if CURRENT.get("direction", "left") == "left"
                        else "marqueeSpeedReturn"
                    ]
                )
            )

            if o_current_time != current_time:
                do_timer()

        if screen.has_resized():
            return False

        global NEEDS_REDRAW, LOADING_STATUS
        if NEEDS_REDRAW:
            NEEDS_REDRAW = False
            # Recalculate rowlimit for current screen size and data
            if CURRENT["category"] in data:
                CONFIG["rowlimit"] = min(screen.height - 2, len(data[CURRENT["category"]]["entries"]))
                if CONFIG["rowlimit"] > 999:
                    CONFIG["rowlimit"] = 999
            draw_categories()
            draw_entries(force=True)
            if LOADING_STATUS:
                alert(screen, LOADING_STATUS)
            screen.refresh()





def _restore_terminal():
    try:
        curses.endwin()
    except Exception:
        pass
    sys.stdout.write("\033[?25h")  # Show cursor (ANSI escape)
    sys.stdout.flush()


def do():
    def signal_handler(sig, frame):
        _restore_terminal()
        sys.exit("Bye")

    signal.signal(signal.SIGINT, signal_handler)

    if not os.path.isfile(FEEDS_FILE_NAME):
        sys.stdout.write("Initalizing RSS feeds...\n")
        dummy = get_feeds_from_rss(log=True)

    with open(FEEDS_FILE_NAME, "r") as fp:
        RSS = json.load(fp)

    CONFIG["categories"] = tuple([(key, d["title"]) for key, d in RSS.items()])

    # Acquire the Gemini API key before starting the main TUI loop
    global gemini_api_key
    if GEMINI_AVAILABLE:
        gemini_api_key = get_gemini_api_key()
    else:
        gemini_api_key = None

    try:
        while True:
            if Screen.wrapper(layout):
                break
    finally:
        _restore_terminal()

    sys.stdout.write("Bye\n")


if __name__ == "__main__":
    do()
