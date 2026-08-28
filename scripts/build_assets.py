#!/usr/bin/env python3
"""Build the SVG assets referenced by README.md.

Static assets (run locally, commit the output):

    uv run --with fonttools --with brotli scripts/build_assets.py

Live stats card (run by .github/workflows/credits.yml and published to the
`output` branch, never committed to main):

    uv run --with fonttools --with brotli scripts/build_assets.py --stats stats.json --out dist

Steps: download Jost (SIL OFL 1.1) once into scripts/.cache/, instance the
variable font at the weights we use, subset it to Basic Latin + Turkish glyphs
and embed it as base64 WOFF2 so the SVGs render identically everywhere.

GitHub serves README images through camo as a plain <img>, so the SVGs must be
self-contained: no external fonts, no scripts, CSS animations only. Media
queries inside an SVG evaluate against the rendered <img> width, which is how
the phone layouts switch on without a second file.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import re
import urllib.request
from pathlib import Path
from string import Template
from typing import Dict, List, Tuple
from xml.sax.saxutils import escape

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
CACHE = SCRIPT_DIR / ".cache"
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/jost/Jost%5Bwght%5D.ttf"
FONT_STACK = '"Jost","Futura","Avenir Next","Helvetica Neue",Arial,sans-serif'

# --- Content -----------------------------------------------------------------
TITLE = "HALİL MERT ÖĞÜT"
SUBTITLE = "FULL STACK DEVELOPER"
FOOTER_LEFT = "EST. MMXXII"  # GitHub account created March 2022
FOOTER_CENTER = "2.39 : 1"  # the frame really is cinemascope
FOOTER_RIGHT = "@HALILMERTOGUT"
COUNTDOWN = ["3", "2"]  # film leader numbers before the cut to the title
CREDITS_HEADER = "STARRING"
CREDITS: List[Tuple[str, str]] = [
    ("FRONTEND", "TypeScript · Next.js · React · Tailwind CSS"),
    ("BACKEND", "Django · FastAPI · Node.js"),
    ("SYSTEMS", "Rust · Docker · Celery"),
    ("DATA", "PostgreSQL · MySQL · PostHog"),
]
STATS_HEADER = "NOW IN PRODUCTION"

# Basic Latin + Turkish letters + the typographic marks we use.
GLYPHS = set(range(0x20, 0x7F)) | {ord(c) for c in "·ÇÖÜçöüĞğİıŞş–—•"}

# Browsers pause <img> SVG animations while off-screen, so the cards start
# almost immediately once scrolled into view instead of syncing with the banner.
ROW_DELAY = 0.15
ROW_STAGGER = 0.12

# Rendered <img> width (CSS px) below which the phone layout switches on.
TITLE_NARROW = 560
CARD_NARROW = 480
CARD_W = 640
CARD_MARGIN = 24

THEMES: Dict[str, Dict[str, str]] = {
    "dark": {"name": "#e6edf3", "label": "#7d8590"},
    "light": {"name": "#1f2328", "label": "#656d76"},
}


# --- Fonts -------------------------------------------------------------------
def variable_font() -> bytes:
    CACHE.mkdir(exist_ok=True)
    path = CACHE / "Jost[wght].ttf"
    if not path.exists():
        print(f"downloading {FONT_URL}")
        with urllib.request.urlopen(FONT_URL, timeout=60) as resp:
            path.write_bytes(resp.read())
    return path.read_bytes()


def build_face(vf: bytes, weight: int) -> Tuple[TTFont, str]:
    """Static instance at `weight`, subset to GLYPHS -> (font, base64 woff2)."""
    font = instancer.instantiateVariableFont(TTFont(io.BytesIO(vf)), {"wght": weight})
    options = subset.Options()
    options.hinting = False
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=GLYPHS)
    subsetter.subset(font)
    font.flavor = "woff2"
    buf = io.BytesIO()
    font.save(buf)
    return font, base64.b64encode(buf.getvalue()).decode("ascii")


class Metrics:
    """Text width in SVG user units, the way browsers lay out <text>."""

    def __init__(self, font: TTFont) -> None:
        self.cmap = font.getBestCmap()
        self.hmtx = font["hmtx"]
        self.upem = font["head"].unitsPerEm

    def width(self, text: str, size: float, tracking_em: float = 0.0) -> float:
        missing = sorted({c for c in text if ord(c) not in self.cmap})
        if missing:
            raise SystemExit(f"glyphs missing from subset: {missing!r}")
        advance = sum(self.hmtx[self.cmap[ord(c)]][0] for c in text) * size / self.upem
        # Browsers add letter-spacing after every glyph, including the last one.
        return advance + tracking_em * size * len(text)

    def fits(self, text: str, size: float, tracking_em: float, max_width: float, what: str) -> None:
        width = self.width(text, size, tracking_em)
        if width > max_width:
            raise SystemExit(f"{what} too wide: {width:.0f} > {max_width:.0f} ({text!r})")


def num(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def centered_x(cx: float, size: float, tracking_em: float) -> str:
    """text-anchor=middle centers the trailing tracking too; shift back by half of it."""
    return num(cx + tracking_em * size / 2)


def row(delay: float, inner: str, extra_class: str = "") -> str:
    cls = f"row {extra_class}".strip()
    return f'<g class="{cls}" style="animation-delay:{delay:.2f}s">{inner}</g>'


FONT_FACE_400 = '@font-face{font-family:"Jost";font-weight:400;src:url(data:font/woff2;base64,$f400) format("woff2")}'
CARD_STYLE = (
    'text{font-family:$fonts;text-rendering:geometricPrecision}'
    '.row{animation:rise 1.1s cubic-bezier(.16,1,.3,1) both}'
    '@keyframes rise{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}'
    '.m{display:none}'
    '@media (max-width:${narrow}px){.d{display:none}.m{display:inline}}'
    '@media (prefers-reduced-motion:reduce){.row{animation:none}}'
)


# --- Title card --------------------------------------------------------------
TITLE_SVG = Template(
    """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 $w $h" width="$w" height="$h" role="img" aria-labelledby="title-desc">
<title id="title-desc">$aria</title>
<style>
@font-face{font-family:"Jost";font-weight:400;src:url(data:font/woff2;base64,$f400) format("woff2")}
@font-face{font-family:"Jost";font-weight:500;src:url(data:font/woff2;base64,$f500) format("woff2")}
text{font-family:$fonts;text-rendering:geometricPrecision}
.leader{opacity:0;animation:hold ${leader_dur}s linear 0s}
.leader line{stroke:#232323;stroke-width:1}
.leader circle{fill:none;stroke:#3d3d3d;stroke-width:1}
.leader .field{fill:#262626;stroke:none}
.leader .sweep{stroke:#0b0b0b;stroke-width:${sweep_w};stroke-dasharray:1;animation:sweep ${count_dur}s linear 0s ${count_n}}
.count{font-size:${count_size}px;font-weight:500;fill:#f3f3f3;opacity:0}
.scene{animation:flicker .8s steps(1,end) ${cut}s both}
.title{font-size:${title_size}px;font-weight:500;letter-spacing:${title_ls}em;fill:#f3f3f3;animation:title 1.9s cubic-bezier(.16,1,.3,1) ${t_title}s both}
.rule{stroke:#3a3a3a;stroke-width:1;transform-origin:${cx}px ${rule_y}px;animation:rule 1.5s cubic-bezier(.16,1,.3,1) ${t_rule}s both}
.subtitle{font-size:${sub_size}px;letter-spacing:${sub_ls}em;fill:#9b9b9b;animation:subtitle 1.7s cubic-bezier(.16,1,.3,1) ${t_sub}s both}
.footer{font-size:${foot_size}px;letter-spacing:${foot_ls}em;fill:#5a5a5a;animation:fade 1.4s ease-out ${t_foot}s both}
@media (max-width:${narrow}px){.title{font-size:${title_size_m}px}.subtitle{font-size:${sub_size_m}px}.footer{font-size:${foot_size_m}px}}
@keyframes hold{from{opacity:1}to{opacity:1}}
@keyframes sweep{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}
@keyframes flicker{0%{opacity:.45}14%{opacity:1}28%{opacity:.6}42%{opacity:1}58%{opacity:.8}72%{opacity:1}100%{opacity:1}}
@keyframes title{from{opacity:0;letter-spacing:${title_ls_from}em}to{opacity:1;letter-spacing:${title_ls}em}}
@keyframes rule{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@keyframes subtitle{from{opacity:0;letter-spacing:${sub_ls_from}em}to{opacity:1;letter-spacing:${sub_ls}em}}
@keyframes fade{from{opacity:0}to{opacity:1}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
</style>
<defs>
<radialGradient id="glow" cx="50%" cy="46%" r="62%"><stop offset="0" stop-color="#191919"/><stop offset="1" stop-color="#060606"/></radialGradient>
<filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency=".8" numOctaves="2" seed="7" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter>
<clipPath id="frame"><rect width="$w" height="$h" rx="14"/></clipPath>
</defs>
<g clip-path="url(#frame)">
<rect width="$w" height="$h" fill="url(#glow)"/>
<rect width="$w" height="$h" filter="url(#grain)" opacity=".06"/>
</g>
<rect x=".5" y=".5" width="$w1" height="$h1" rx="13.5" fill="none" stroke="#1f1f1f"/>
<g class="leader">
<line x1="0" y1="$cy" x2="$w" y2="$cy"/><line x1="$cx" y1="0" x2="$cx" y2="$h"/>
<circle cx="$cx" cy="$cy" r="$r_outer"/><circle cx="$cx" cy="$cy" r="$r_inner"/>
<circle class="field" cx="$cx" cy="$cy" r="$r_inner"/>
<circle class="sweep" cx="$cx" cy="$cy" r="$r_sweep" fill="none" pathLength="1" transform="rotate(-90 $cx $cy)"/>
$counts
</g>
<g class="scene">
<text class="title" x="$title_x" y="$title_y" text-anchor="middle">$title</text>
<line class="rule" x1="$rule_x1" y1="$rule_y" x2="$rule_x2" y2="$rule_y"/>
<text class="subtitle" x="$sub_x" y="$sub_y" text-anchor="middle">$subtitle</text>
<text class="footer" x="$foot_lx" y="$foot_y">$footer_left</text>
<text class="footer" x="$foot_cx" y="$foot_y" text-anchor="middle">$footer_center</text>
<text class="footer" x="$foot_rx" y="$foot_y" text-anchor="end">$footer_right</text>
</g>
</svg>
"""
)


def render_title(f400: str, f500: str, m400: Metrics, m500: Metrics) -> str:
    w, h = 908, 380  # 2.39:1, cinemascope
    cx, cy = w / 2, h / 2
    title_size, title_ls, title_ls_from = 46, 0.28, 0.6
    sub_size, sub_ls, sub_ls_from = 13.5, 0.55, 0.95
    foot_size, foot_ls = 10.5, 0.3
    title_size_m, sub_size_m, foot_size_m = 60, 22, 17  # phone: same frame, bigger type
    rule_y, margin = 212, 36

    # Film leader: one sweep per number, hard cut to black, then the title.
    count_dur, count_size = 0.8, 64
    leader_dur = count_dur * len(COUNTDOWN)
    cut = leader_dur + 0.15
    r_outer, r_inner = 92, 66
    r_sweep = r_inner / 2  # a circle stroked with width == diameter fills a disc
    counts = "\n".join(
        f'<text class="count" x="{num(cx)}" y="{num(cy + count_size * 0.36)}" text-anchor="middle" '
        f'style="animation:hold {count_dur}s linear {i * count_dur:.2f}s">{escape(n)}</text>'
        for i, n in enumerate(COUNTDOWN)
    )

    m500.fits(TITLE, title_size, title_ls, w * 0.76, "title")
    m500.fits(TITLE, title_size_m, title_ls, w - 2 * margin, "title (phone)")
    m400.fits(SUBTITLE, sub_size_m, sub_ls, w - 2 * margin, "subtitle (phone)")
    footer_w = sum(m400.width(t, foot_size_m, foot_ls) for t in (FOOTER_LEFT, FOOTER_CENTER, FOOTER_RIGHT))
    if footer_w > w - 2 * margin - 2 * 40:
        raise SystemExit(f"footer (phone) too wide: {footer_w:.0f}")
    print(f"title width {m500.width(TITLE, title_size, title_ls):.0f}/{w}, leader {leader_dur:.1f}s, title at {cut + 0.05:.2f}s")

    return TITLE_SVG.substitute(
        w=w, h=h, w1=w - 1, h1=h - 1, cx=num(cx), cy=num(cy), fonts=FONT_STACK, f400=f400, f500=f500,
        aria=escape(f"{TITLE} — {SUBTITLE}"),
        title=escape(TITLE), subtitle=escape(SUBTITLE),
        footer_left=escape(FOOTER_LEFT), footer_center=escape(FOOTER_CENTER), footer_right=escape(FOOTER_RIGHT),
        leader_dur=num(leader_dur), count_dur=num(count_dur), count_n=len(COUNTDOWN), count_size=count_size,
        r_outer=r_outer, r_inner=r_inner, r_sweep=num(r_sweep), sweep_w=r_inner, counts=counts,
        cut=num(cut), t_title=num(cut + 0.05), t_rule=num(cut + 0.45), t_sub=num(cut + 0.85), t_foot=num(cut + 1.6),
        title_size=title_size, title_ls=title_ls, title_ls_from=title_ls_from,
        title_x=centered_x(cx, title_size, title_ls), title_y=184,
        rule_y=rule_y, rule_x1=num(cx - 110), rule_x2=num(cx + 110),
        sub_size=sub_size, sub_ls=sub_ls, sub_ls_from=sub_ls_from,
        sub_x=centered_x(cx, sub_size, sub_ls), sub_y=242,
        foot_size=foot_size, foot_ls=foot_ls, foot_y=h - 30,
        foot_lx=margin, foot_cx=centered_x(cx, foot_size, foot_ls), foot_rx=num(w - margin + foot_ls * foot_size),
        narrow=TITLE_NARROW, title_size_m=title_size_m, sub_size_m=sub_size_m, foot_size_m=foot_size_m,
    )


# --- Credits card ------------------------------------------------------------
CREDITS_SVG = Template(
    """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 $w $h" width="$w" height="$h" role="img" aria-labelledby="credits-desc">
<title id="credits-desc">$aria</title>
<style>
"""
    + FONT_FACE_400
    + "\n"
    + CARD_STYLE
    + """
.head{font-size:${head_size}px;letter-spacing:${head_ls}em;fill:$label}
.role{font-size:${role_size}px;letter-spacing:${role_ls}em;fill:$label}
.name{font-size:${name_size}px;letter-spacing:${name_ls}em;fill:$name}
.m .head{font-size:${head_size_m}px}
.m .role{font-size:${role_size_m}px}
.m .name{font-size:${name_size_m}px}
</style>
<g class="d">
$desktop
</g>
<g class="m">
$mobile
</g>
</svg>
"""
)


def credits_alt() -> str:
    parts = [f"{role.title()}: {name}" for role, name in CREDITS]
    return f"{CREDITS_HEADER.title()} — " + " · ".join(parts)


def render_credits(f400: str, m: Metrics, theme: str) -> str:
    w, margin = CARD_W, CARD_MARGIN
    head_size, head_ls = 11, 0.5
    role_size, role_ls = 10.5, 0.3
    name_size, name_ls = 15, 0.01
    head_size_m, role_size_m, name_size_m = 14, 13, 21
    colors = THEMES[theme]

    # Desktop: end-credits layout, role right-aligned | gutter | name left-aligned.
    head_y, row0, step, gap = 30, 78, 38, 26
    max_role = max(m.width(role, role_size, role_ls) for role, _ in CREDITS)
    max_name = max(m.width(name, name_size, name_ls) for _, name in CREDITS)
    gutter = w / 2 - (max_name - max_role) / 2  # block optically centered
    left, right = gutter - gap / 2 - max_role, gutter + gap / 2 + max_name
    if left < margin or right > w - margin:
        raise SystemExit(f"credits overflow: {left:.0f}..{right:.0f} in {w}")
    desktop = [
        row(ROW_DELAY, f'<text class="head" x="{centered_x(w / 2, head_size, head_ls)}" y="{head_y}" text-anchor="middle">{escape(CREDITS_HEADER)}</text>')
    ]
    for i, (role, name) in enumerate(CREDITS):
        y = row0 + i * step
        desktop.append(
            row(
                ROW_DELAY + 0.2 + i * ROW_STAGGER,
                f'<text class="role" x="{num(gutter - gap / 2 + role_ls * role_size)}" y="{y}" text-anchor="end">{escape(role)}</text>'
                f'<text class="name" x="{num(gutter + gap / 2)}" y="{y}">{escape(name)}</text>',
            )
        )
    h_desktop = row0 + step * (len(CREDITS) - 1) + 30

    # Phone: stacked and centered, larger type (the <img> renders at ~0.55x there).
    head_y_m, row0_m, step_m, name_dy = 26, 58, 46, 22
    for _, name in CREDITS:
        m.fits(name, name_size_m, name_ls, w - 2 * margin, "credits name (phone)")
    mobile = [
        row(ROW_DELAY, f'<text class="head" x="{centered_x(w / 2, head_size_m, head_ls)}" y="{head_y_m}" text-anchor="middle">{escape(CREDITS_HEADER)}</text>')
    ]
    for i, (role, name) in enumerate(CREDITS):
        y = row0_m + i * step_m
        mobile.append(
            row(
                ROW_DELAY + 0.2 + i * ROW_STAGGER,
                f'<text class="role" x="{centered_x(w / 2, role_size_m, role_ls)}" y="{y}" text-anchor="middle">{escape(role)}</text>'
                f'<text class="name" x="{centered_x(w / 2, name_size_m, name_ls)}" y="{y + name_dy}" text-anchor="middle">{escape(name)}</text>',
            )
        )
    h_mobile = row0_m + step_m * (len(CREDITS) - 1) + name_dy + 22
    h = max(h_desktop, h_mobile)
    print(f"credits[{theme}] block {left:.0f}..{right:.0f}/{w}, h={h}")

    return CREDITS_SVG.substitute(
        w=w, h=h, fonts=FONT_STACK, f400=f400, aria=escape(credits_alt()), narrow=CARD_NARROW,
        head_size=head_size, head_ls=head_ls, role_size=role_size, role_ls=role_ls, name_size=name_size, name_ls=name_ls,
        head_size_m=head_size_m, role_size_m=role_size_m, name_size_m=name_size_m,
        label=colors["label"], name=colors["name"],
        desktop="\n".join(desktop), mobile="\n".join(mobile),
    )


# --- Live stats card ---------------------------------------------------------
STATS_SVG = Template(
    """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 $w $h" width="$w" height="$h" role="img" aria-labelledby="stats-desc">
<title id="stats-desc">$aria</title>
<style>
"""
    + FONT_FACE_400
    + "\n"
    + CARD_STYLE
    + """
.head{font-size:${head_size}px;letter-spacing:${head_ls}em;fill:$label}
.line{font-size:${line_size}px;letter-spacing:${line_ls}em;fill:$label}
.num{fill:$name}
.m .head{font-size:${head_size_m}px}
.m .line{font-size:${line_size_m}px}
</style>
<g class="d">
$desktop
</g>
<g class="m">
$mobile
</g>
</svg>
"""
)


def stats_lines(stats: dict) -> Tuple[str, str, str]:
    """(desktop one-liner, phone line 1, phone line 2)."""
    count = f"{int(stats['last_30_days']):,}"
    streak = int(stats.get("streak_days") or 0)
    seen = stats.get("last_seen_days_ago")
    if streak >= 7:  # a short streak next to a big monthly count reads weak
        tail = f"{streak}-DAY STREAK"
    elif seen == 0:
        tail = "LAST SEEN TODAY"
    elif seen == 1:
        tail = "LAST SEEN YESTERDAY"
    elif seen is None:
        tail = "ON HIATUS"
    else:
        tail = f"LAST SEEN {seen} DAYS AGO"
    return f"{count} CONTRIBUTIONS IN THE LAST 30 DAYS · {tail}", f"{count} CONTRIBUTIONS · LAST 30 DAYS", tail


def highlight(text: str) -> str:
    """Escape for XML and wrap numbers in a brighter tspan."""
    return re.sub(r"\d[\d,]*", lambda m: f'<tspan class="num">{m.group(0)}</tspan>', escape(text))


def render_stats(f400: str, m: Metrics, theme: str, stats: dict) -> str:
    w, h, margin = CARD_W, 92, CARD_MARGIN
    head_size, head_ls = 11, 0.5
    line_size, line_ls = 11, 0.3
    head_size_m, line_size_m = 14, 15
    colors = THEMES[theme]
    desktop_line, phone_1, phone_2 = stats_lines(stats)
    m.fits(desktop_line, line_size, line_ls, w - 2 * margin, "stats line")
    m.fits(phone_1, line_size_m, line_ls, w - 2 * margin, "stats line (phone)")

    cx = w / 2
    desktop = [
        row(ROW_DELAY, f'<text class="head" x="{centered_x(cx, head_size, head_ls)}" y="26" text-anchor="middle">{escape(STATS_HEADER)}</text>'),
        row(ROW_DELAY + 0.2, f'<text class="line" x="{centered_x(cx, line_size, line_ls)}" y="56" text-anchor="middle">{highlight(desktop_line)}</text>'),
    ]
    mobile = [
        row(ROW_DELAY, f'<text class="head" x="{centered_x(cx, head_size_m, head_ls)}" y="24" text-anchor="middle">{escape(STATS_HEADER)}</text>'),
        row(ROW_DELAY + 0.2, f'<text class="line" x="{centered_x(cx, line_size_m, line_ls)}" y="54" text-anchor="middle">{highlight(phone_1)}</text>'),
        row(ROW_DELAY + 0.32, f'<text class="line" x="{centered_x(cx, line_size_m, line_ls)}" y="78" text-anchor="middle">{highlight(phone_2)}</text>'),
    ]
    aria = f"{STATS_HEADER.title()} — {desktop_line.lower()} (as of {stats.get('generated_at', 'unknown')})"
    print(f"stats[{theme}]: {desktop_line}")
    return STATS_SVG.substitute(
        w=w, h=h, fonts=FONT_STACK, f400=f400, aria=escape(aria), narrow=CARD_NARROW,
        head_size=head_size, head_ls=head_ls, line_size=line_size, line_ls=line_ls,
        head_size_m=head_size_m, line_size_m=line_size_m,
        label=colors["label"], name=colors["name"],
        desktop="\n".join(desktop), mobile="\n".join(mobile),
    )


# --- Main --------------------------------------------------------------------
def write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    print(f"wrote {path} ({len(content.encode()) / 1024:.1f} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stats", type=Path, help="stats JSON from fetch_stats.py; renders only the live stats card")
    parser.add_argument("--out", type=Path, default=ROOT / "assets", help="output directory (default: assets/)")
    args = parser.parse_args()

    vf = variable_font()
    regular, f400 = build_face(vf, 400)
    m400 = Metrics(regular)
    args.out.mkdir(parents=True, exist_ok=True)

    if args.stats:
        stats = json.loads(args.stats.read_text(encoding="utf-8"))
        for theme in THEMES:
            write(args.out / f"stats-{theme}.svg", render_stats(f400, m400, theme, stats))
        return

    medium, f500 = build_face(vf, 500)
    write(args.out / "title.svg", render_title(f400, f500, m400, Metrics(medium)))
    for theme in THEMES:
        write(args.out / f"credits-{theme}.svg", render_credits(f400, m400, theme))
    print(f"\ncredits alt text:\n{credits_alt()}")


if __name__ == "__main__":
    main()
