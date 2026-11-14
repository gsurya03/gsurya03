import os, json, html, re, urllib.request
from datetime import date

TOKEN = os.environ["GH_TOKEN"]

def gql(query, variables=None):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    data = json.load(urllib.request.urlopen(req))
    if "errors" in data:
        raise SystemExit(data["errors"])
    return data["data"]

# ---------- repos (public + private, owned, non-fork) ----------
REPOS_Q = """
query($after:String){ viewer{ login name
  repositories(first:100, after:$after, ownerAffiliations:OWNER, isFork:false,
               orderBy:{field:PUSHED_AT, direction:DESC}){
    totalCount pageInfo{hasNextPage endCursor}
    nodes{ name isPrivate stargazerCount
      languages(first:10, orderBy:{field:SIZE, direction:DESC}){ edges{ size node{name} } } } } } }"""
repos, after = [], None
while True:
    v = gql(REPOS_Q, {"after": after})["viewer"]
    repos += v["repositories"]["nodes"]
    pi = v["repositories"]["pageInfo"]
    if not pi["hasNextPage"]:
        break
    after = pi["endCursor"]
login = v["login"]

langs = {}
for r in repos:
    for e in r["languages"]["edges"]:
        langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
total_size = sum(langs.values()) or 1
top = sorted(langs.items(), key=lambda x: -x[1])[:6]

# ---------- commits across every year (public + private) ----------
years = gql("{viewer{contributionsCollection{contributionYears}}}")["viewer"]["contributionsCollection"]["contributionYears"]
commits = 0
for y in years:
    c = gql("""query($f:DateTime!,$t:DateTime!){viewer{contributionsCollection(from:$f,to:$t){
        totalCommitContributions restrictedContributionsCount}}}""",
        {"f": f"{y}-01-01T00:00:00Z", "t": f"{y}-12-31T23:59:59Z"})["viewer"]["contributionsCollection"]
    commits += c["totalCommitContributions"] + c["restrictedContributionsCount"]

# ---------- last-year calendar ----------
cal = gql("""{viewer{contributionsCollection{contributionCalendar{totalContributions
    weeks{contributionDays{contributionLevel date}}}}}}""")["viewer"]["contributionsCollection"]["contributionCalendar"]
LV = {"NONE":0,"FIRST_QUARTER":1,"SECOND_QUARTER":2,"THIRD_QUARTER":3,"FOURTH_QUARTER":4}

stars = sum(r["stargazerCount"] for r in repos)
fmt = lambda n: f"{n:,}"

# ---------- SVG ----------
W, PAD = 800, 32
cell, gap = 11, 3
parts = []
stats = [(fmt(commits), "total commits"), (fmt(cal["totalContributions"]), "contributions this year"),
         (fmt(len(repos)), "repositories"), (fmt(stars), "stars earned")]
colw = (W - 2*PAD) / 4
for i, (n, label) in enumerate(stats):
    x = PAD + i*colw
    parts.append(f'<text x="{x}" y="62" font-size="28" font-weight="600">{n}</text>')
    parts.append(f'<text x="{x}" y="82" font-size="12" class="mut">{label}</text>')

gx, gy = PAD, 120
for wi, w in enumerate(cal["weeks"]):
    for di, d in enumerate(w["contributionDays"]):
        parts.append(f'<rect x="{gx+wi*(cell+gap)}" y="{gy+di*(cell+gap)}" width="{cell}" height="{cell}" rx="2" class="l{LV[d["contributionLevel"]]}"/>')

ly = gy + 7*(cell+gap) + 34
parts.append(f'<text x="{PAD}" y="{ly}" font-size="12" class="mut">languages · all repositories</text>')
bx, by, bw = PAD, ly+12, W - 2*PAD
pal = ["#3b82f6","#22c55e","#f59e0b","#ec4899","#a855f7","#94a3b8"]
x = bx
for i, (n, s) in enumerate(top):
    w = bw * s / sum(s for _, s in top)
    parts.append(f'<rect x="{x:.1f}" y="{by}" width="{w:.1f}" height="8" fill="{pal[i]}"/>')
    x += w
parts.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="8" rx="4" fill="none" stroke="none"/>')
for i, (n, s) in enumerate(top):
    cx = PAD + (i % 3) * (bw/3)
    cy = by + 34 + (i // 3) * 22
    parts.append(f'<circle cx="{cx+4}" cy="{cy-4}" r="4" fill="{pal[i]}"/>')
    parts.append(f'<text x="{cx+16}" y="{cy}" font-size="12">{html.escape(n)} <tspan class="mut">{s*100/total_size:.1f}%</tspan></text>')

H = by + 34 + 22 + 28
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<style>
text{{font-family:-apple-system,"Segoe UI",Helvetica,Arial,sans-serif;fill:#1f2328}}
.mut{{fill:#656d76}}.bg{{fill:#fff;stroke:#d0d7de}}
.l0{{fill:#ebedf0}}.l1{{fill:#9be9a8}}.l2{{fill:#40c463}}.l3{{fill:#30a14e}}.l4{{fill:#216e39}}
@media (prefers-color-scheme:dark){{
text{{fill:#e6edf3}}.mut{{fill:#8b949e}}.bg{{fill:#0d1117;stroke:#30363d}}
.l0{{fill:#161b22}}.l1{{fill:#0e4429}}.l2{{fill:#006d32}}.l3{{fill:#26a641}}.l4{{fill:#39d353}}}}
</style>
<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="12" class="bg"/>
{chr(10).join(parts)}
</svg>'''
open("stats.svg", "w").write(svg)

# ---------- repo list in README ----------
pub = [r for r in repos if not r["isPrivate"]]
prv = [r for r in repos if r["isPrivate"]]
block = "**Public**<br>\n" + " · ".join(f"`{r['name']}`" for r in pub) + "\n\n"
block += "**Private** 🔒<br>\n" + " · ".join(f"`{r['name']}`" for r in prv) + "\n"
md = open("README.md").read()
md = re.sub(r"<!--REPOS:START-->.*?<!--REPOS:END-->", f"<!--REPOS:START-->\n{block}<!--REPOS:END-->", md, flags=re.S)
open("README.md", "w").write(md)
print(f"{login}: {len(repos)} repos, {commits} commits")