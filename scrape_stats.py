"""
Play-Cricket Statistics Scraper
================================
Fetches batting and bowling statistics for Divisions 1–4 from
https://sdl.play-cricket.com/Statistics

Usage:
    pip install -r requirements.txt
    python scrape_stats.py

Output:
    data/batting_div{1..4}.csv
    data/bowling_div{1..4}.csv
    data/all_batting.csv
    data/all_bowling.csv
    data/multi_division_players.csv
"""

import os
import time
import logging
import re
import unicodedata

import requests
import pandas as pd
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

BASE_URL = "https://sdl.play-cricket.com"
STATS_URL = f"{BASE_URL}/Statistics"

# Division identifiers used as query parameters on the site.
# Inspect Network tab in your browser to confirm the exact parameter names
# and values; update DIVISIONS below if they differ.
DIVISIONS = {
    1: "Division 1",
    2: "Division 2",
    3: "Division 3",
    4: "Division 4",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.5",
    "Referer": STATS_URL,
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

OUTPUT_DIR = "data"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalise_name(name: str) -> str:
    """Lowercase, strip accents, collapse whitespace and punctuation."""
    if not name:
        return ""
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.lower()
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def get_page(url: str, params: dict = None, retries: int = 3) -> requests.Response:
    for attempt in range(1, retries + 1):
        try:
            resp = SESSION.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            log.warning("Attempt %d/%d failed for %s: %s", attempt, retries, url, exc)
            if attempt < retries:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed to fetch {url} after {retries} attempts")


# ---------------------------------------------------------------------------
# API / endpoint discovery
# ---------------------------------------------------------------------------

def discover_endpoints() -> dict:
    """
    Load the Statistics page and look for API endpoints / form parameters.

    Play-Cricket pages are often JavaScript-heavy. This function tries:
      1. Static HTML table parsing.
      2. Detecting XHR/fetch endpoints embedded in <script> tags.
    Returns a dict with keys 'batting_url', 'bowling_url', 'div_param',
    'stat_param' filled in where discoverable.
    """
    log.info("Loading statistics page to discover endpoints …")
    resp = get_page(STATS_URL)
    soup = BeautifulSoup(resp.text, "html.parser")

    info = {
        "batting_url": None,
        "bowling_url": None,
        "div_param": None,
        "stat_param": None,
        "raw_html": resp.text,
    }

    # Look for AJAX endpoint patterns in inline scripts
    script_texts = " ".join(s.get_text() for s in soup.find_all("script"))
    for pattern in [
        r"(https?://[^\s\"']+(?:batting|stats|statistics)[^\s\"']*)",
        r"(https?://[^\s\"']+(?:bowling)[^\s\"']*)",
        r"[\"'](/api/[^\s\"']+)[\"']",
        r"[\"'](/Statistics[^\s\"']*)[\"']",
    ]:
        matches = re.findall(pattern, script_texts, re.IGNORECASE)
        for m in matches:
            url = m if m.startswith("http") else BASE_URL + m
            log.info("  Candidate endpoint: %s", url)
            if "batting" in url.lower() and not info["batting_url"]:
                info["batting_url"] = url
            elif "bowling" in url.lower() and not info["bowling_url"]:
                info["bowling_url"] = url

    return info


# ---------------------------------------------------------------------------
# Table parsing
# ---------------------------------------------------------------------------

def parse_html_table(soup: BeautifulSoup, stat_type: str, division: int) -> pd.DataFrame:
    """Extract the first matching HTML table from a BeautifulSoup object."""
    tables = soup.find_all("table")
    if not tables:
        log.warning("No <table> elements found for division %d %s.", division, stat_type)
        return pd.DataFrame()

    frames = []
    for table in tables:
        try:
            df = pd.read_html(str(table))[0]
            df["division"] = division
            df["stat_type"] = stat_type
            frames.append(df)
        except Exception as exc:
            log.debug("Could not parse table: %s", exc)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_stat_page(stat_type: str, division: int, extra_params: dict = None) -> pd.DataFrame:
    """
    Fetch one statistics page (batting or bowling) for a given division.

    The function tries several common query-parameter patterns seen on
    Play-Cricket sites. Adjust PARAM_CANDIDATES if your league uses
    different parameter names.
    """
    PARAM_CANDIDATES = [
        # pattern 1: type + division as separate params
        {"type": stat_type, "division": division},
        # pattern 2: stat + div
        {"stat": stat_type, "div": division},
        # pattern 3: season param with division filter
        {"StatisticsType": stat_type, "DivisionId": division},
        # pattern 4: category + league_division
        {"category": stat_type, "league_division": division},
    ]

    all_frames = []
    succeeded = False

    for params in PARAM_CANDIDATES:
        if extra_params:
            params = {**params, **extra_params}
        log.info("  Trying params %s …", params)
        try:
            resp = get_page(STATS_URL, params=params)
            soup = BeautifulSoup(resp.text, "html.parser")
            df = parse_html_table(soup, stat_type, division)
            if not df.empty:
                all_frames.append(df)
                succeeded = True
                log.info("    → %d rows retrieved.", len(df))
                break
        except Exception as exc:
            log.debug("    Param set failed: %s", exc)

    if not succeeded:
        log.warning(
            "Could not retrieve %s stats for division %d with any parameter set. "
            "Check the browser Network tab and update PARAM_CANDIDATES.",
            stat_type,
            division,
        )

    return pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame()


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def fetch_all_pages(stat_type: str, division: int) -> pd.DataFrame:
    """Collect all paginated results for a stat type / division."""
    all_frames = []
    page = 1
    while True:
        log.info("Fetching %s / division %d / page %d …", stat_type, division, page)
        df = fetch_stat_page(stat_type, division, extra_params={"page": page})
        if df.empty:
            break
        all_frames.append(df)
        # Stop if this page has fewer rows than a full page (heuristic: 25 rows)
        if len(df) < 25:
            break
        page += 1
        time.sleep(0.5)  # polite crawl delay

    return pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame()


# ---------------------------------------------------------------------------
# Cross-division player matching
# ---------------------------------------------------------------------------

PLAYER_COL_CANDIDATES = ["Player", "Name", "Batsman", "Bowler", "player_name"]
CLUB_COL_CANDIDATES = ["Club", "Team", "club_name", "team_name", "Side"]


def find_col(df: pd.DataFrame, candidates: list) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
        for col in df.columns:
            if col.lower() == c.lower():
                return col
    return None


def add_normalised_name(df: pd.DataFrame) -> pd.DataFrame:
    player_col = find_col(df, PLAYER_COL_CANDIDATES)
    if player_col:
        df["normalised_name"] = df[player_col].astype(str).apply(normalise_name)
    else:
        log.warning("No player name column found in dataframe. Columns: %s", list(df.columns))
        df["normalised_name"] = "unknown"
    return df


def find_multi_division_players(batting: pd.DataFrame, bowling: pd.DataFrame) -> pd.DataFrame:
    """
    Identify players who appear in more than one division.
    Returns a summary dataframe.
    """
    frames = []
    for df, stat in [(batting, "batting"), (bowling, "bowling")]:
        if df.empty:
            continue
        df = add_normalised_name(df)
        player_col = find_col(df, PLAYER_COL_CANDIDATES) or "normalised_name"
        club_col = find_col(df, CLUB_COL_CANDIDATES)
        cols = {"normalised_name", "division", player_col}
        if club_col:
            cols.add(club_col)
        sub = df[list(cols)].drop_duplicates()
        sub["stat_type"] = stat
        frames.append(sub)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    divisions_per_player = (
        combined.groupby("normalised_name")["division"]
        .nunique()
        .reset_index(name="num_divisions")
    )
    multi = divisions_per_player[divisions_per_player["num_divisions"] > 1]
    return multi.sort_values("num_divisions", ascending=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Optionally discover endpoints first
    info = discover_endpoints()
    log.info("Endpoint discovery complete.")

    batting_frames = []
    bowling_frames = []

    for div_id in DIVISIONS:
        log.info("=== Division %d ===", div_id)

        bat_df = fetch_all_pages("batting", div_id)
        bowl_df = fetch_all_pages("bowling", div_id)

        if not bat_df.empty:
            out = os.path.join(OUTPUT_DIR, f"batting_div{div_id}.csv")
            bat_df.to_csv(out, index=False)
            log.info("Saved %s (%d rows)", out, len(bat_df))
            batting_frames.append(bat_df)
        else:
            log.warning("No batting data for division %d.", div_id)

        if not bowl_df.empty:
            out = os.path.join(OUTPUT_DIR, f"bowling_div{div_id}.csv")
            bowl_df.to_csv(out, index=False)
            log.info("Saved %s (%d rows)", out, len(bowl_df))
            bowling_frames.append(bowl_df)
        else:
            log.warning("No bowling data for division %d.", div_id)

    # Combined datasets
    all_batting = pd.concat(batting_frames, ignore_index=True) if batting_frames else pd.DataFrame()
    all_bowling = pd.concat(bowling_frames, ignore_index=True) if bowling_frames else pd.DataFrame()

    if not all_batting.empty:
        all_batting.to_csv(os.path.join(OUTPUT_DIR, "all_batting.csv"), index=False)
    if not all_bowling.empty:
        all_bowling.to_csv(os.path.join(OUTPUT_DIR, "all_bowling.csv"), index=False)

    # Multi-division players
    multi = find_multi_division_players(all_batting, all_bowling)
    if not multi.empty:
        out = os.path.join(OUTPUT_DIR, "multi_division_players.csv")
        multi.to_csv(out, index=False)
        log.info("Multi-division player summary saved to %s", out)
        print("\n=== Multi-division players ===")
        print(multi.to_string(index=False))
    else:
        log.warning(
            "No multi-division players found (or no data was retrieved). "
            "This is likely because the site requires JavaScript to render tables. "
            "See README for manual steps."
        )

    log.info("Done. Output files are in ./%s/", OUTPUT_DIR)


if __name__ == "__main__":
    main()
