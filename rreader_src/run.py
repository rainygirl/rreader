# -*- coding:utf-8 -*-

import json
import os
import re
import sys
import signal
import time
import webbrowser
import threading

from asciimatics.screen import Screen
from asciimatics.effects import Print
from asciimatics.scene import Scene
from asciimatics.renderers import ColourImageFile, SpeechBubble

from .common import p, FEEDS_FILE_NAME
from .get_rss import do as getFeedFromRSS


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
    "arrow": [KEY["up"], KEY["down"], KEY["shiftUp"], KEY["shiftDown"], KEY["esc"]] + KEY["s"] + KEY["w"] + KEY["j"] + KEY["k"],
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

data, CURRENT = {}, {}

os.environ.setdefault("ESCDELAY", "10")


def getFeed(category="news"):
    try:
        with open(p["path_data"] + "rss_%s.json" % category, "r") as c:
            d = json.load(c)
    except:
        d = getFeedFromRSS(category)
        if not d:
            sys.exit("oops")
    return d

    return None


def layout(screen):

    global data, CURRENT

    def reloadData():

        global data, CURRENT

        while True:

            time.sleep(1)

            ccategory = CURRENT.get("category")

            if (
                ccategory in data
                and data[ccategory].get("created_at")
                and int(data[ccategory].get("created_at")) + CONFIG["refresh"] < int(time.time())
                and not CONFIG.get("loading")
            ):

                CONFIG["loading"] = True

                alert(screen, "UPDATING")

                d = getFeedFromRSS(CURRENT["category"])

                CONFIG["loading"] = False

                if not d:
                    alert(screen, "Update failed")
                    time.sleep(0.5)
                    data[ccategory]["created_at"] = int(time.time())
                    return

                data[ccategory] = d

                if ccategory != CURRENT["category"]:
                    return

                if CURRENT["line"] > -1:
                    i = -1
                    for entry in data[ccategory]["entries"]:
                        i += 1
                        if entry["id"] == CURRENT["id"]:
                            CURRENT["line"] = i
                            break
                    CURRENT["line"] = i

                drawCategories()
                drawEntries(force=True)
                screen.refresh()

    def isDoubleChar(s):

        return (
            re.compile(
                "(\u00a9|\u00ae|[\u2000-\u3300]|\ud83c[\ud000-\udfff]|\ud83d[\ud000-\udfff]|\ud83e[\ud000-\udfff]|[가-힣]|[\u4e00-\u9fff]|[\u3400-\u4dbf]|[\U00020000-\U0002a6df]|[\U0002a700-\U0002b73f]|[\U0002b740-\U0002b81f]|[\U0002b820-\U0002ceaf])"
            ).findall(s)
            != []
        )

    def textLength(s):

        return sum([2 if isDoubleChar(d) else 1 for d in s])

    def alert(screen, text):

        space = 3
        length = textLength(text) + space * 2
        text = " " * space + text + " " * space
        pos = (screen.width - len(text), 0)

        screen.print_at(text, pos[0], pos[1], colour=COLOR["alertfg"], bg=COLOR["alertbg"])
        screen.refresh()

    def sliceText(s, l, maxwidth=80, shift=0):
        rslt = ""

        stringLength = textLength(s)

        over = stringLength > maxwidth

        if over:  # to show a marquee
            if stringLength - shift + CONFIG["marqueeDelayReturn"] < maxwidth or shift == -1:
                if CURRENT.get("direction", "left") == "left":
                    CURRENT["direction"] = "right"
                else:
                    CURRENT["direction"] = "left"

            if CURRENT.get("direction", "left") == "left":
                if shift < CONFIG["marqueeDelay"]:
                    shift = 0
                else:
                    shift -= CONFIG["marqueeDelay"]

            if stringLength - shift + maxwidth / 4 < maxwidth:
                shift = stringLength - maxwidth + maxwidth / 4

        m = 0
        for d in s:
            m += 1
            if isDoubleChar(d):
                m += 1
            if not over:
                rslt += d
            else:
                if m == shift and isDoubleChar(d):
                    rslt += " "
                elif m >= shift:
                    rslt += d

            if m >= l + shift or m >= maxwidth + shift:
                break

        return rslt

    def drawCategories():

        screen.print_at("." * screen.width, 0, 0, colour=COLOR["categorybg"], bg=COLOR["categorybg"])

        x = 1
        for category in CONFIG["categories"]:
            s = " %s " % category[1]
            if category[0] == CURRENT["category"]:
                screen.print_at(s, x, 0, colour=COLOR["categoryfgS"], bg=COLOR["categorybgS"])
            else:
                screen.print_at(s, x, 0, colour=COLOR["categoryfg"], bg=COLOR["categorybg"])

            x += len(s) + 2

    def drawEntries(clearline=False, force=False, lines=False):

        category_ = CURRENT["category"]

        if category_ not in FIELDS:
            category_ = "default"

        lineRange = range(0, CONFIG["rowlimit"])

        if lines:
            lineRange = range(0, lines)

        elif CURRENT["line"] > -1 and not force:
            lineRange = [CURRENT["line"]]
            if CURRENT["oline"] != CURRENT["line"] and CURRENT["oline"] != -1:
                lineRange = [CURRENT["oline"], CURRENT["line"]]

        for i in lineRange:
            isSelected = (i == CURRENT["line"]) and not CURRENT.get("input", False)
            row = i + 1

            if isSelected:
                screen.print_at(
                    " " * screen.width,
                    0,
                    row,
                    colour=COLOR["selected"],
                    bg=COLOR["selected"],
                )
            else:
                screen.print_at(" " * screen.width, 0, row, colour=0, bg=0)

            if CURRENT["line"] > -1 and clearline and not force and not isSelected:
                screen.refresh()

            for f in FIELDS[category_]:
                kColor = 2 if len(f) > 2 else 1

                txt = data[CURRENT["category"]]["entries"][i].get(f[1], "")

                if isSelected and f[1] + "S" in data[CURRENT["category"]]["entries"][i]:
                    txt = data[CURRENT["category"]]["entries"][i][f[1] + "S"]
                    if f[1] in data[CURRENT["category"]]["entries"][i] and len(data[CURRENT["category"]]["entries"][i][f[1]]) > len(txt):

                        txt += " " * (len(data[CURRENT["category"]]["entries"][i][f[1]]) - len(txt))

                if txt == "":
                    continue

                col = f[0]

                if col < 0:
                    col = screen.width + col - len(txt)
                elif CURRENT.get("input", False):
                    col += 4

                fg = COLOR.get(f[kColor], COLOR["default"])
                bg = 0

                if i == CURRENT["line"] and not CURRENT.get("input", False):
                    fg = 0
                    bg = COLOR["selected"]
                    if COLOR.get("%sS" % f[kColor], None):
                        fg = COLOR["%sS" % f[kColor]]

                if isSelected and f[1] in CONFIG["marqueeFields"]:
                    txt = sliceText(
                        txt,
                        screen.width - col - 1,
                        maxwidth=screen.width - col,
                        shift=CURRENT["shift"],
                    )

                if col > 1:
                    col -= 1
                    txt = " %s " % txt

                if len(f) > 3:
                    txt += " " * 20

                try:
                    screen.print_at(txt, col, row, colour=fg, bg=bg)
                except:
                    pass

            if CURRENT["line"] > -1 and clearline and not force and not isSelected:
                screen.refresh()

        if force and lineRange[-1] + 1 < screen.height - 1:
            for i in range(lineRange[-1] + 2, screen.height):
                screen.print_at(" " * screen.width, 0, i, colour=0, bg=0)

            screen.refresh()

    def doTimer():
        if CURRENT["line"] > -1:
            CURRENT["shift"] = CURRENT.get("shift", 0) + (1 if CURRENT.get("direction", "left") == "left" else -1)
            drawEntries()
            screen.refresh()

    def resetListArrowKey():
        CURRENT["shift"] = 0
        CURRENT["oline"] = CURRENT["line"]

    def showCurrentInputNumber():

        lineRange = range(0, CONFIG["rowlimit"])

        try:
            currentNumber = int(CURRENT["inputnumber"])
        except:
            currentNumber = ""

        for i in lineRange:
            fg = COLOR["number"]
            if i + 1 == currentNumber:
                fg = COLOR["numberselected"]
            screen.print_at(("%3s" % (i + 1)).rjust(3), 1, i + 1, colour=fg, bg=0)

        screen.refresh()

    def offNumberMode():
        CURRENT["shift"] = 0
        CURRENT["input"] = False
        CURRENT["inputnumber"] = ""

        drawEntries(clearline=True, force=True)
        screen.refresh()

    def openURL(cn):

        if "link" in cn:
            webbrowser.open(cn["link"], new=2)
        elif "url" in cn:
            webbrowser.open(cn["url"], new=2)
        elif "links" in cn:
            if len(cn["links"]) == 1:
                webbrowser.open(cn["links"][0], new=2)
            else:
                webbrowser.open(cn["permalink"], new=2)
        elif "permalink" in cn:
            webbrowser.open(cn["permalink"], new=2)
        else:
            return False

        return True

    def showHelp():
        w = 60
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
            screen.print_at(d, left, top + i, colour=COLOR["alertfg"], bg=COLOR["alertbg"])

        screen.refresh()
        idx = 0
        while True:
            if screen.get_key():
                return
            time.sleep(0.5)

        screen.clear()

    reloadLoop = threading.Thread(target=reloadData, args=[])
    reloadLoop.daemon = True
    reloadLoop.start()

    CURRENT = {"line": -1, "column": -1, "category": "news"}

    data[CURRENT["category"]] = getFeed(CURRENT["category"])

    CONFIG["rowlimit"] = screen.height - 2

    if len(data[CURRENT["category"]]["entries"]) < CONFIG["rowlimit"]:
        CONFIG["rowlimit"] = len(data[CURRENT["category"]]["entries"])

    if CONFIG["rowlimit"] > 999:
        CONFIG["rowlimit"] = 999

    screen.clear()
    drawCategories()
    drawEntries(force=True)
    screen.refresh()

    currentTime = int(time.time() * CONFIG["marqueeSpeed"])

    while True:

        time.sleep(0.02)

        keyCode = screen.get_key()

        if keyCode:

            if keyCode == KEY["esc"] or keyCode in KEY["q"]:
                screen.clear()
                screen.refresh()
                return True

            elif CURRENT.get("input"):
                if keyCode == KEY["enter"] or keyCode == KEY[":"]:

                    if keyCode == KEY["enter"] and CURRENT["inputnumber"] != "" and int(CURRENT["inputnumber"]) <= CONFIG["rowlimit"]:
                        CURRENT["line"] = int(CURRENT["inputnumber"]) - 1
                    else:
                        CURRENT["line"] = CURRENT["oline"]

                    offNumberMode()
                    continue

                elif keyCode in KEYLIST["number"]:
                    if len(CURRENT["inputnumber"]) < 3:
                        CURRENT["inputnumber"] += str(keyCode - KEYLIST["number"][0])

                elif keyCode == KEY["backspace"]:
                    if CURRENT["inputnumber"] != "":
                        CURRENT["inputnumber"] = CURRENT["inputnumber"][:-1]
                    else:
                        CURRENT["line"] = CURRENT["oline"]
                        offNumberMode()
                        continue

                showCurrentInputNumber()

                continue

            elif keyCode in KEY["r"]:
                CURRENT["line"] = -1
                data[CURRENT["category"]] = getFeed(CURRENT["category"])
                CONFIG["rowlimit"] = screen.height - 1
                if len(data[CURRENT["category"]]["entries"]) < CONFIG["rowlimit"]:
                    CONFIG["rowlimit"] = len(data[CURRENT["category"]]["entries"])
                drawEntries()
                screen.refresh()

            elif keyCode == KEY["esc"]:
                resetListArrowKey()
                CURRENT["line"] = -1

            elif keyCode == KEY["down"] or keyCode in KEY["j"] + KEY["s"]:
                resetListArrowKey()
                CURRENT["line"] += 1
                if CURRENT["line"] >= CONFIG["rowlimit"]:
                    CURRENT["line"] = 0

            elif keyCode == KEY["up"] or keyCode in KEY["k"] + KEY["w"]:
                resetListArrowKey()
                CURRENT["line"] -= 1
                if CURRENT["line"] < 0:
                    CURRENT["line"] = CONFIG["rowlimit"] - 1

            elif keyCode == KEY["shiftUp"]:
                resetListArrowKey()
                CURRENT["line"] -= 10
                if CURRENT["line"] < 0:
                    CURRENT["line"] = CONFIG["rowlimit"] - 1

            elif keyCode == KEY["shiftDown"]:
                CURRENT["shift"] = 0
                CURRENT["oline"] = CURRENT["line"]
                CURRENT["line"] += 10
                if CURRENT["line"] >= CONFIG["rowlimit"]:
                    CURRENT["line"] = 0

            elif keyCode in KEY["o"]:
                openURL(data[CURRENT["category"]]["entries"][CURRENT["line"]])

            elif keyCode == KEY["space"]:
                cn = data[CURRENT["category"]]["entries"][CURRENT["line"]]

                openURL(cn)

            elif keyCode == KEY[":"]:
                CURRENT["input"] = True
                CURRENT["oline"] = CURRENT["line"]
                CURRENT["line"] = -1
                CURRENT["inputnumber"] = ""

                drawEntries(clearline=True, force=True)
                showCurrentInputNumber()
                screen.refresh()

            elif keyCode in KEY["h"] or keyCode == KEY["?"]:
                showHelp()
                drawCategories()
                drawEntries(clearline=True, force=True)
                screen.refresh()

            elif keyCode in [KEY["tab"], KEY["shiftTab"]]:
                for idx, d in enumerate(CONFIG["categories"]):
                    if CURRENT["category"] == d[0]:
                        try:
                            CURRENT["category"] = CONFIG["categories"][idx + (1 if keyCode == KEY["tab"] else -1)][0]
                        except:
                            CURRENT["category"] = CONFIG["categories"][0 if keyCode == KEY["tab"] else -1][0]
                        break

                drawCategories()
                alert(screen, "LOADING")

                data[CURRENT["category"]] = getFeed(CURRENT["category"])

                CURRENT["line"] = -1
                CURRENT["oline"] = -1
                CONFIG["rowlimit"] = screen.height - 1
                if CURRENT["category"] in data and len(data[CURRENT["category"]]["entries"]) < CONFIG["rowlimit"]:
                    CONFIG["rowlimit"] = len(data[CURRENT["category"]]["entries"])

                drawCategories()
                drawEntries(force=True)
                screen.refresh()

            if CURRENT["line"] > -1:
                CURRENT["id"] = data[CURRENT["category"]]["entries"][CURRENT["line"]].get("id", "")

            if keyCode in KEYLIST["arrow"]:
                drawEntries(clearline=True)
                screen.refresh()

            """  
            # for keyCode debug
            screen.print_at('%s   ' % keyCode, screen.width - 15, screen.height - 2, colour=0, bg=15)
            screen.refresh()
            #"""

        if CURRENT["line"] > -1:
            oCurrentTime = currentTime
            currentTime = int(time.time() * (CONFIG["marqueeSpeed" if CURRENT.get("direction", "left") == "left" else "marqueeSpeedReturn"]))

            if oCurrentTime != currentTime:
                doTimer()

        if screen.has_resized():
            return False


def do():
    def signalHandler(sig, frame):
        sys.exit("Bye")

    signal.signal(signal.SIGINT, signalHandler)

    if not os.path.isfile(FEEDS_FILE_NAME):
        sys.stdout.write("Initalizing RSS feeds...\n")
        dummy = getFeedFromRSS(log=True)

    with open(FEEDS_FILE_NAME, "r") as fp:
        RSS = json.load(fp)

    CONFIG["categories"] = tuple([(key, d["title"]) for key, d in RSS.items()])

    while True:
        if Screen.wrapper(layout):
            break

    sys.stdout.write("Bye\n")


if __name__ == "__main__":
    do()
