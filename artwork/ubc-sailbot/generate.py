# /// script
# dependencies = ["fonttools"]
# ///
"""Generate UBC Sailbot logo as SVG preview and KiCad footprint.

Vector rebuild of ubc-sailbot.png (280x280). Reference geometry in source
pixel coordinates, scaled to mm. Layers:
  F.SilkS - both sail triangles, solid white
  F.Cu    - binary digits under the small sail silk (subtle emboss),
            and copper under the text opening (metallic text)
  F.Mask  - text-shaped openings over the copper text
"""

import subprocess
import sys
import uuid
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen


def find_font(pattern, family):
    """Resolve a font file via fontconfig; fail loudly on a wrong match."""
    got = subprocess.run(
        ["fc-match", "-f", "%{family}\t%{file}", pattern],
        capture_output=True, text=True, check=True,
    ).stdout
    got_family, path = got.split("\t")
    if family not in got_family:
        raise SystemExit(f"font '{pattern}' resolved to '{got_family}'; install {family}")
    return path


# Helvetica Bold clone, gently narrowed via TEXT_XSCALE to match the
# original's measured width-to-cap ratio
TEXT_FONT = find_font("TeX Gyre Heros:style=Bold", "TeX Gyre Heros")
TEXT_XSCALE = 0.95
# monospace with plain oval zero, like the original's binary texture
DIGIT_FONT = find_font("Liberation Mono:style=Bold", "Liberation Mono")

UUID_NS = uuid.uuid5(uuid.NAMESPACE_DNS, "gs-kicad-lib.ubc-sailbot")


class UuidSeq:
    """Deterministic per-footprint uuid stream so regeneration is diff-stable."""

    def __init__(self, name):
        self.name = name
        self.i = 0

    def __call__(self):
        self.i += 1
        return uuid.uuid5(UUID_NS, f"{self.name}:{self.i}")

# --- reference geometry, source-image pixels, y-down ---
# big sail base widened a touch vs the source (134->132, 223->227) so the
# edge clipping takes less out of the S and T
BIG_SAIL = [(140, 22), (227, 247), (132, 247)]
SMALL_SAIL = [(135, 90), (124, 247), (68, 247)]

# text metrics measured from the source image
UBC_X = 134           # keeps the source's 2px offset from the widened mast (was 136)
UBC_BASE = 225        # baseline y
UBC_CAP = 10          # cap height px
TEXT_DILATE = 0.12    # px outward offset on all text, for etch robustness
UBC_DILATE = 0.2      # px extra on UBC; original UBC is heavier than Heros Bold
SAIL_X = 127          # left of the mast; clipping eats part of the S like the original
SAIL_BASE = 244
SAIL_CAP = 17

# alternate layout: "UBC SAILBOT" as one line under the sails, sized to
# span the sail bbox exactly
ALT_GAP = 9           # px between the sail feet and the text cap top

# ENIG-plate layout: white silk plate, gold (copper + mask) sails and text,
# "UBC" over "SAILBOT" right-justified to the left of the sails
PLATE_CAP = 30        # px cap height for both text lines
PLATE_LINE_GAP = 0.32  # extra gap between the two baselines, as a fraction of cap
PLATE_TEXT_GAP = 16   # px between the text's right edge and the sail's left foot
PLATE_PAD = 22        # px equal padding from content bbox to the plate edge
PLATE_RADIUS_FRAC = 0.11  # corner radius as a fraction of plate height
PLATE_HEIGHT_MM = 12.0    # a little taller than the 10mm main variant
PLATE_DIGIT_ROWS = 8      # binary rows on the small sail in the plate variants

# binary digit grid inside the small sail
DIGIT_MARGIN = 1.5    # px inset from triangle edges
MIN_FEATURE_MM = 0.09  # typical 1oz outer copper minimum; thinner text fragments are dropped
BITS = "".join(f"{ord(c):08b}" for c in "UBC SAILBOT ")


# --- font outline extraction ---

class FlattenPen(BasePen):
    """Collect glyph contours as polylines, curves flattened."""

    def __init__(self, glyphset, steps=12):
        super().__init__(glyphset)
        self.steps = steps
        self.contours = []
        self._cur = None

    def _moveTo(self, pt):
        self._cur = [pt]

    def _lineTo(self, pt):
        self._cur.append(pt)

    def _curveToOne(self, p1, p2, p3):
        p0 = self._cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps
            mt = 1 - t
            x = mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0]
            y = mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]
            self._cur.append((x, y))

    def _qCurveToOne(self, p1, p2):
        p0 = self._cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps
            mt = 1 - t
            x = mt**2 * p0[0] + 2 * mt * t * p1[0] + t**2 * p2[0]
            y = mt**2 * p0[1] + 2 * mt * t * p1[1] + t**2 * p2[1]
            self._cur.append((x, y))

    def _closePath(self):
        self.contours.append(self._cur)
        self._cur = None


class Font:
    def __init__(self, path):
        self.font = TTFont(path)
        self.glyphset = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap()
        self.upem = self.font["head"].unitsPerEm
        self.cap = self.font["OS/2"].sCapHeight

    def glyph(self, ch):
        """Return (contours, advance) in font units, y-up."""
        name = self.cmap[ord(ch)]
        pen = FlattenPen(self.glyphset)
        g = self.glyphset[name]
        g.draw(pen)
        return pen.contours, g.width

    def text_contours(self, text, x, baseline, cap_px, xscale=1.0):
        """Layout text; returns list of per-glyph contour lists in px, y-down."""
        s = cap_px / self.cap
        out = []
        pen_x = x
        for ch in text:
            contours, adv = self.glyph(ch)
            if contours:
                out.append([
                    [(pen_x + px * s * xscale, baseline - py * s) for px, py in c]
                    for c in contours
                ])
            pen_x += adv * s * xscale
        return out, pen_x

    def text_width(self, text, cap_px):
        s = cap_px / self.cap
        return sum(self.glyph(ch)[1] for ch in text) * s


# --- digit grid ---

def inset_triangle(tri, d):
    """Shrink triangle by moving each edge inward by d."""
    import math
    cx = sum(p[0] for p in tri) / 3
    cy = sum(p[1] for p in tri) / 3
    lines = []
    for i in range(3):
        (x1, y1), (x2, y2) = tri[i], tri[(i + 1) % 3]
        nx, ny = y2 - y1, x1 - x2  # normal
        ln = math.hypot(nx, ny)
        nx, ny = nx / ln, ny / ln
        if nx * (cx - x1) + ny * (cy - y1) < 0:
            nx, ny = -nx, -ny  # point inward
        lines.append((x1 + nx * d, y1 + ny * d, x2 + nx * d, y2 + ny * d))

    def isect(l1, l2):
        x1, y1, x2, y2 = l1
        x3, y3, x4, y4 = l2
        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / den
        py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / den
        return (px, py)

    return [isect(lines[2], lines[0]), isect(lines[0], lines[1]), isect(lines[1], lines[2])]


def clip_to_tri(poly, tri):
    """Sutherland-Hodgman clip of a simple polygon to a triangle."""
    cx = sum(p[0] for p in tri) / 3
    cy = sum(p[1] for p in tri) / 3
    out = list(poly)
    for i in range(3):
        (x1, y1), (x2, y2) = tri[i], tri[(i + 1) % 3]
        nx, ny = y2 - y1, x1 - x2
        if nx * (cx - x1) + ny * (cy - y1) < 0:
            nx, ny = -nx, -ny

        def side(p):
            return nx * (p[0] - x1) + ny * (p[1] - y1)

        inp, out = out, []
        for j, cur in enumerate(inp):
            prev = inp[j - 1]
            sc, sp = side(cur), side(prev)
            if sc >= 0:
                if sp < 0:
                    t = sp / (sp - sc)
                    out.append((prev[0] + t * (cur[0] - prev[0]), prev[1] + t * (cur[1] - prev[1])))
                out.append(cur)
            elif sp >= 0:
                t = sp / (sp - sc)
                out.append((prev[0] + t * (cur[0] - prev[0]), prev[1] + t * (cur[1] - prev[1])))
        if not out:
            return []
    return out


def digit_grid(font, rows, tri, margin):
    """Rows of bits filling the triangle, glyphs clipped at the edges.

    Returns a flat list of simple (hole-free, pre-stitched) contours in px."""
    top = tri[0][1]
    bottom = tri[1][1]
    pitch = (bottom - top) / (rows + 0.5)
    cap = pitch * 0.85
    s = cap / font.cap
    adv = font.glyph("0")[1] * s
    right = max(p[0] for p in tri)
    left = min(p[0] for p in tri)
    clip_tri = inset_triangle(tri, margin)
    contours = []
    bit_i = 0
    n_cols = int((right - left) / adv) + 1
    for r in range(rows):
        base = bottom - margin - pitch * (rows - 1 - r)  # bottom row sits on the base
        for c in range(n_cols):
            gx = right - margin - adv * (n_cols - c)
            ch = BITS[bit_i % len(BITS)]
            bit_i += 1
            glyph = [
                [(gx + px * s, base - py * s) for px, py in cont]
                for cont in font.glyph(ch)[0]
            ]
            for simple in stitch_holes(glyph):
                clipped = clip_to_tri(simple, clip_tri)
                if len(clipped) >= 3 and abs(signed_area(clipped)) > 0.5:
                    contours.append([clipped])
    return contours


# --- contour utilities ---

def signed_area(c):
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(c, c[1:] + c[:1])) / 2


def mean_thickness(c):
    """4A/P: equals the stroke width for long thin shapes.

    Used to drop clip fragments too thin to etch reliably."""
    import math
    per = sum(math.hypot(x2 - x1, y2 - y1) for (x1, y1), (x2, y2) in zip(c, c[1:] + c[:1]))
    return 4 * abs(signed_area(c)) / per if per else 0.0


def densify(contour, max_seg, splice=()):
    """Subdivide edges so no segment exceeds max_seg.

    Points in splice that lie on an edge are inserted at their exact
    position, so a hole contour sharing that point can attach with a
    zero-length bridge (a true notch instead of a hole plus sliver)."""
    import math
    out = []
    n_edges = len(contour)
    for i in range(n_edges):
        a, b = contour[i], contour[(i + 1) % n_edges]
        ex, ey = b[0] - a[0], b[1] - a[1]
        ln2 = ex * ex + ey * ey
        on_edge = []
        for p in splice:
            t = ((p[0] - a[0]) * ex + (p[1] - a[1]) * ey) / ln2
            if 1e-9 < t < 1 - 1e-9:
                d = abs((p[0] - a[0]) * ey - (p[1] - a[1]) * ex) / math.sqrt(ln2)
                if d < 1e-6:
                    on_edge.append((t, p))
        n = max(1, int(math.sqrt(ln2) / max_seg))
        dens = [(j / n, (a[0] + ex * j / n, a[1] + ey * j / n)) for j in range(n)]
        out += [p for _, p in sorted(dens + on_edge)]
    return out


def notch(outline, hole, tri, tol=1e-6):
    """Subtract a hole that meets the outline along tri's edges.

    The hole's chord segments (those lying on a triangle edge) and the
    outline subsegments they shadow are dropped; the remaining pieces
    reconnect so the cut becomes part of the outline itself, with no
    coincident doubled path for the renderer to trip on. Returns
    (new outline, pockets), where pockets are regions the cut sealed off,
    or None if the hole never touches an edge. Assumes the hole's chord
    endpoints are already spliced into the outline (densify splice)."""
    import math

    def edge_t(p, a, b):
        """Param along a-b if p lies on that edge line, else None."""
        ex, ey = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(ex, ey)
        if abs((p[0] - a[0]) * ey - (p[1] - a[1]) * ex) / ln >= tol:
            return None
        return ((p[0] - a[0]) * ex + (p[1] - a[1]) * ey) / (ln * ln)

    def chord_span(p, q):
        """(edge index, t-interval) if segment p-q lies on a tri edge."""
        for i in range(3):
            a, b = tri[i], tri[(i + 1) % 3]
            tp, tq = edge_t(p, a, b), edge_t(q, a, b)
            if tp is not None and tq is not None:
                return i, min(tp, tq), max(tp, tq)
        return None

    h = list(hole)
    if (signed_area(h) > 0) == (signed_area(outline) > 0):
        h.reverse()
    spans = {}
    is_chord = []
    for i in range(len(h)):
        s = chord_span(h[i], h[(i + 1) % len(h)])
        is_chord.append(s is not None)
        if s is not None:
            spans.setdefault(s[0], []).append((s[1], s[2]))
    if not spans:
        return None

    def pieces(pts, drop):
        """Split a cyclic path into the polyline runs of kept segments."""
        m = len(pts)
        start = next(i for i in range(m) if drop[i])
        runs, cur = [], None
        for k in range(1, m + 1):
            i = (start + k) % m
            if drop[i]:
                if cur:
                    runs.append(cur)
                cur = None
            else:
                if cur is None:
                    cur = [pts[i]]
                cur.append(pts[(i + 1) % m])
        if cur:
            runs.append(cur)
        return runs

    shadowed = []
    for i in range(len(outline)):
        p, q = outline[i], outline[(i + 1) % len(outline)]
        mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        hit = False
        for e, ivals in spans.items():
            t = edge_t(mid, tri[e], tri[(e + 1) % 3])
            if t is not None and any(lo + 1e-12 < t < hi - 1e-12 for lo, hi in ivals):
                hit = True
                break
        shadowed.append(hit)

    # pieces meet only at chord endpoints, each of degree two, so they
    # reassemble into disjoint cycles: the notched outline plus pockets
    by_start = {pc[0]: pc for pc in pieces(h, is_chord) + pieces(outline, shadowed)}
    cycles = []
    while by_start:
        _, cur = by_start.popitem()
        cycle = cur[:-1]
        while cur[-1] in by_start:
            cur = by_start.pop(cur[-1])
            cycle += cur[:-1]
        cycles.append(cycle)
    cycles.sort(key=lambda c: -abs(signed_area(c)))
    return cycles[0], cycles[1:]


def prune_collinear(contour, tol=1e-7):
    """Drop vertices lying on the straight segment between their neighbors.

    Removes the densify() points that no bridge attached to; collinear
    vertices on a straight outline edge make KiCad's canvas triangulation
    emit degenerate slivers that render as hairline cracks. Vertices that
    appear more than once are bridge endpoints and are kept."""
    from collections import Counter
    counts = Counter(contour)
    n = len(contour)
    out = []
    for i, p in enumerate(contour):
        a, b = contour[i - 1], contour[(i + 1) % n]
        cross = (p[0] - a[0]) * (b[1] - a[1]) - (p[1] - a[1]) * (b[0] - a[0])
        between = (p[0] - a[0]) * (b[0] - p[0]) + (p[1] - a[1]) * (b[1] - p[1]) >= 0
        if counts[p] == 1 and abs(cross) < tol and between:
            continue
        out.append(p)
    return out


def stitch_holes(contours):
    """Merge holes into their outer contour with zero-width bridges.

    Assumes one outer contour (largest |area|) per glyph piece; robust enough
    for font glyphs. Returns list of hole-free contours."""
    if len(contours) <= 1:
        return contours
    cs = sorted(contours, key=lambda c: -abs(signed_area(c)))
    outer, holes = list(cs[0]), cs[1:]
    outer_ccw = signed_area(outer) > 0
    for hole in holes:
        h = list(hole)
        if (signed_area(h) > 0) == outer_ccw:
            h.reverse()
        # nearest vertex pair
        best = None
        for i, po in enumerate(outer):
            for j, ph in enumerate(h):
                d = (po[0] - ph[0]) ** 2 + (po[1] - ph[1]) ** 2
                if best is None or d < best[0]:
                    best = (d, i, j)
        _, i, j = best
        outer = outer[: i + 1] + h[j:] + h[: j + 1] + outer[i:]
    return [outer]


def rounded_rect(x0, y0, x1, y1, r, seg=10):
    """Filleted rectangle contour (px, y-down), corners as quarter arcs."""
    import math
    r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
    # (arc center, start angle) per corner, walking clockwise in y-down space
    corners = [
        ((x1 - r, y0 + r), -math.pi / 2),  # top-right
        ((x1 - r, y1 - r), 0.0),           # bottom-right
        ((x0 + r, y1 - r), math.pi / 2),   # bottom-left
        ((x0 + r, y0 + r), math.pi),       # top-left
    ]
    pts = []
    for (ax, ay), a0 in corners:
        for i in range(seg + 1):
            a = a0 + (math.pi / 2) * i / seg
            pts.append((ax + r * math.cos(a), ay + r * math.sin(a)))
    return pts


def transform(contours_list, scale, cx, cy):
    """px y-down -> mm centered at origin (KiCad y-down too)."""
    return [
        [[((x - cx) * scale, (y - cy) * scale) for x, y in c] for c in glyph]
        for glyph in contours_list
    ]


# --- build artwork for a given target height ---

def build_plate(text_font, digit_font, oneline=False, scheme="enig"):
    """Filleted badge plate with equal margins around the artwork. "UBC"/
    "SAILBOT" on two lines (or "UBC SAILBOT" on one), right-justified to the
    left of the sails and bottom-aligned to the sail feet. Three layer schemes:

      enig     - white silk plate; gold (copper + mask opening) sails and text.
      enig_num - as enig, plus binary numbers on the small sail formed by mask
                 opening with no copper, so they read as bare board in the gold.
      inverted - plate background and letter counters are a mask opening (exposed
                 board); sails and text are white silk over retained soldermask
                 (so fabs keep it); copper numbers embossed under the small sail."""
    cap = PLATE_CAP
    sail_left = min(x for tri in (BIG_SAIL, SMALL_SAIL) for x, _ in tri)
    sail_foot = max(y for tri in (BIG_SAIL, SMALL_SAIL) for _, y in tri)
    right = sail_left - PLATE_TEXT_GAP  # shared right edge of the text
    if oneline:
        w = text_font.text_width("UBC SAILBOT", cap) * TEXT_XSCALE
        text_glyphs, _ = text_font.text_contours("UBC SAILBOT", right - w, sail_foot, cap, TEXT_XSCALE)
    else:
        base_top = sail_foot - cap - PLATE_LINE_GAP * cap
        w_ubc = text_font.text_width("UBC", cap) * TEXT_XSCALE
        w_sail = text_font.text_width("SAILBOT", cap) * TEXT_XSCALE
        ubc_glyphs, _ = text_font.text_contours("UBC", right - w_ubc, base_top, cap, TEXT_XSCALE)
        sail_glyphs, _ = text_font.text_contours("SAILBOT", right - w_sail, sail_foot, cap, TEXT_XSCALE)
        text_glyphs = ubc_glyphs + sail_glyphs

    # letter outers become plate holes; counters come back as islands
    text_holes, islands = [], []
    for glyph in text_glyphs:
        cs = sorted(glyph, key=lambda c: -abs(signed_area(c)))
        text_holes.append(cs[0])
        islands += cs[1:]
    text_fills = [[s] for glyph in text_glyphs for s in stitch_holes(glyph)]

    # plate rectangle: the content bbox with equal padding on all four sides
    art_contours = [BIG_SAIL, SMALL_SAIL] + [c for g in text_glyphs for c in g]
    xs = [x for c in art_contours for x, _ in c]
    ys = [y for c in art_contours for _, y in c]
    x0, x1 = min(xs) - PLATE_PAD, max(xs) + PLATE_PAD
    y0, y1 = min(ys) - PLATE_PAD, max(ys) + PLATE_PAD
    plate_rect = rounded_rect(x0, y0, x1, y1, PLATE_RADIUS_FRAC * (y1 - y0))
    scale = PLATE_HEIGHT_MM / (y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

    def T(cl):
        return transform(cl, scale, cx, cy)

    # keepout outline: the plate grown by the 0.3mm fill margin, concentric so
    # the fillet radius grows to match the plate's rounded corners
    km = 0.3 / scale
    keepout_outline = T([[rounded_rect(
        x0 - km, y0 - km, x1 + km, y1 + km,
        PLATE_RADIUS_FRAC * (y1 - y0) + km)]])

    digits = digit_grid(digit_font, PLATE_DIGIT_ROWS, SMALL_SAIL, DIGIT_MARGIN)
    digit_holes = [c for gl in digits for c in gl]
    text_group = {"fill": T(text_fills), "outline": [], "stroke": 0.0}

    if scheme == "inverted":
        # exposed-board plate with white silk sails and text. The mask opens
        # over the plate background and the letter counters but stays CLOSED
        # under the silk (sails + letter strokes), so the silk lands on
        # soldermask; fabs like JLC strip silk printed over a bare mask
        # opening. Copper numbers sit under that retained mask under the
        # small-sail silk, fully embossed.
        mask_open = stitch_holes([plate_rect, BIG_SAIL, SMALL_SAIL] + text_holes)
        return {
            "svg_scheme": "inverted",
            "mask_only": T([mask_open] + [[isl] for isl in islands]),
            "silk": T([[BIG_SAIL], [SMALL_SAIL]] + text_fills),
            "copper": T(digits),
            "digits": [], "gold": [], "text": [], "text_layers": (),
            "plate": T([[plate_rect]]),
            "keepout": keepout_outline,
        }

    plate_silk = stitch_holes([plate_rect, BIG_SAIL, SMALL_SAIL] + text_holes)
    silk_src = [plate_silk] + [[isl] for isl in islands]
    art = {
        "svg_scheme": scheme,
        "silk": T(silk_src),
        "gold": T([[BIG_SAIL], [SMALL_SAIL]]),
        "text": [text_group],
        "text_layers": ("F.Cu", "F.Mask"),
        "digits": [],
        "keepout": keepout_outline,
    }
    if scheme == "enig_num":
        # small sail: mask stays fully open, copper is knocked out where the
        # numbers are, so the numbers read as bare board inside the gold
        small_cu = stitch_holes([SMALL_SAIL] + digit_holes)
        art["gold"] = T([[BIG_SAIL]])
        art["copper"] = T([small_cu])
        art["mask_only"] = T([[SMALL_SAIL]])
        art["bareboard_num"] = T(digits)
    return art


def build(height_mm, digit_rows, alt_text=False, silk_text=False, plate=False,
          oneline=False, scheme="enig", text=True):
    text_font = Font(TEXT_FONT)
    digit_font = Font(DIGIT_FONT)

    if plate:
        return build_plate(text_font, digit_font, oneline, scheme)

    if not text:
        groups_src = []
    elif alt_text:
        sail_x0 = min(x for tri in (BIG_SAIL, SMALL_SAIL) for x, _ in tri)
        sail_x1 = max(x for tri in (BIG_SAIL, SMALL_SAIL) for x, _ in tri)
        sail_y1 = max(y for tri in (BIG_SAIL, SMALL_SAIL) for _, y in tri)
        cap = (sail_x1 - sail_x0) / (text_font.text_width("UBC SAILBOT", 1.0) * TEXT_XSCALE)
        line_glyphs, _ = text_font.text_contours(
            "UBC SAILBOT", sail_x0, sail_y1 + ALT_GAP + cap, cap, TEXT_XSCALE)
        groups_src = [(line_glyphs, TEXT_DILATE)]
    else:
        ubc_glyphs, _ = text_font.text_contours("UBC", UBC_X, UBC_BASE, UBC_CAP, TEXT_XSCALE)
        sail_glyphs, _ = text_font.text_contours("SAILBOT", SAIL_X, SAIL_BASE, SAIL_CAP, TEXT_XSCALE)
        groups_src = [(ubc_glyphs, UBC_DILATE + TEXT_DILATE), (sail_glyphs, TEXT_DILATE)]

    # scale and centering follow the full artwork extents (sails plus text)
    xs = [x for tri in (BIG_SAIL, SMALL_SAIL) for x, _ in tri]
    ys = [y for tri in (BIG_SAIL, SMALL_SAIL) for _, y in tri]
    for glyphs, _ in groups_src:
        xs += [x for g in glyphs for c in g for x, _ in c]
        ys += [y for g in glyphs for c in g for _, y in c]
    scale = height_mm / (max(ys) - min(ys))
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2

    min_w = MIN_FEATURE_MM / scale  # px equivalent of the fab's min copper feature

    def clip_text(glyphs):
        """Clip glyphs at the sail's edge like the source artwork (cuts S and T).

        Returns (fill pieces, outline contours, punch contours, islands);
        outlines are stroked by KiCad to thicken the text with clean rounded
        joins, punch contours (letter outers) become holes in the big-sail
        silk so the text shows through, and islands (letter counters) are
        drawn back on top as separate silk polys so no stitching seam has to
        cross a letter."""
        fills, outlines, punch, islands = [], [], [], []
        for glyph in glyphs:
            kept = False
            for simple in stitch_holes(glyph):
                clipped = clip_to_tri(simple, BIG_SAIL)
                if len(clipped) >= 3 and mean_thickness(clipped) >= min_w:
                    kept = True
                    fills.append([clipped])
            if not kept:
                continue
            for contour in glyph:
                clipped = clip_to_tri(contour, BIG_SAIL)
                if len(clipped) >= 3 and abs(signed_area(clipped)) > 0.5:
                    outlines.append([clipped])
            cs = sorted(glyph, key=lambda c: -abs(signed_area(c)))
            p = clip_to_tri(cs[0], BIG_SAIL)
            if len(p) >= 3:
                punch.append(p)
            for counter in cs[1:]:
                c = clip_to_tri(counter, BIG_SAIL)
                if len(c) >= 3:
                    islands.append(c)
        return fills, outlines, punch, islands

    def plain_text(glyphs):
        """Unclipped text away from the sails; nothing to punch or island."""
        fills, outlines = [], []
        for glyph in glyphs:
            for simple in stitch_holes(glyph):
                fills.append([simple])
            for contour in glyph:
                outlines.append([contour])
        return fills, outlines, [], []

    prep = plain_text if alt_text else clip_text
    text_groups = []
    punch, islands = [], []
    for glyphs, dilate in groups_src:
        fills, outlines, grp_punch, grp_islands = prep(glyphs)
        punch += grp_punch
        islands += grp_islands
        text_groups.append({
            "fill": transform(fills, scale, cx, cy),
            "outline": transform(outlines, scale, cx, cy),
            "stroke": 2 * dilate * scale,  # dilate px per side -> stroke width mm
        })
    digits = digit_grid(digit_font, digit_rows, SMALL_SAIL, DIGIT_MARGIN) if digit_rows else []

    # big sail with the text punched out; letters cut by the sail edge (the
    # S and T) are subtracted from the outline itself so those cuts open
    # flush, interior letters are stitched in as holes, and the outline is
    # densified so their bridges attach nearby, then pruned back to just
    # the attachment points
    edge_pts = [v for c in punch for v in c]
    outline = densify(BIG_SAIL, 2.0, splice=edge_pts)
    interior, pockets = [], []
    for hole in punch:
        cut = notch(outline, hole, BIG_SAIL)
        if cut is None:
            interior.append(hole)
        else:
            outline, sealed = cut
            pockets += sealed
    big_sail = [prune_collinear(c) for c in stitch_holes([outline] + interior)]

    art = {
        "svg_scheme": "normal",
        "silk": transform([big_sail, [SMALL_SAIL]] + [[c] for c in pockets + islands], scale, cx, cy),
        "text": text_groups,
        "text_layers": ("F.SilkS",) if silk_text else ("F.Cu", "F.Mask"),
        "digits": transform(digits, scale, cx, cy),
    }
    return art


# --- SVG preview ---

def svg_path(glyph):
    d = ""
    for c in glyph:
        d += "M " + " L ".join(f"{x:.3f} {y:.3f}" for x, y in c) + " Z "
    return d.strip()


SILK = "#f0ede5"   # white silkscreen ink
GOLD = "#c9a44c"   # ENIG-plated exposed copper
BARE = "#b7a15c"   # exposed laminate (mask open, no copper)
BLUE = "#1b4488"   # soldermask
EMBOSS = "#d8d2c2"  # copper under mask under silk, faint tone


def write_svg(art, path, width_extra=2):
    keys = ("silk", "gold", "copper", "mask_only")
    xs = [x for k in keys for g in art.get(k, []) for c in g for x, _ in c]
    ys = [y for k in keys for g in art.get(k, []) for c in g for _, y in c]
    for grp in art["text"]:
        xs += [x for g in grp["fill"] for c in g for x, _ in c]
        ys += [y for g in grp["fill"] for c in g for _, y in c]
    x0, x1 = min(xs) - width_extra, max(xs) + width_extra
    y0, y1 = min(ys) - width_extra, max(ys) + width_extra
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0} {y0} {x1-x0} {y1-y0}" width="{(x1-x0)*40}" height="{(y1-y0)*40}">',
        f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" fill="{BLUE}"/>',
    ]

    def draw(glyphs, fill, evenodd=False):
        rule = ' fill-rule="evenodd"' if evenodd else ""
        for g in glyphs:
            parts.append(f'<path d="{svg_path(g)}" fill="{fill}"{rule}/>')

    scheme = art.get("svg_scheme", "normal")
    if scheme == "inverted":
        # exposed-board plate, white silk sails+text, copper embossed under the
        # small-sail silk (faint relief tone drawn over the ink, like the emboss)
        draw(art["plate"], BARE)
        draw(art["silk"], SILK)
        draw(art["copper"], EMBOSS, evenodd=True)
    elif scheme == "enig_num":
        draw(art["silk"], SILK)
        draw(art["gold"], GOLD)             # big sail
        draw(art["mask_only"], GOLD)        # small sail, solid gold
        draw(art["bareboard_num"], BARE, evenodd=True)  # bare-board numbers
        draw([g for grp in art["text"] for g in grp["fill"]], GOLD, evenodd=True)
    else:
        draw(art["silk"], SILK)
        draw(art.get("gold", []), GOLD)
        draw(art["digits"], EMBOSS, evenodd=True)
        tcol = SILK if "F.SilkS" in art["text_layers"] else GOLD
        for grp in art["text"]:
            draw(grp["fill"], tcol, evenodd=True)
            if grp["stroke"] > 0:
                for g in grp["outline"]:
                    parts.append(
                        f'<path d="{svg_path(g)}" fill="none" stroke="{tcol}" '
                        f'stroke-width="{grp["stroke"]:.4f}" stroke-linejoin="round"/>'
                    )
    parts.append("</svg>")
    with open(path, "w") as f:
        f.write("\n".join(parts))


# --- KiCad footprint ---

def fp_poly(contour, layer, uid, fill=True, stroke_w=0.0):
    # drop zero-length segments (zero-length splice bridges, rounding dupes)
    rounded = [(round(x, 4), round(y, 4)) for x, y in contour]
    rounded = [p for i, p in enumerate(rounded) if p != rounded[i - 1]]
    pts = " ".join(f"(xy {x:.4f} {y:.4f})" for x, y in rounded)
    return f"""\t(fp_poly
\t\t(pts
\t\t\t{pts}
\t\t)
\t\t(stroke
\t\t\t(width {round(stroke_w, 4):g})
\t\t\t(type solid)
\t\t)
\t\t(fill {"yes" if fill else "no"})
\t\t(layer "{layer}")
\t\t(uuid "{uid}")
\t)"""


def write_footprint(art, name, descr, path):
    uid = UuidSeq(name)
    polys = []
    for g in art["silk"]:
        for c in stitch_holes(g):
            polys.append(fp_poly(c, "F.SilkS", uid()))
    for g in art["digits"]:
        for c in stitch_holes(g):
            polys.append(fp_poly(c, "F.Cu", uid()))
    # gold shapes (plate variant sails): copper plus a matching mask opening
    for g in art.get("gold", []):
        for c in stitch_holes(g):
            for layer in ("F.Cu", "F.Mask"):
                polys.append(fp_poly(c, layer, uid()))
    # copper-only (exposed numbers, or the holed small sail) and mask-only
    # (the exposed plate, or a full mask opening over the small sail)
    for g in art.get("copper", []):
        for c in stitch_holes(g):
            polys.append(fp_poly(c, "F.Cu", uid()))
    for g in art.get("mask_only", []):
        for c in stitch_holes(g):
            polys.append(fp_poly(c, "F.Mask", uid()))
    # text: filled letters plus a stroked outline for weight, on copper and
    # as a matching mask opening; the silk punch above reveals it
    for grp in art["text"]:
        for layer in art["text_layers"]:
            for g in grp["fill"]:
                for c in g:
                    polys.append(fp_poly(c, layer, uid()))
            if grp["stroke"] > 0:
                for g in grp["outline"]:
                    for c in g:
                        polys.append(fp_poly(c, layer, uid(), fill=False, stroke_w=grp["stroke"]))
    # keepout over the artwork so pours, tracks, and vias can't disturb it;
    # silk-only footprints have no copper to protect, so they get none
    xs = [x for key in ("silk", "gold", "copper", "mask_only")
          for g in art.get(key, []) for c in g for x, _ in c]
    ys = [y for key in ("silk", "gold", "copper", "mask_only")
          for g in art.get(key, []) for c in g for _, y in c]
    for grp in art["text"]:
        xs += [x for g in grp["fill"] for c in g for x, _ in c]
        ys += [y for g in grp["fill"] for c in g for _, y in c]
    has_conductor = bool(art["digits"] or art.get("gold") or art.get("copper")
                         or art.get("mask_only")) or any(
        grp["fill"] and any(l != "F.SilkS" for l in art["text_layers"])
        for grp in art["text"])
    if has_conductor:
        if art.get("keepout"):
            # plate variants: follow the plate's rounded rectangle
            outline = [(round(x, 4), round(y, 4)) for x, y in art["keepout"][0][0]]
            outline = [p for i, p in enumerate(outline) if p != outline[i - 1]]
            pts = " ".join(f"(xy {x:.4f} {y:.4f})" for x, y in outline)
        else:
            m = 0.3
            kx0, kx1, ky0, ky1 = min(xs) - m, max(xs) + m, min(ys) - m, max(ys) + m
            pts = (f"(xy {kx0:.4f} {ky0:.4f}) (xy {kx1:.4f} {ky0:.4f}) "
                   f"(xy {kx1:.4f} {ky1:.4f}) (xy {kx0:.4f} {ky1:.4f})")
        keepout = f"""\t(zone
\t\t(net 0)
\t\t(net_name "")
\t\t(layer "F.Cu")
\t\t(uuid "{uid()}")
\t\t(name "logo_keepout")
\t\t(hatch edge 0.5)
\t\t(connect_pads
\t\t\t(clearance 0)
\t\t)
\t\t(min_thickness 0.25)
\t\t(filled_areas_thickness no)
\t\t(keepout
\t\t\t(tracks not_allowed)
\t\t\t(vias not_allowed)
\t\t\t(pads allowed)
\t\t\t(copperpour not_allowed)
\t\t\t(footprints allowed)
\t\t)
\t\t(fill
\t\t\t(thermal_gap 0.5)
\t\t\t(thermal_bridge_width 0.5)
\t\t)
\t\t(polygon
\t\t\t(pts
\t\t\t\t{pts}
\t\t\t)
\t\t)
\t)"""
        polys.append(keepout)
    body = "\n".join(polys)
    ref_y = min(ys) - 1
    content = f"""(footprint "{name}"
\t(version 20241229)
\t(generator "pcbnew")
\t(generator_version "9.0")
\t(layer "F.Cu")
\t(property "Reference" "REF**"
\t\t(at 0 {ref_y:.2f} 0)
\t\t(unlocked yes)
\t\t(layer "F.SilkS")
\t\t(hide yes)
\t\t(uuid "{uid()}")
\t\t(effects
\t\t\t(font
\t\t\t\t(size 1 1)
\t\t\t\t(thickness 0.1)
\t\t\t)
\t\t)
\t)
\t(property "Value" ""
\t\t(at 0 {-ref_y:.2f} 0)
\t\t(unlocked yes)
\t\t(layer "F.Fab")
\t\t(uuid "{uid()}")
\t\t(effects
\t\t\t(font
\t\t\t\t(size 1 1)
\t\t\t\t(thickness 0.15)
\t\t\t)
\t\t)
\t)
\t(property "Datasheet" ""
\t\t(at 0 0 0)
\t\t(unlocked yes)
\t\t(layer "F.Fab")
\t\t(hide yes)
\t\t(uuid "{uid()}")
\t\t(effects
\t\t\t(font
\t\t\t\t(size 1 1)
\t\t\t\t(thickness 0.15)
\t\t\t)
\t\t)
\t)
\t(property "Description" "{descr}"
\t\t(at 0 0 0)
\t\t(unlocked yes)
\t\t(layer "F.Fab")
\t\t(hide yes)
\t\t(uuid "{uid()}")
\t\t(effects
\t\t\t(font
\t\t\t\t(size 1 1)
\t\t\t\t(thickness 0.15)
\t\t\t)
\t\t)
\t)
\t(attr smd)
{body}
\t(embedded_fonts no)
)
"""
    with open(path, "w") as f:
        f.write(content)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = args[0] if args else "."
    for tag, descr, opts in [
        ("", "UBC Sailbot logo, 10mm", dict(height_mm=10.0, digit_rows=11)),
        ("_Small", "UBC Sailbot logo, small, 6mm", dict(height_mm=6.0, digit_rows=6)),
        ("_Alt", "UBC Sailbot logo, text below the sails, 10mm",
         dict(height_mm=10.0, digit_rows=11, alt_text=True)),
        ("_Plain", "UBC Sailbot logo, silkscreen only, 10mm",
         dict(height_mm=10.0, digit_rows=0, alt_text=True, silk_text=True)),
        ("_Large", "UBC Sailbot logo, large silkscreen sails, embossed copper, no text, 15mm",
         dict(height_mm=15.0, digit_rows=11, text=False)),
        ("_Huge", "UBC Sailbot logo, silkscreen sails only, no copper, 40mm",
         dict(height_mm=40.0, digit_rows=0, text=False)),
        ("_Enig", "UBC Sailbot logo, gold on white plate, 12mm",
         dict(height_mm=PLATE_HEIGHT_MM, digit_rows=0, plate=True)),
        ("_Enig_Line", "UBC Sailbot logo, gold on white plate, one line, 12mm",
         dict(height_mm=PLATE_HEIGHT_MM, digit_rows=0, plate=True, oneline=True)),
        ("_Enig_Num", "UBC Sailbot logo, gold plate, bare-board numbers, 12mm",
         dict(height_mm=PLATE_HEIGHT_MM, digit_rows=0, plate=True, scheme="enig_num")),
        ("_Silk", "UBC Sailbot logo, silk on exposed-board plate, 12mm",
         dict(height_mm=PLATE_HEIGHT_MM, digit_rows=0, plate=True, scheme="inverted")),
        ("_Silk_Line", "UBC Sailbot logo, silk on exposed-board plate, one line, 12mm",
         dict(height_mm=PLATE_HEIGHT_MM, digit_rows=0, plate=True, scheme="inverted", oneline=True)),
    ]:
        art = build(**opts)
        if "--svg" in sys.argv:
            write_svg(art, f"{out}/UBC_Sailbot_Logo{tag}.svg")
        write_footprint(art, f"UBC_Sailbot_Logo{tag}", descr,
                        f"{out}/UBC_Sailbot_Logo{tag}.kicad_mod")
        print(f"UBC_Sailbot_Logo{tag}: {opts['height_mm']}mm tall")
