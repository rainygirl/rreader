"""Writes the news.coroke.net app icon as HVIF (Haiku Vector Icon Format)."""
import math
import struct
import sys

STYLE_SOLID = 1
STYLE_GRADIENT = 2
GRAD_TRANSFORM, GRAD_NO_ALPHA = 0x02, 0x04
PATH_CLOSED, PATH_NO_CURVES = 0x02, 0x08
SHAPE_PATH_SOURCE = 0x0A
SHAPE_HAS_TRANSFORMERS = 0x10
TRANSFORMER_STROKE = 23


def f24(v):
    if v == 0:
        return b"\0\0\0"
    bits = struct.unpack(">I", struct.pack(">f", v))[0]
    sign = bits >> 31
    exp = ((bits >> 23) & 0xFF) - 127 + 32
    mant = (bits & 0x7FFFFF) >> 6
    exp = max(0, min(63, exp))
    n = (sign << 23) | (exp << 17) | mant
    return bytes([(n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF])


def coord(v):
    n = int(round((v + 128.0) * 102.0))
    return bytes([0x80 | (n >> 8), n & 0xFF])


class Icon:
    def __init__(self):
        self.styles, self.paths, self.shapes = [], [], []

    def solid(self, r, g, b, a=255):
        self.styles.append(bytes([STYLE_SOLID, r, g, b, a]))
        return len(self.styles) - 1

    def gradient(self, a, b, stops):
        """Linear gradient from point a to b; stops: [(offset 0..1, (r,g,b))]."""
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        s = length / 128.0
        cos, sin = dx / length, dy / length
        matrix = [s * cos, s * sin, -s * sin, s * cos, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
        out = bytes([STYLE_GRADIENT, 0, GRAD_TRANSFORM | GRAD_NO_ALPHA, len(stops)])
        out += b"".join(f24(m) for m in matrix)
        for off, (r, g, bb) in stops:
            out += bytes([int(round(off * 255)), r, g, bb])
        self.styles.append(out)
        return len(self.styles) - 1

    def poly(self, points):
        out = bytes([PATH_CLOSED | PATH_NO_CURVES, len(points)])
        out += b"".join(coord(x) + coord(y) for x, y in points)
        self.paths.append(out)
        return len(self.paths) - 1

    def fill(self, style, path):
        self.shapes.append(bytes([SHAPE_PATH_SOURCE, style, 1, path, 0]))

    def stroke(self, style, path, width):
        self.shapes.append(bytes([SHAPE_PATH_SOURCE, style, 1, path, SHAPE_HAS_TRANSFORMERS, 1,
                                  TRANSFORMER_STROKE, int(width + 128), 0x02 | (0x02 << 4), 4]))

    def data(self):
        out = b"ncif"
        for section in (self.styles, self.paths, self.shapes):
            out += bytes([len(section)]) + b"".join(section)
        return out


# Page corners, tilted BeOS-style: leaning back to the upper right.
TL, TR, BR, BL = (13.0, 12.0), (52.0, 20.0), (46.0, 56.0), (6.0, 47.0)


def at(u, v):
    x = TL[0] * (1 - u) * (1 - v) + TR[0] * u * (1 - v) + BR[0] * u * v + BL[0] * (1 - u) * v
    y = TL[1] * (1 - u) * (1 - v) + TR[1] * u * (1 - v) + BR[1] * u * v + BL[1] * (1 - u) * v
    return (x, y)


def quad(u0, v0, u1, v1):
    return [at(u0, v0), at(u1, v0), at(u1, v1), at(u0, v1)]


def shifted(points, dx, dy):
    return [(x + dx, y + dy) for x, y in points]


icon = Icon()
page = quad(0, 0, 1, 1)

shadow = icon.solid(0, 0, 0, 70)
icon.fill(shadow, icon.poly(shifted(page, 4.5, 5.5)))

# Stacked pages underneath give the paper some thickness.
under_style = icon.gradient(at(0, 0), at(1, 1), [(0, (0xE6, 0xDD, 0xC8)), (1, (0xA8, 0x9C, 0x82))])
under = icon.poly(shifted(page, 2.2, 2.6))
icon.fill(under_style, under)
outline = icon.solid(0x3A, 0x2E, 0x22, 230)
icon.stroke(outline, under, 1.4)

paper = icon.gradient(at(0, 0), at(1, 1), [(0, (0xFF, 0xFE, 0xF8)), (0.6, (0xF3, 0xEC, 0xDC)), (1, (0xD8, 0xCE, 0xB6))])
page_path = icon.poly(page)
icon.fill(paper, page_path)

masthead = icon.gradient(at(0, 0.06), at(0, 0.22), [(0, (0xF6, 0xA8, 0x8C)), (1, (0xD8, 0x6A, 0x4A))])
icon.fill(masthead, icon.poly(quad(0.08, 0.07, 0.92, 0.21)))

ink = icon.solid(0x4A, 0x44, 0x3E)
icon.fill(ink, icon.poly(quad(0.08, 0.28, 0.92, 0.35)))

photo = icon.gradient(at(0.08, 0.44), at(0.45, 0.72), [(0, (0x9C, 0xC8, 0xEE)), (1, (0x3E, 0x6E, 0xA8))])
icon.fill(photo, icon.poly(quad(0.08, 0.43, 0.45, 0.72)))

text = icon.solid(0x8A, 0x82, 0x78)
for v in (0.44, 0.53, 0.62, 0.70):
    icon.fill(text, icon.poly(quad(0.53, v, 0.92, v + 0.035)))
for v in (0.80, 0.88):
    icon.fill(text, icon.poly(quad(0.08, v, 0.92, v + 0.035)))

icon.stroke(outline, page_path, 1.6)

sys.stdout.buffer.write(icon.data())
