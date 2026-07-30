"""
GitHub istatistiklerini GraphQL API'den çeker ve stats-langs.svg dosyasını
gerçek, güncel verilerle yeniden üretir. Kart boyutları/şablonu sabit tutulur,
böylece görsel her zaman eşit yükseklikte kalır.
"""

import os
import sys
import datetime
import requests

USERNAME = os.environ.get("GH_USERNAME", "hamzasisman")
TOKEN = os.environ["GITHUB_TOKEN"]

API_URL = "https://api.github.com/graphql"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# Renk paleti (GitHub'ın resmi dil renkleriyle uyumlu, en yaygın diller için)
LANG_COLORS = {
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "CSS": "#563d7c",
    "SCSS": "#c6538c",
    "HTML": "#e34c26",
    "Java": "#b07219",
    "Ruby": "#701516",
    "Objective-C": "#438eff",
    "Objective-C++": "#6866fb",
    "Python": "#3572A5",
    "C++": "#f34b7d",
    "C#": "#178600",
    "PHP": "#4F5D95",
}
DEFAULT_COLOR = "#8b7bff"


def gql(query, variables=None):
    resp = requests.post(
        API_URL, headers=HEADERS, json={"query": query, "variables": variables or {}}
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


def get_account_created_year():
    query = """
    query($login: String!) {
      user(login: $login) { createdAt }
    }
    """
    data = gql(query, {"login": USERNAME})
    created_at = data["user"]["createdAt"]
    return int(created_at[:4])


def get_total_commits_all_years():
    start_year = get_account_created_year()
    current_year = datetime.datetime.utcnow().year
    total = 0
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          restrictedContributionsCount
        }
      }
    }
    """
    for year in range(start_year, current_year + 1):
        frm = f"{year}-01-01T00:00:00Z"
        to = f"{year}-12-31T23:59:59Z"
        data = gql(query, {"login": USERNAME, "from": frm, "to": to})
        cc = data["user"]["contributionsCollection"]
        total += cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
    return total


def get_prs_issues_stars_and_languages():
    query = """
    query($login: String!, $cursor: String) {
      user(login: $login) {
        pullRequests { totalCount }
        issues { totalCount }
        repositories(first: 100, after: $cursor, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
          totalCount
          pageInfo { hasNextPage endCursor }
          nodes {
            stargazerCount
            languages(first: 6, orderBy: {field: SIZE, direction: DESC}) {
              edges { size node { name } }
            }
          }
        }
      }
    }
    """
    cursor = None
    total_stars = 0
    lang_bytes = {}
    prs = issues = repo_count = 0

    while True:
        data = gql(query, {"login": USERNAME, "cursor": cursor})
        user = data["user"]
        prs = user["pullRequests"]["totalCount"]
        issues = user["issues"]["totalCount"]
        repos = user["repositories"]
        repo_count = repos["totalCount"]

        for node in repos["nodes"]:
            total_stars += node["stargazerCount"]
            for edge in node["languages"]["edges"]:
                name = edge["node"]["name"]
                lang_bytes[name] = lang_bytes.get(name, 0) + edge["size"]

        if repos["pageInfo"]["hasNextPage"]:
            cursor = repos["pageInfo"]["endCursor"]
        else:
            break

    return prs, issues, total_stars, repo_count, lang_bytes


def get_contributed_to_last_year():
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          totalRepositoriesWithContributedCommits
        }
      }
    }
    """
    data = gql(query, {"login": USERNAME})
    return data["user"]["contributionsCollection"]["totalRepositoriesWithContributedCommits"]


def top_languages(lang_bytes, limit=6):
    total = sum(lang_bytes.values()) or 1
    ranked = sorted(lang_bytes.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [(name, size, round(size / total * 100, 2)) for name, size in ranked]


def render_svg(stats, langs):
    total_commits, total_prs, total_issues, total_stars, contributed_to = stats

    # Sağ taraf dil çubuğu: her dil oranına göre genişlik (toplam 430px alan)
    bar_total_width = 430
    bar_x = 540
    bar_segments = []
    x = bar_x
    for i, (name, _, pct) in enumerate(langs):
        w = round(bar_total_width * pct / 100, 2)
        color = LANG_COLORS.get(name, DEFAULT_COLOR)
        radius_attr = ""
        if i == 0:
            radius_attr = 'rx="6"'
        bar_segments.append(f'<rect x="{x}" y="65" width="{w}" height="12" {radius_attr} fill="{color}"/>')
        x += w

    # Legend: 2 sütun, 3 satır (6 dil)
    legend_items = []
    col_x = [546, 750]
    for i, (name, _, pct) in enumerate(langs):
        col = i // 3
        row = i % 3
        cx = col_x[col]
        cy = 103 + row * 30
        color = LANG_COLORS.get(name, DEFAULT_COLOR)
        legend_items.append(
            f'<circle cx="{cx}" cy="{cy}" r="6" fill="{color}"/>'
            f'<text x="{cx+14}" y="{cy+5}">{name} {pct}%</text>'
        )

    svg = f"""<svg viewBox="0 0 1000 260" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="ringGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#4ade80"/>
      <stop offset="100%" stop-color="#22c55e"/>
    </linearGradient>
  </defs>

  <rect x="0" y="0" width="480" height="260" rx="14" fill="#2d1b4e"/>
  <text x="30" y="42" font-family="Segoe UI, Arial, sans-serif" font-size="18" font-weight="700" fill="#b39ddb">{USERNAME}'s GitHub Stats</text>

  <g font-family="Segoe UI, Arial, sans-serif" font-size="15" fill="#e0d5f5">
    <circle cx="34" cy="72" r="5" fill="#f9d94e"/>
    <text x="48" y="77" font-weight="600">Total Stars Earned:</text>
    <text x="260" y="77" font-weight="700">{total_stars}</text>

    <circle cx="34" cy="102" r="5" fill="#c084fc"/>
    <text x="48" y="107" font-weight="600">Total Commits:</text>
    <text x="260" y="107" font-weight="700">{total_commits}</text>

    <circle cx="34" cy="132" r="5" fill="#c084fc"/>
    <text x="48" y="137" font-weight="600">Total PRs:</text>
    <text x="260" y="137" font-weight="700">{total_prs}</text>

    <circle cx="34" cy="162" r="5" fill="#c084fc"/>
    <text x="48" y="167" font-weight="600">Total Issues:</text>
    <text x="260" y="167" font-weight="700">{total_issues}</text>

    <circle cx="34" cy="192" r="5" fill="#c084fc"/>
    <text x="48" y="197" font-weight="600">Contributed to (last year):</text>
    <text x="260" y="197" font-weight="700">{contributed_to}</text>
  </g>

  <circle cx="410" cy="140" r="55" fill="none" stroke="#3d2f66" stroke-width="8"/>
  <circle cx="410" cy="140" r="55" fill="none" stroke="url(#ringGrad)" stroke-width="8"
          stroke-dasharray="290 345" stroke-linecap="round" transform="rotate(-90 410 140)"/>
  <text x="410" y="150" font-family="Segoe UI, Arial, sans-serif" font-size="26" font-weight="800"
        fill="#4ade80" text-anchor="middle">A+</text>

  <rect x="510" y="0" width="490" height="260" rx="14" fill="#2d1b4e"/>
  <text x="540" y="42" font-family="Segoe UI, Arial, sans-serif" font-size="18" font-weight="700" fill="#b39ddb">Most Used Languages</text>

  <g>
    {''.join(bar_segments)}
  </g>

  <g font-family="Segoe UI, Arial, sans-serif" font-size="14.5" fill="#e0d5f5">
    {''.join(legend_items)}
  </g>
</svg>
"""
    return svg


def main():
    total_commits = get_total_commits_all_years()
    total_prs, total_issues, total_stars, repo_count, lang_bytes = get_prs_issues_stars_and_languages()
    contributed_to = get_contributed_to_last_year()
    langs = top_languages(lang_bytes)

    svg = render_svg((total_commits, total_prs, total_issues, total_stars, contributed_to), langs)

    out_path = os.environ.get("OUTPUT_PATH", "stats-langs.svg")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg)

    print(f"Yazıldı: {out_path}")
    print(f"Commits={total_commits} PRs={total_prs} Issues={total_issues} Stars={total_stars} Repos={repo_count}")
    print(f"Diller: {langs}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"HATA: {exc}", file=sys.stderr)
        sys.exit(1)
