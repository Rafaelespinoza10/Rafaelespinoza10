#!/usr/bin/env python3
"""Generate the HUD-style profile, telemetry and loadout cards for the README.

Pulls live numbers from the GitHub GraphQL API, so it needs a token in
GH_TOKEN / GITHUB_TOKEN (falls back to `gh auth token`). Standard library only.

Run from the repository root:
    python scripts/hud/generate.py
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"
SKILLS = Path(__file__).resolve().parent / "skills.json"

LOGIN = "Rafaelespinoza10"
W = 1180
MONO = "ui-monospace,SFMono-Regular,Consolas,monospace"

# Byte-heavy or non-code languages that would drown out the real mix.
LANG_EXCLUDE = {"Jupyter Notebook", "HTML", "CSS", "SCSS", "Dockerfile", "Makefile"}

PROFILE = {
    "dossier": [
        ("CALLSIGN", "Rafael Moreno"),
        ("CLASS", "Software Engineer · Full-Stack & AI"),
        ("ORIGIN", "Mechatronics Engineering"),
        ("BASE", "San Luis Potosí, MX"),
    ],
    "brief": (
        "I build full-stack products and AI-assisted systems: serverless APIs, "
        ".NET and Node services, and the test automation that keeps them honest. "
        "Mechatronics taught me to measure, iterate and ship."
    ),
    "directive": "Become a Full-Stack AI Engineer",
    "modules": [
        "AI-powered automation",
        "Full-stack applications",
        "Testing infrastructure",
        "Developer productivity tools",
    ],
    "interests": [
        "Full-Stack Development",
        "AI Engineering",
        "Software Architecture",
        "Test Automation",
        "Developer Tools",
    ],
    "fun_fact": "there are only 10 types of people: those who get binary and those who don't",
}

THEMES = {
    "dark": {
        "bg": "#0A101F",
        "panel": "#0D1628",
        "panel2": "#101B30",
        "line": "#25344C",
        "muted": "#8291A8",
        "text": "#DDE7F5",
        "chrome": "#22D3EE",
        "blue": "#7AA2F7",
        "accent": "#10B981",
        "shadow": "#02050B",
        "track": "#16233B",
        # Sequential cyan ramp: empty -> busiest (lighter = more on dark).
        "heat": ["#16233B", "#0E4A5C", "#0E7490", "#06B6D4", "#67E8F9"],
    },
    "light": {
        "bg": "#F6F8FA",
        "panel": "#FFFFFF",
        "panel2": "#EDF3F7",
        "line": "#CBD7E1",
        "muted": "#64748B",
        "text": "#172033",
        "chrome": "#0891B2",
        "blue": "#1E3A8A",
        "accent": "#059669",
        "shadow": "#AAB7C4",
        "track": "#DCE5EE",
        "heat": ["#DCE5EE", "#A5F3FC", "#22D3EE", "#0891B2", "#155E75"],
    },
}

LEVELS = {
    "NONE": 0,
    "FIRST_QUARTILE": 1,
    "SECOND_QUARTILE": 2,
    "THIRD_QUARTILE": 3,
    "FOURTH_QUARTILE": 4,
}

QUERY = """
query($login: String!) {
  user(login: $login) {
    createdAt
    repositories(ownerAffiliations: OWNER, first: 100, isFork: false, privacy: PUBLIC) {
      totalCount
      nodes {
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount contributionLevel } }
      }
    }
  }
}
"""


# ---------------------------------------------------------------- data


def token() -> str:
    for key in ("GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(key):
            return os.environ[key]
    return subprocess.run(
        ["gh", "auth", "token"], capture_output=True, text=True, check=True
    ).stdout.strip()


def fetch() -> dict:
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode(),
        headers={"Authorization": f"bearer {token()}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if "errors" in payload:
        raise SystemExit(f"GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def streaks(days: list[dict]) -> tuple[int, int]:
    """Current streak (today may still be empty) and longest streak, in days."""
    longest = run = 0
    for day in days:
        run = run + 1 if day["contributionCount"] else 0
        longest = max(longest, run)
    current = 0
    tail = days[:-1] if days and not days[-1]["contributionCount"] else days
    for day in reversed(tail):
        if not day["contributionCount"]:
            break
        current += 1
    return current, longest


def language_mix(user: dict, top: int = 6) -> list[tuple[str, float]]:
    totals: dict[str, int] = {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            if name not in LANG_EXCLUDE:
                totals[name] = totals.get(name, 0) + edge["size"]
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])
    grand = sum(totals.values()) or 1
    mix = [(name, size / grand) for name, size in ranked[:top]]
    rest = sum(size for _, size in ranked[top:])
    if rest:
        mix.append(("Other", rest / grand))
    return mix


# ---------------------------------------------------------------- svg helpers


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def tw(text: str, size: float) -> float:
    """Monospace advance used for layout (matches the banner generator)."""
    return len(text) * size * 0.605


def text(x, y, body, t, color="text", size=14, anchor="start", weight=None, spacing=None):
    attrs = f'x="{x:g}" y="{y:g}" fill="{t[color]}" font-family="{MONO}" font-size="{size}"'
    if anchor != "start":
        attrs += f' text-anchor="{anchor}"'
    if weight:
        attrs += f' font-weight="{weight}"'
    if spacing:
        attrs += f' letter-spacing="{spacing}"'
    return f"<text {attrs}>{esc(body)}</text>"


def wrap(body: str, width: int) -> list[str]:
    lines, line = [], ""
    for word in body.split():
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return lines + [line] if line else lines


def frame(t: dict, height: int, title: str, desc: str, chrome_title: str) -> list[str]:
    """Window chrome shared by every card, matching the rafael.sh banner."""
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" '
        f'viewBox="0 0 {W} {height}" role="img" aria-labelledby="title desc">',
        f'<title id="title">{esc(title)}</title><desc id="desc">{esc(desc)}</desc>',
        "<defs>"
        '<filter id="shadow" x="-20%" y="-20%" width="140%" height="150%">'
        f'<feDropShadow dx="0" dy="12" stdDeviation="16" flood-color="{t["shadow"]}" '
        'flood-opacity=".28"/></filter>'
        '<filter id="glow" x="-100%" y="-100%" width="300%" height="300%">'
        f'<feGaussianBlur stdDeviation="3" result="b"/><feFlood flood-color="{t["chrome"]}" '
        'flood-opacity=".45"/><feComposite in2="b" operator="in"/>'
        '<feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
        '<linearGradient id="scan" x1="0" x2="1">'
        f'<stop offset="0" stop-color="{t["chrome"]}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{t["chrome"]}" stop-opacity=".22"/></linearGradient>'
        "</defs>",
        f'<rect width="{W}" height="{height}" rx="18" fill="{t["bg"]}"/>',
        f'<rect x="13" y="13" width="1154" height="{height - 26}" rx="13" fill="{t["panel"]}" '
        f'stroke="{t["line"]}" filter="url(#shadow)"/>',
        f'<path d="M13 62H1167" stroke="{t["line"]}"/>',
        '<circle cx="38" cy="38" r="6" fill="#FF5F57"/>'
        '<circle cx="59" cy="38" r="6" fill="#FEBC2E"/>'
        '<circle cx="80" cy="38" r="6" fill="#28C840"/>',
        text(590, 43, chrome_title, t, "muted", 13, "middle", spacing=".4"),
    ]


def panel(t, x, y, w, h, label, right: str | None = None) -> list[str]:
    parts = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{t["panel2"]}" '
        f'stroke="{t["line"]}"/>',
        f'<path d="M{x} {y + 36}H{x + w}" stroke="{t["line"]}"/>',
        text(x + 16, y + 23, label, t, "chrome", 13, weight=700, spacing="1.2"),
        # HUD corner brackets.
        f'<path d="M{x + 8} {y + 48}h10M{x + 8} {y + 48}v10M{x + w - 8} {y + 48}h-10'
        f'M{x + w - 8} {y + 48}v10M{x + 8} {y + h - 8}h10M{x + 8} {y + h - 8}v-10'
        f'M{x + w - 8} {y + h - 8}h-10M{x + w - 8} {y + h - 8}v-10" fill="none" '
        f'stroke="{t["chrome"]}" opacity=".5"/>',
    ]
    if right:
        parts.append(text(x + w - 16, y + 23, right, t, "muted", 11, "end"))
    return parts


def live_dot(t, x, y, color="accent", delay=0.0) -> str:
    return (
        f'<circle cx="{x:g}" cy="{y:g}" r="4" fill="{t[color]}">'
        f'<animate attributeName="opacity" values="1;.25;1" dur="1.8s" begin="{delay:g}s" '
        'repeatCount="indefinite"/></circle>'
    )


def scanline(t, x, y, w, h, dur=6.0) -> str:
    """A soft vertical sweep that crosses a region and loops."""
    return (
        f'<rect x="{x - 60}" y="{y}" width="60" height="{h}" fill="url(#scan)" opacity=".9">'
        f'<animate attributeName="x" values="{x - 60};{x + w}" dur="{dur}s" '
        'repeatCount="indefinite"/></rect>'
    )


# ---------------------------------------------------------------- cards


def profile_card(t: dict) -> str:
    h = 440
    parts = frame(
        t, h, "Rafael Moreno - operator profile",
        "Mission brief, active modules and interests.", "operator.profile --brief",
    )

    # Left: dossier + brief.
    lx, ly, lw, lh = 35, 88, 606, 296
    parts += panel(t, lx, ly, lw, lh, "MISSION.BRIEF", "CLEARANCE: OPEN")
    y = ly + 70
    for key, value in PROFILE["dossier"]:
        parts.append(text(lx + 24, y, key, t, "muted", 13, spacing=".6"))
        parts.append(text(lx + 150, y, value, t, "text", 14, weight=600))
        y += 25
    y += 8
    parts.append(f'<path d="M{lx + 24} {y - 14}H{lx + lw - 24}" stroke="{t["line"]}" '
                 'stroke-dasharray="2 4"/>')
    for line in wrap(PROFILE["brief"], 64):
        parts.append(text(lx + 24, y + 6, line, t, "text", 13))
        y += 21
    y += 16
    parts.append(text(lx + 24, y, "PRIME.DIRECTIVE ▸", t, "chrome", 13, weight=700, spacing=".6"))
    parts.append(text(lx + 190, y, PROFILE["directive"], t, "text", 14, weight=700))
    cursor_x = lx + 190 + tw(PROFILE["directive"], 14) + 6
    parts.append(
        f'<rect x="{cursor_x:g}" y="{y - 12}" width="8" height="15" fill="{t["chrome"]}">'
        '<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;.5;.5;1" dur="1.1s" '
        'repeatCount="indefinite"/></rect>'
    )

    # Right: active modules + interests.
    rx, ry, rw, rh = 661, 88, 485, 296
    parts += panel(t, rx, ry, rw, rh, "ACTIVE.MODULES")
    parts.append(live_dot(t, rx + rw - 64, ry + 18, "accent"))
    parts.append(text(rx + rw - 16, ry + 23, "ONLINE", t, "accent", 11, "end", weight=700))
    y = ry + 72
    for i, module in enumerate(PROFILE["modules"]):
        parts.append(live_dot(t, rx + 30, y - 5, "chrome", delay=i * 0.35))
        parts.append(text(rx + 46, y, module, t, "text", 14))
        parts.append(text(rx + rw - 24, y, "RUNNING", t, "muted", 10, "end", spacing="1"))
        y += 27
    y += 10
    parts.append(text(rx + 24, y, "INTERESTS", t, "muted", 11, weight=700, spacing="1.2"))
    cx, cy = rx + 24, y + 14
    for interest in PROFILE["interests"]:
        cw = tw(interest, 11) + 20
        if cx + cw > rx + rw - 20:
            cx, cy = rx + 24, cy + 30
        parts.append(
            f'<rect x="{cx:g}" y="{cy}" width="{cw:g}" height="22" rx="11" '
            f'fill="{t["chrome"]}" fill-opacity=".1" stroke="{t["chrome"]}" stroke-opacity=".55"/>'
        )
        parts.append(text(cx + cw / 2, cy + 15, interest, t, "chrome", 11, "middle"))
        cx += cw + 8

    parts.append(scanline(t, 35, 88, 1111, 296, dur=7))
    parts.append(f'<path d="M35 400H1146" stroke="{t["line"]}"/>')
    parts.append(text(35, 420, f"> fun_fact: {PROFILE['fun_fact']}", t, "muted", 11))
    parts.append(text(1146, 420, "● SIGNAL STRONG", t, "accent", 11, "end"))
    parts.append("</svg>")
    return "".join(parts)


def telemetry_card(t: dict, user: dict, today: str) -> str:
    h = 496
    cc = user["contributionsCollection"]
    calendar = cc["contributionCalendar"]
    weeks = calendar["weeks"]
    days = [d for week in weeks for d in week["contributionDays"]]
    current, longest = streaks(days)
    since = user["createdAt"][:4]

    parts = frame(
        t, h, "Rafael Moreno - GitHub telemetry",
        f"{calendar['totalContributions']} contributions in the last year, "
        f"{current}-day current streak, {longest}-day longest streak.",
        "telemetry.stream --last-365d",
    )
    px, py, pw, ph = 35, 88, 1111, 356
    parts += panel(t, px, py, pw, ph, "TELEMETRY", f"SYNC {today} UTC")

    tiles = [
        ("CONTRIBUTIONS", f"{calendar['totalContributions']:,}", "last 365 days"),
        ("COMMITS", f"{cc['totalCommitContributions']:,}", "public repos"),
        ("PULL REQUESTS", f"{cc['totalPullRequestContributions']:,}", "opened"),
        ("CURRENT STREAK", f"{current}", "days"),
        ("LONGEST STREAK", f"{longest}", "days"),
        ("REPOSITORIES", f"{user['repositories']['totalCount']}", "public"),
    ]
    gap = 12
    tile_w = (pw - 48 - gap * (len(tiles) - 1)) / len(tiles)
    for i, (label, value, sub) in enumerate(tiles):
        x = px + 24 + i * (tile_w + gap)
        y = py + 56
        parts.append(
            f'<rect x="{x:g}" y="{y}" width="{tile_w:g}" height="92" rx="5" fill="{t["panel"]}" '
            f'stroke="{t["line"]}"/>'
            f'<path d="M{x:g} {y + 1}h3v90h-3z" fill="{t["chrome"]}" opacity=".8"/>'
        )
        parts.append(text(x + 16, y + 24, label, t, "muted", 10, spacing="1"))
        parts.append(text(x + 16, y + 60, value, t, "text", 30, weight=700))
        parts.append(text(x + 16, y + 80, sub, t, "muted", 10))

    # Contribution heatmap: one sequential hue, GitHub's own quartile levels.
    cell, step = 14, 18.5
    grid_w = (len(weeks) - 1) * step + cell
    gx, gy = px + (pw - grid_w) / 2, py + 196
    last_month = None
    for wi, week in enumerate(weeks):
        first = week["contributionDays"][0]["date"]
        month = first[5:7]
        if month != last_month and wi < len(weeks) - 2:
            label = dt.date.fromisoformat(first).strftime("%b").upper()
            parts.append(text(gx + wi * step, gy - 10, label, t, "muted", 10))
            last_month = month
        for day in week["contributionDays"]:
            row = dt.date.fromisoformat(day["date"]).isoweekday() % 7
            level = LEVELS.get(day["contributionLevel"], 0)
            parts.append(
                f'<rect x="{gx + wi * step:g}" y="{gy + row * step:g}" width="{cell}" '
                f'height="{cell}" rx="3" fill="{t["heat"][level]}">'
                f'<title>{day["date"]} · {day["contributionCount"]} contributions</title></rect>'
            )
    parts.append(scanline(t, gx, gy - 4, grid_w, 7 * step, dur=5))

    ly = gy + 7 * step + 16
    parts.append(text(gx, ly, "◢ CONTRIBUTION DENSITY", t, "muted", 10, spacing="1"))
    lx = gx + grid_w - 5 * step - 42
    parts.append(text(lx - 8, ly, "LESS", t, "muted", 10, "end"))
    for level in range(5):
        parts.append(
            f'<rect x="{lx + level * step:g}" y="{ly - 11}" width="{cell}" height="{cell}" '
            f'rx="3" fill="{t["heat"][level]}"/>'
        )
    parts.append(text(lx + 5 * step + 4, ly, "MORE", t, "muted", 10))

    parts.append(f'<path d="M35 460H1146" stroke="{t["line"]}"/>')
    parts.append(text(35, 480, f"● UPLINK ACTIVE · ONLINE SINCE {since}", t, "accent", 11))
    parts.append(text(1146, 480, "auto-sync daily via GitHub Actions", t, "muted", 11, "end"))
    parts.append("</svg>")
    return "".join(parts)


def loadout_card(t: dict, mix: list[tuple[str, float]], skills: list) -> str:
    h = 400
    parts = frame(
        t, h, "Rafael Moreno - language mix and skill matrix",
        "Language share by bytes across public repositories, and self-assessed skill levels.",
        "loadout.sys --scan",
    )

    # Left: language mix, one hue, sorted by share.
    lx, ly, lw, lh = 35, 88, 545, 260
    parts += panel(t, lx, ly, lw, lh, "LANGUAGE.MIX", "BY BYTES")
    track_x, track_w = lx + 160, 290
    y = ly + 70
    for name, share in mix:
        bar = max(track_w * share, 4)
        parts.append(text(lx + 24, y, name, t, "text", 13))
        parts.append(
            f'<rect x="{track_x}" y="{y - 9}" width="{track_w}" height="8" rx="4" fill="{t["track"]}"/>'
            f'<rect x="{track_x}" y="{y - 9}" width="{bar:g}" height="8" rx="4" fill="{t["chrome"]}"/>'
        )
        parts.append(text(lx + lw - 24, y, f"{share * 100:.1f}%", t, "muted", 12, "end"))
        y += 26

    # Right: self-assessed skill gauges, ten segments each.
    rx, ry, rw, rh = 600, 88, 546, 260
    parts += panel(t, rx, ry, rw, rh, "SKILL.MATRIX", "SELF-ASSESSED")
    seg_w, seg_gap = 20, 5
    seg_x = rx + 200
    y = ry + 70
    for i, (name, level) in enumerate(skills):
        parts.append(text(rx + 24, y, name, t, "text", 13))
        for s in range(10):
            on = s < level
            fill = t["blue"] if on else t["track"]
            parts.append(
                f'<rect x="{seg_x + s * (seg_w + seg_gap)}" y="{y - 11}" width="{seg_w}" '
                f'height="12" rx="2" fill="{fill}"/>'
            )
        # A pulse travels along each filled gauge.
        if level:
            end = seg_x + level * (seg_w + seg_gap) - seg_gap
            parts.append(
                f'<rect x="{seg_x}" y="{y - 11}" width="{seg_w}" height="12" rx="2" '
                f'fill="{t["text"]}" opacity=".35">'
                f'<animate attributeName="x" values="{seg_x};{end - seg_w}" dur="2.4s" '
                f'begin="{i * 0.3:g}s" repeatCount="indefinite"/></rect>'
            )
        parts.append(text(rx + rw - 24, y, f"{level}/10", t, "muted", 12, "end"))
        y += 30

    parts.append(f'<path d="M35 364H1146" stroke="{t["line"]}"/>')
    parts.append(text(35, 384, "◢ public repos · notebooks & markup excluded", t, "muted", 11))
    parts.append(text(1146, 384, "● LOADOUT NOMINAL", t, "accent", 11, "end"))
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------- main


def main() -> None:
    user = fetch()
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    mix = language_mix(user)
    skills = json.loads(SKILLS.read_text(encoding="utf-8"))["skills"]
    ASSETS.mkdir(parents=True, exist_ok=True)
    for name, t in THEMES.items():
        cards = {
            f"hud-profile-{name}.svg": profile_card(t),
            f"hud-telemetry-{name}.svg": telemetry_card(t, user, today),
            f"hud-loadout-{name}.svg": loadout_card(t, mix, skills),
        }
        for filename, svg in cards.items():
            output = ASSETS / filename
            output.write_text(svg, encoding="utf-8")
            print(f"{output.relative_to(ROOT)}: {output.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
