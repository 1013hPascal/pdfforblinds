"""Exakte Vektordaten einer Grafik aus der PDF auslesen und als Text für die Bildbeschreibung aufbereiten.

Bei Vektorgrafiken (z. B. aus LaTeX) stehen Linien, Pfeile und Beschriftungen
mit exakten Koordinaten in der PDF. Diese werden entdoppelt, Pfeilspitzen den
Linien zugeordnet und, wenn möglich, über die Achsenbeschriftungen in
Achsen-Einheiten umgerechnet. Bei Rasterbildern (Fotos, Scans) gibt es keine
solchen Daten; dann liefert extract() None.
"""

import math
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from . import config

MARGIN = 0.01
ARROWHEAD_MAX = 20      # Punkte: gefüllte Formen bis zu dieser Größe gelten als Pfeilspitze
ATTACH_DIST = 6         # Punkte: max. Abstand Linienende <-> Pfeilspitze
LABEL_DIST = 20         # Punkte: max. Abstand Beschriftung <-> Pfeil
MAX_ELEMENTS = 40
MAX_DRAWINGS = 80       # mehr Zeichnungen -> nur die Texte ausgeben
DOT_SIZE = 4            # Punkte: kleinere geschlossene Kurven sind markierte Punkte
LABEL_MAX_LEN = 3       # nur kurze Bezeichner (a, b, T, F1) werden Pfeilen/Linien zugeordnet
NUMBER_RE = re.compile(r"^[-−]?\d+([.,]\d+)?$")

Point = tuple[float, float]


@dataclass
class Arrowhead:
    tip: Point
    base: Point          # Mittelpunkt der übrigen Ecken
    used: bool = False

    @property
    def direction(self) -> str:
        dx, dy = self.tip[0] - self.base[0], self.base[1] - self.tip[1]
        angle = math.degrees(math.atan2(dy, dx)) % 360
        names = ["rechts", "rechts oben", "oben", "links oben", "links", "links unten", "unten", "rechts unten"]
        return names[int((angle + 22.5) // 45) % 8]


@dataclass
class Word:
    text: str
    rect: pymupdf.Rect

    @property
    def center(self) -> Point:
        return ((self.rect.x0 + self.rect.x1) / 2, (self.rect.y0 + self.rect.y1) / 2)


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _dist_to_segment(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    length2 = (bx - ax) ** 2 + (by - ay) ** 2
    if length2 == 0:
        return _dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - ax) * (bx - ax) + (p[1] - ay) * (by - ay)) / length2))
    return _dist(p, (ax + t * (bx - ax), ay + t * (by - ay)))


def _points(drawing) -> list[Point]:
    pts = []
    for item in drawing["items"]:
        for p in item[1:]:
            if isinstance(p, pymupdf.Point):
                pts.append((p.x, p.y))
            elif isinstance(p, pymupdf.Rect):
                pts += [(p.x0, p.y0), (p.x1, p.y0), (p.x1, p.y1), (p.x0, p.y1)]
            elif isinstance(p, pymupdf.Quad):
                pts += [(q.x, q.y) for q in (p.ul, p.ur, p.lr, p.ll)]
    return pts


def _key(drawing) -> tuple:
    return (bool(drawing.get("fill")), tuple((round(x, 1), round(y, 1)) for x, y in _points(drawing)))


class _Axes:
    """Umrechnung von PDF-Punkten in Achsen-Einheiten."""

    def __init__(self, origin_x, origin_y, scale_x, scale_y, x_name, y_name):
        self.origin_x, self.origin_y = origin_x, origin_y
        self.scale_x, self.scale_y = scale_x, scale_y
        self.x_name, self.y_name = x_name, y_name

    def __call__(self, p: Point) -> Point:
        return ((p[0] - self.origin_x) / self.scale_x, (self.origin_y - p[1]) / self.scale_y)


def _number(text: str) -> float:
    return float(text.replace("−", "-").replace(",", "."))


def _calibrate(words: list[Word], heads: list[Arrowhead]) -> _Axes | None:
    """Ursprung aus den Achsen-Pfeilspitzen bzw. der 0-Beschriftung, Maßstab aus der weitesten Zahl."""
    numbers = [w for w in words if NUMBER_RE.match(w.text)]
    if len(numbers) < 2:
        return None

    def rows(key):
        groups: list[list[Word]] = []
        for w in sorted(numbers, key=key):
            if groups and abs(key(groups[-1][0]) - key(w)) < 4:
                groups[-1].append(w)
            else:
                groups.append([w])
        return [g for g in groups if len({_number(w.text) for w in g}) >= 2]

    x_rows = rows(lambda w: w.center[1])   # Zahlen in einer Zeile -> x-Achse
    y_cols = rows(lambda w: w.center[0])   # Zahlen in einer Spalte -> y-Achse
    if not x_rows or not y_cols:
        return None
    x_ticks = max(x_rows, key=len)
    y_ticks = max(y_cols, key=len)

    right = [h for h in heads if h.direction == "rechts"]
    up = [h for h in heads if h.direction == "oben"]
    # Ursprung: Achsen-Pfeilspitzen, sonst Position der Beschriftung 0
    if up:
        origin_x = up[0].tip[0]
    else:
        zero = next((w for w in x_ticks if _number(w.text) == 0), None)
        if zero is None:
            return None
        origin_x = zero.center[0]
    if right:
        origin_y = right[0].tip[1]
    else:
        zero = next((w for w in y_ticks if _number(w.text) == 0), None)
        if zero is None:
            return None
        origin_y = zero.center[1]

    far_x = max(x_ticks, key=lambda w: abs(_number(w.text)))
    far_y = max(y_ticks, key=lambda w: abs(_number(w.text)))
    if _number(far_x.text) == 0 or _number(far_y.text) == 0:
        return None
    scale_x = (far_x.center[0] - origin_x) / _number(far_x.text)
    scale_y = (origin_y - far_y.center[1]) / _number(far_y.text)
    if abs(scale_x) < 1 or abs(scale_y) < 1:
        return None

    tick_words = set(map(id, x_ticks + y_ticks))
    letters = [w for w in words if id(w) not in tick_words and len(w.text) <= 2 and w.text.isalpha()]
    x_name = next((w.text for w in letters if right and _dist(w.center, right[0].tip) < 25), "x")
    y_name = next((w.text for w in letters if up and _dist(w.center, up[0].tip) < 25), "y")
    return _Axes(origin_x, origin_y, scale_x, scale_y, x_name, y_name)


def _fmt(v: float) -> str:
    return f"{v:.1f}".replace(".", ",").replace("-0,0", "0,0")


def extract(source: Path, page_nr: int, bbox) -> str | None:
    if not bbox or source.suffix.lower() in config.IMAGE_SUFFIXES or not source.exists():
        return None
    doc = pymupdf.open(source)
    try:
        page = doc[page_nr - 1]
        r = page.rect
        x1, y1, x2, y2 = bbox
        clip = pymupdf.Rect(r.x0 + (x1 - MARGIN) * r.width, r.y0 + (y1 - MARGIN) * r.height,
                            r.x0 + (x2 + MARGIN) * r.width, r.y0 + (y2 + MARGIN) * r.height)

        seen = set()
        drawings = []
        for d in page.get_drawings():
            if not d["rect"].intersects(clip):
                continue
            key = _key(d)
            if key not in seen:
                seen.add(key)
                drawings.append(d)

        # Nur Wörter, die wirklich zur Grafik gehören: Mitte im Bildbereich, ganz im Ausschnitt
        inner = pymupdf.Rect(r.x0 + x1 * r.width, r.y0 + y1 * r.height, r.x0 + x2 * r.width, r.y0 + y2 * r.height)
        words, seen_words = [], set()
        for w in page.get_text("words"):
            rect = pymupdf.Rect(w[:4])
            key = (w[4], round(w[0]), round(w[1]))
            if key in seen_words or not clip.contains(rect):
                continue
            word = Word(w[4], rect)
            if inner.contains(pymupdf.Point(word.center)):
                seen_words.add(key)
                words.append(word)
    finally:
        doc.close()

    def text_only() -> str | None:
        # Komplexes Diagramm: Geometrie wäre nur Rauschen, die exakten Texte helfen trotzdem
        if not words:
            return None
        return ("Exakt aus der PDF ausgelesene Texte in diesem Bild (in Lesereihenfolge): "
                + " ".join(w.text for w in words))

    if not drawings:
        return None
    if len(drawings) > MAX_DRAWINGS:
        return text_only()

    heads: list[Arrowhead] = []
    segments: list[tuple[Point, Point]] = []
    curves: list[list[Point]] = []
    for d in drawings:
        pts = _points(d)
        if d.get("fill") and d["rect"].width <= ARROWHEAD_MAX and d["rect"].height <= ARROWHEAD_MAX and len(pts) >= 3:
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            tip = max(pts, key=lambda p: _dist(p, (cx, cy)))
            rest = [p for p in pts if p != tip]
            base = (sum(p[0] for p in rest) / len(rest), sum(p[1] for p in rest) / len(rest))
            heads.append(Arrowhead(tip, base))
            continue
        for item in d["items"]:
            if item[0] == "l":
                segments.append(((item[1].x, item[1].y), (item[2].x, item[2].y)))
            elif item[0] == "c":
                if curves and _dist(curves[-1][-1], (item[1].x, item[1].y)) < 0.5:
                    curves[-1].append((item[4].x, item[4].y))
                else:
                    curves.append([(item[1].x, item[1].y), (item[4].x, item[4].y)])
            elif item[0] == "re":
                rect = item[1]
                segments += [((rect.x0, rect.y0), (rect.x1, rect.y0)), ((rect.x1, rect.y0), (rect.x1, rect.y1)),
                             ((rect.x1, rect.y1), (rect.x0, rect.y1)), ((rect.x0, rect.y1), (rect.x0, rect.y0))]

    axes = _calibrate(words, heads)
    if axes:
        conv = axes

        def where(p):
            x, y = conv(p)
            return f"({_fmt(x)} | {_fmt(y)})"
    else:
        def where(p):
            x = (p[0] - clip.x0) / clip.width * 100
            y = (clip.y1 - p[1]) / clip.height * 100
            return f"({x:.0f} % | {y:.0f} %)"

    used_words: set[int] = set()

    def label_for(a: Point, b: Point) -> str:
        best, best_d = None, LABEL_DIST
        for w in words:
            if id(w) in used_words or NUMBER_RE.match(w.text) or len(w.text) > LABEL_MAX_LEN:
                continue
            dist = _dist_to_segment(w.center, a, b)
            if dist < best_d:
                best, best_d = w, dist
        if best is None:
            return ""
        used_words.add(id(best))
        return f" mit der Beschriftung „{best.text}“"

    lines: list[str] = []
    if axes:
        lines.append(f"Achsen: {axes.x_name}-Achse nach rechts, {axes.y_name}-Achse nach oben, Ursprung (0 | 0). "
                     f"Maßstab aus den Achsenbeschriftungen abgeleitet.")
        for h in heads:
            if (h.direction == "rechts" and abs(h.tip[1] - axes.origin_y) < 2) or \
                    (h.direction == "oben" and abs(h.tip[0] - axes.origin_x) < 2):
                h.used = True  # Pfeilspitzen der Achsen
        for w in words:
            if w.text in (axes.x_name, axes.y_name) or NUMBER_RE.match(w.text):
                used_words.add(id(w))

    def on_axis(a: Point, b: Point) -> bool:
        if not axes:
            return False
        horizontal = abs(a[1] - axes.origin_y) < 2 and abs(b[1] - axes.origin_y) < 2
        vertical = abs(a[0] - axes.origin_x) < 2 and abs(b[0] - axes.origin_x) < 2
        return horizontal or vertical

    for a, b in segments:
        if _dist(a, b) < 1 or on_axis(a, b):
            continue
        head = None
        for h in heads:
            if h.used:
                continue
            for start, end in ((a, b), (b, a)):
                if _dist(end, h.base) < ATTACH_DIST or _dist(end, h.tip) < ATTACH_DIST:
                    head, a, b = h, start, end
                    break
            if head:
                break
        if head:
            head.used = True
            lines.append(f"Pfeil{label_for(a, head.tip)}: von {where(a)} nach {where(head.tip)}")
        else:
            lines.append(f"Linie{label_for(a, b)}: von {where(a)} nach {where(b)}")

    for h in heads:
        if not h.used:
            lines.append(f"Pfeilspitze bei {where(h.tip)}, zeigt nach {h.direction}")

    dots: list[Point] = []
    for pts in curves:
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        if max(xs) - min(xs) < DOT_SIZE and max(ys) - min(ys) < DOT_SIZE:
            center = (sum(xs) / len(xs), sum(ys) / len(ys))
            if all(_dist(center, d) > 1 for d in dots):
                dots.append(center)
            continue
        step = max(1, len(pts) // 8)
        sample = pts[::step] + ([pts[-1]] if (len(pts) - 1) % step else [])
        lines.append(f"Kurve{label_for(pts[0], pts[-1])} durch die Punkte " + ", ".join(where(p) for p in sample))

    for d in dots:
        lines.append(f"Punkt{label_for(d, d)} bei {where(d)}")

    rest = [w for w in words if id(w) not in used_words]
    for w in rest:
        lines.append(f"Text „{w.text}“ bei {where(w.center)}")

    if len(lines) > MAX_ELEMENTS:
        return text_only()

    if axes:
        header = ("Exakt aus der PDF ausgelesene Zeichnungsdaten dieses Bildes, umgerechnet in Achsen-Einheiten "
                  "(Genauigkeit etwa ±0,1, da der Maßstab aus der Lage der Achsenbeschriftungen stammt):")
    else:
        header = ("Exakt aus der PDF ausgelesene Zeichnungsdaten dieses Bildes. Positionen in Prozent der "
                  "Bildbreite und -höhe, gemessen von unten links:")
    return header + "\n" + "\n".join(lines)
