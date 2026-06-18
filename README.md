# SLAM Cricket – Top 16 Table

A live **Top 16 qualification table** that aggregates standings from all 12 SLAM cricket leagues and automatically selects:

- **12 League Winners** – the team ranked 1st in each league
- **4 Wildcards** – the next-best teams across all leagues, ranked by Points then Net Run Rate (NRR)

The page refreshes automatically every 5 minutes and includes a manual **Refresh** button.  
It is published at: **https://plekkala.github.io/slamtable/**

---

## Enabling GitHub Pages (one-time setup)

1. Go to **Settings → Pages** in this repository.
2. Under **Source**, select **GitHub Actions**.
3. Save. The next push to `main` (or a manual workflow trigger) will publish the site.

---

## How it works

| Step | Detail |
|------|--------|
| Fetch | Uses public CORS proxies (`corsproxy.io`, `allorigins.win`) to retrieve each of the 12 league pages from `theslam.play-cricket.com` |
| Parse | Extracts the standings table from the HTML (team name, points, NRR, played/won/lost) |
| Select | Top team per league = 12 automatic qualifiers; best remaining teams by Pts → NRR = 4 wildcards |
| Display | Single ranked table showing league source and qualification type |
| Refresh | Manual button + automatic 5-minute refresh |

## League sources

| # | URL |
|---|-----|
| 1 | https://theslam.play-cricket.com/website/division/138912 |
| 2 | https://theslam.play-cricket.com/website/division/138913 |
| 3 | https://theslam.play-cricket.com/website/division/138917 |
| 4 | https://theslam.play-cricket.com/website/division/138918 |
| 5 | https://theslam.play-cricket.com/website/division/138919 |
| 6 | https://theslam.play-cricket.com/website/division/138921 |
| 7 | https://theslam.play-cricket.com/website/division/138922 |
| 8 | https://theslam.play-cricket.com/website/division/138923 |
| 9 | https://theslam.play-cricket.com/website/division/138924 |
| 10 | https://theslam.play-cricket.com/website/division/138925 |
| 11 | https://theslam.play-cricket.com/website/division/138926 |
| 12 | https://theslam.play-cricket.com/website/division/138927 |
