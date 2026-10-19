"""Build a crimson telemetry card from public + private GitHub activity.

Runs inside GitHub Actions. Env vars:
  GH_USER   - GitHub username
  PR_TOKEN  - classic personal access token with `repo` scope (sees private repos)
  OUT       - output SVG path (default dist/telemetry.svg)
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from html import escape

USER = os.environ["GH_USER"]
TOKEN = os.environ.get("PR_TOKEN", "").strip()
OUT = os.environ.get("OUT", "dist/telemetry.svg")
if not TOKEN:
    raise SystemExit("PR_STATS_TOKEN secret is missing or empty. Add it under Settings > Secrets and variables > Actions.")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "telemetry-card",
}


def _open(req):
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise SystemExit("401 Unauthorized: PR_STATS_TOKEN is invalid or expired. Generate a new classic token with 'repo' scope and update the secret.")
        if e.code == 403:
            raise SystemExit("403 Forbidden: token not authorized for an org (Configure SSO on the token) or rate-limited.")
        raise


def search_count(query):
    url = "https://api.github.com/search/issues?per_page=1&q=" + urllib.parse.quote(query)
    return _open(urllib.request.Request(url, headers=HEADERS))["total_count"]


def graphql(query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    data = _open(urllib.request.Request("https://api.github.com/graphql", data=body, headers=HEADERS))
    if data.get("errors"):
        raise SystemExit(f"GraphQL error: {data['errors'][0].get('message')}")
    return data["data"]


# ---------- PRs ----------
opened = search_count(f"is:pr author:{USER}")
merged = search_count(f"is:pr is:merged author:{USER}")

# ---------- commits + contributions, every year (private included for your own token) ----------
years = graphql(
    "query($u:String!){user(login:$u){contributionsCollection{contributionYears}}}", {"u": USER}
)["user"]["contributionsCollection"]["contributionYears"]

commits = contributions = 0
for y in years:
    c = graphql(
        """query($u:String!,$f:DateTime!,$t:DateTime!){user(login:$u){
             contributionsCollection(from:$f,to:$t){
               totalCommitContributions restrictedContributionsCount
               contributionCalendar{totalContributions}}}}""",
        {"u": USER, "f": f"{y}-01-01T00:00:00Z", "t": f"{y}-12-31T23:59:59Z"},
    )["user"]["contributionsCollection"]
    commits += c["totalCommitContributions"]
    contributions += c["contributionCalendar"]["totalContributions"]

# ---------- repos contributed to + language mix across them ----------
lang_bytes, repo_count, cursor = {}, 0, None
while True:
    r = graphql(
        """query($u:String!,$c:String){user(login:$u){
             repositoriesContributedTo(first:50,after:$c,includeUserRepositories:true,
               contributionTypes:[COMMIT,PULL_REQUEST,REPOSITORY]){
               totalCount pageInfo{hasNextPage endCursor}
               nodes{isFork languages(first:10,orderBy:{field:SIZE,direction:DESC}){edges{size node{name}}}}}}}""",
        {"u": USER, "c": cursor},
    )["user"]["repositoriesContributedTo"]
    repo_count = r["totalCount"]
    for repo in r["nodes"]:
        if repo["isFork"]:
            continue
        for e in repo["languages"]["edges"]:
            n = e["node"]["name"]
            lang_bytes[n] = lang_bytes.get(n, 0) + e["size"]
    if not r["pageInfo"]["hasNextPage"]:
        break
    cursor = r["pageInfo"]["endCursor"]

total_b = sum(lang_bytes.values()) or 1
langs = sorted(lang_bytes.items(), key=lambda kv: -kv[1])[:6]
langs = [(n, b * 100 / total_b) for n, b in langs]

rate = f"{round(merged * 100 / opened)}%" if opened else "-"
fmt = lambda v: v if isinstance(v, str) else f"{v:,}"
print({"commits": commits, "contributions": contributions, "opened": opened,
       "merged": merged, "rate": rate, "repos": repo_count, "langs": langs})

# ---------- draw ----------
W, H = 840, 384
rows = [
    [("COMMITS", commits), ("PULL REQUESTS", opened), ("PRS MERGED", merged)],
    [("MERGE RATE", rate), ("CONTRIBUTIONS", contributions), ("REPOS CONTRIBUTED TO", repo_count)],
]
colw = W / 3
parts, k = [], 0
for ri, row in enumerate(rows):
    ny, ly = 102 + ri * 92, 128 + ri * 92
    for ci, (label, value) in enumerate(row):
        cx = colw * ci + colw / 2
        parts.append(
            f'<g style="animation:rise .8s ease-out {k*0.12:.2f}s both">'
            f'<text x="{cx:.0f}" y="{ny}" text-anchor="middle" class="num">{fmt(value)}</text>'
            f'<text x="{cx:.0f}" y="{ly}" text-anchor="middle" class="lbl">{label}</text></g>')
        k += 1
for i in (1, 2):
    parts.append(f'<line x1="{colw*i:.0f}" y1="66" x2="{colw*i:.0f}" y2="226" stroke="#FF5368" stroke-opacity=".2"/>')
parts.append('<line x1="28" y1="250" x2="812" y2="250" stroke="#FF5368" stroke-opacity=".2"/>')

palette = ["#FF2D4A", "#FF8A5C", "#FFB454", "#E0E3E8", "#8B929E", "#7A1A2C"]
parts.append('<text x="28" y="280" class="t">// LANGUAGES ACROSS REPOS I WORK IN</text>')
bx, bw = 28, 784
parts.append(f'<clipPath id="bar"><rect x="{bx}" y="294" width="{bw}" height="10" rx="5"/></clipPath><g clip-path="url(#bar)">')
x = bx
for i, (n, p) in enumerate(langs):
    w = bw * p / sum(pp for _, pp in langs)
    parts.append(f'<rect x="{x:.1f}" y="294" width="{w+0.5:.1f}" height="10" fill="{palette[i]}"/>')
    x += w
parts.append('</g>')
for i, (n, p) in enumerate(langs):
    col, row = i % 3, i // 3
    lx, ly = 28 + col * 262, 334 + row * 26
    parts.append(f'<circle cx="{lx+5}" cy="{ly-4}" r="5" fill="{palette[i]}"/>'
                 f'<text x="{lx+16}" y="{ly}" class="leg">{escape(n)} <tspan fill="#8B929E">{p:.1f}%</tspan></text>')

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
  <style>
    .t{{font:700 12px 'JetBrains Mono',Consolas,monospace;fill:#FF5368;letter-spacing:3px}}
    .num{{font:800 38px 'JetBrains Mono',Consolas,monospace;fill:#F2F3F5}}
    .lbl{{font:600 10.5px 'JetBrains Mono',Consolas,monospace;fill:#8B929E;letter-spacing:2px}}
    .leg{{font:600 12px 'JetBrains Mono',Consolas,monospace;fill:#E0E3E8}}
    @keyframes rise{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:none}}}}
  </style>
  <rect width="{W}" height="{H}" rx="12" fill="#08090D"/>
  <text x="28" y="38" class="t">// ENGINEERING TELEMETRY · PUBLIC + PRIVATE</text>
  {''.join(parts)}
  <rect x="0" y="{H-3}" width="{W}" height="3" fill="#FF5368" opacity=".7"/>
</svg>'''

os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(svg)
print("wrote", OUT)
