"""Count Shikhar's PRs (public + private) with a personal token and draw a crimson SVG card.

Runs inside GitHub Actions. Needs env vars:
  GH_USER   - GitHub username
  PR_TOKEN  - classic personal access token with `repo` scope (sees private repos)
  OUT       - output SVG path
"""
import json
import os
import urllib.parse
import urllib.request

USER = os.environ["GH_USER"]
TOKEN = os.environ["PR_TOKEN"]
OUT = os.environ.get("OUT", "dist/pr-stats.svg")


def count(query: str) -> int:
    url = "https://api.github.com/search/issues?per_page=1&q=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "pr-stats-card",
    })
    with urllib.request.urlopen(req) as r:
        return json.load(r)["total_count"]


stats = [
    ("PULL REQUESTS OPENED", count(f"is:pr author:{USER}")),
    ("PULL REQUESTS MERGED", count(f"is:pr is:merged author:{USER}")),
    ("PULL REQUESTS REVIEWED", count(f"is:pr reviewed-by:{USER} -author:{USER}")),
]
print(stats)

cols = len(stats)
W, H = 840, 190
colw = W / cols
cells = []
for i, (label, value) in enumerate(stats):
    cx = colw * i + colw / 2
    delay = i * 0.25
    cells.append(f'''
  <g style="animation:rise .9s ease-out {delay}s both">
    <text x="{cx}" y="104" text-anchor="middle" class="num">{value:,}</text>
    <text x="{cx}" y="140" text-anchor="middle" class="lbl">{label}</text>
  </g>''')
    if i:
        x = colw * i
        cells.append(f'<line x1="{x}" y1="62" x2="{x}" y2="156" stroke="#FF5368" stroke-opacity=".25"/>')

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
  <style>
    .t{{font:700 13px 'JetBrains Mono',Consolas,monospace;fill:#FF5368;letter-spacing:3px}}
    .num{{font:800 44px 'JetBrains Mono',Consolas,monospace;fill:#F2F3F5}}
    .lbl{{font:600 11px 'JetBrains Mono',Consolas,monospace;fill:#8B929E;letter-spacing:2px}}
    @keyframes rise{{from{{opacity:0;transform:translateY(10px)}}to{{opacity:1;transform:none}}}}
  </style>
  <rect width="{W}" height="{H}" rx="12" fill="#08090D"/>
  <text x="28" y="36" class="t">// PULL REQUEST LOG · PUBLIC + PRIVATE</text>
  {''.join(cells)}
  <rect x="0" y="{H-3}" width="{W}" height="3" rx="1.5" fill="#FF5368" opacity=".7"/>
</svg>'''

os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(svg)
print("wrote", OUT)
