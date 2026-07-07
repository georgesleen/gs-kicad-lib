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
BIG_SAIL = [(140, 22), (223, 247), (134, 247)]
SMALL_SAIL = [(135, 90), (124, 247), (68, 247)]
CONTENT = (68, 22, 223, 247)  # bbox of all artwork

# text metrics measured from the source image
UBC_X = 136
UBC_BASE = 225        # baseline y
UBC_CAP = 10          # cap height px
TEXT_DILATE = 0.12    # px outward offset on all text, for etch robustness
UBC_DILATE = 0.2      # px extra on UBC; original UBC is heavier than Heros Bold
SAIL_X = 127          # well left of the mast; clipping eats half the S like the original
SAIL_BASE = 244
SAIL_CAP = 17

# binary digit grid inside the small sail
DIGIT_MARGIN = 1.5    # px inset from triangle edges
SILK_PEN_MM = 0.01    # outline pen on silk polys; paints over the zero-width
                      # stitching seams the editor canvas otherwise shows
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


def densify(contour, max_seg):
    """Subdivide edges so no segment exceeds max_seg."""
    import math
    out = []
    for (x1, y1), (x2, y2) in zip(contour, contour[1:] + contour[:1]):
        n = max(1, int(math.hypot(x2 - x1, y2 - y1) / max_seg))
        out += [(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n) for i in range(n)]
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


def transform(contours_list, scale, cx, cy):
    """px y-down -> mm centered at origin (KiCad y-down too)."""
    return [
        [[((x - cx) * scale, (y - cy) * scale) for x, y in c] for c in glyph]
        for glyph in contours_list
    ]


# --- build artwork for a given target height ---

def build(height_mm, digit_rows):
    text_font = Font(TEXT_FONT)
    digit_font = Font(DIGIT_FONT)
    x0, y0, x1, y1 = CONTENT
    scale = height_mm / (y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

    min_w = MIN_FEATURE_MM / scale  # px equivalent of the fab's min copper feature

    def clip_text(glyphs):
        """Clip glyphs at the sail's edge like the source artwork (cuts S and T).

        Returns (fill pieces, outline contours, punch contours, islands);
        outlines are stroked by KiCad to thicken the text with clean rounded
        joins, punch contours (letter outers) become holes in the big-sail
        silk so the text shows through, and islands (letter counters) are
        drawn back on top as separate silk polys so no stitching seam has to
        cross a letter. The punch is clipped a hair inside the sail so its
        holes never sit exactly on the silk outline."""
        fills, outlines, punch, islands = [], [], [], []
        punch_tri = inset_triangle(BIG_SAIL, 0.02)
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
            p = clip_to_tri(cs[0], punch_tri)
            if len(p) >= 3:
                punch.append(p)
            for counter in cs[1:]:
                c = clip_to_tri(counter, BIG_SAIL)
                if len(c) >= 3:
                    islands.append(c)
        return fills, outlines, punch, islands

    ubc_glyphs, _ = text_font.text_contours("UBC", UBC_X, UBC_BASE, UBC_CAP, TEXT_XSCALE)
    sail_glyphs, _ = text_font.text_contours("SAILBOT", SAIL_X, SAIL_BASE, SAIL_CAP, TEXT_XSCALE)
    text_groups = []
    punch, islands = [], []
    for glyphs, dilate in ((ubc_glyphs, UBC_DILATE + TEXT_DILATE), (sail_glyphs, TEXT_DILATE)):
        fills, outlines, grp_punch, grp_islands = clip_text(glyphs)
        punch += grp_punch
        islands += grp_islands
        text_groups.append({
            "fill": transform(fills, scale, cx, cy),
            "outline": transform(outlines, scale, cx, cy),
            "stroke": 2 * dilate * scale,  # dilate px per side -> stroke width mm
        })
    digits = digit_grid(digit_font, digit_rows, SMALL_SAIL, DIGIT_MARGIN)

    # big sail with the text punched out; edges densified so hole bridges
    # can attach nearby instead of stretching to a far triangle corner
    big_sail = stitch_holes([densify(BIG_SAIL, 2.0)] + punch)

    art = {
        "silk": transform([big_sail, [SMALL_SAIL]] + [[c] for c in islands], scale, cx, cy),
        "text": text_groups,
        "digits": transform(digits, scale, cx, cy),
    }
    return art


# --- SVG preview ---

def svg_path(glyph):
    d = ""
    for c in glyph:
        d += "M " + " L ".join(f"{x:.3f} {y:.3f}" for x, y in c) + " Z "
    return d.strip()


def write_svg(art, path, width_extra=2):
    xs = [x for g in art["silk"] for c in g for x, _ in c]
    ys = [y for g in art["silk"] for c in g for _, y in c]
    x0, x1 = min(xs) - width_extra, max(xs) + width_extra
    y0, y1 = min(ys) - width_extra, max(ys) + width_extra
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0} {y0} {x1-x0} {y1-y0}" width="{(x1-x0)*40}" height="{(y1-y0)*40}">',
        f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" fill="#1b4488"/>',
    ]
    for g in art["silk"]:
        parts.append(f'<path d="{svg_path(g)}" fill="#f0ede5"/>')
    # digits: copper under mask under silk -> faint emboss
    for g in art["digits"]:
        parts.append(f'<path d="{svg_path(g)}" fill="#d8d2c2" fill-rule="evenodd"/>')
    # text: exposed copper (ENIG gold), fill plus stroked outline for weight
    for grp in art["text"]:
        for g in grp["fill"]:
            parts.append(f'<path d="{svg_path(g)}" fill="#c9a44c" fill-rule="evenodd"/>')
        for g in grp["outline"]:
            parts.append(
                f'<path d="{svg_path(g)}" fill="none" stroke="#c9a44c" '
                f'stroke-width="{grp["stroke"]:.4f}" stroke-linejoin="round"/>'
            )
    parts.append("</svg>")
    with open(path, "w") as f:
        f.write("\n".join(parts))


# --- KiCad footprint ---

def fp_poly(contour, layer, uid, fill=True, stroke_w=0.0):
    pts = " ".join(f"(xy {x:.4f} {y:.4f})" for x, y in contour)
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
            polys.append(fp_poly(c, "F.SilkS", uid(), stroke_w=SILK_PEN_MM))
    for g in art["digits"]:
        for c in stitch_holes(g):
            polys.append(fp_poly(c, "F.Cu", uid()))
    # text: filled letters plus a stroked outline for weight, on copper and
    # as a matching mask opening; the silk punch above reveals it
    for grp in art["text"]:
        for layer in ("F.Cu", "F.Mask"):
            for g in grp["fill"]:
                for c in g:
                    polys.append(fp_poly(c, layer, uid()))
            for g in grp["outline"]:
                for c in g:
                    polys.append(fp_poly(c, layer, uid(), fill=False, stroke_w=grp["stroke"]))
    # keepout over the artwork so pours, tracks, and vias can't disturb it
    xs = [x for g in art["silk"] for c in g for x, _ in c]
    ys = [y for g in art["silk"] for c in g for _, y in c]
    m = 0.3
    kx0, kx1, ky0, ky1 = min(xs) - m, max(xs) + m, min(ys) - m, max(ys) + m
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
\t\t\t\t(xy {kx0:.4f} {ky0:.4f}) (xy {kx1:.4f} {ky0:.4f}) (xy {kx1:.4f} {ky1:.4f}) (xy {kx0:.4f} {ky1:.4f})
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
    for tag, height, rows, descr in [
        ("", 10.0, 11, "UBC Sailbot logo, 10mm"),
        ("_Small", 6.0, 6, "UBC Sailbot logo, small, 6mm"),
    ]:
        art = build(height, rows)
        if "--svg" in sys.argv:
            write_svg(art, f"{out}/UBC_Sailbot_Logo{tag}.svg")
        write_footprint(art, f"UBC_Sailbot_Logo{tag}", descr,
                        f"{out}/UBC_Sailbot_Logo{tag}.kicad_mod")
        print(f"UBC_Sailbot_Logo{tag}: {height}mm tall, {rows} digit rows")
