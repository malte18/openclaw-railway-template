"""
Apify actor runner with polling — extracted from scout.py and discover.py.
"""

import sys
import time

from core.config import APIFY_TOKEN, APIFY_BASE, APIFY_ACTORS
from core.http import http_request


def run_apify_actor(actor_id, input_data, poll_interval=5, max_polls=60):
    """
    Run an Apify actor and wait for results.
    Returns list of items from the dataset, or empty list on failure.
    """
    url = f"{APIFY_BASE}/acts/{actor_id}/runs?token={APIFY_TOKEN}"
    run = http_request(url, method="POST", data=input_data)
    if not run:
        return []

    run_id = run.get("data", {}).get("id")
    if not run_id:
        return []

    poll_url = f"{APIFY_BASE}/actor-runs/{run_id}?token={APIFY_TOKEN}"
    for _ in range(max_polls):
        time.sleep(poll_interval)
        status = http_request(poll_url)
        if not status:
            continue

        state = status.get("data", {}).get("status")
        if state == "SUCCEEDED":
            ds = status.get("data", {}).get("defaultDatasetId")
            if ds:
                items = http_request(f"{APIFY_BASE}/datasets/{ds}/items?token={APIFY_TOKEN}")
                return items if isinstance(items, list) else []
            return []
        elif state in ("FAILED", "ABORTED", "TIMED-OUT"):
            print(f"Actor {run_id}: {state}", file=sys.stderr)
            return []

    print(f"Actor {run_id}: polling timed out", file=sys.stderr)
    return []


def get_actor_id(platform, source_type):
    """Get the Apify actor ID for a platform + source type combo."""
    return APIFY_ACTORS.get(f"{platform}_{source_type}") or APIFY_ACTORS.get(f"{platform}_profile")


def build_tiktok_input(source_type, source_url="", search_term="", limit=5):
    """Build Apify input for TikTok scraping."""
    if source_type == "profile":
        return {"profiles": [source_url], "resultsPerPage": limit}
    elif source_type == "hashtag":
        h = source_url.replace("https://www.tiktok.com/tag/", "").strip("/") or search_term.replace("#", "")
        return {"hashtags": [h], "resultsPerPage": limit}
    elif source_type == "keyword":
        kw = search_term or source_url
        return {"searchQueries": [kw], "resultsPerPage": limit}
    return {"profiles": [source_url], "resultsPerPage": limit}


def build_instagram_input(source_type, source_url="", limit=5):
    """Build Apify input for Instagram scraping."""
    if source_type == "hashtag":
        tag_url = source_url if source_url.startswith("http") else f"https://www.instagram.com/explore/tags/{source_url.replace('#', '')}/"
        return {"directUrls": [tag_url], "resultsLimit": limit}
    return {"directUrls": [source_url], "resultsLimit": limit}


def scrape_source(source, posts_per_source):
    """
    Scrape a single source via Apify.
    Source dict must have: platform, type, source_url, search_term.
    """
    platform = source["platform"]
    stype = source["type"]
    actor_id = get_actor_id(platform, stype)
    if not actor_id:
        return []

    if platform == "tiktok":
        inp = build_tiktok_input(stype, source.get("source_url", ""), source.get("search_term", ""), posts_per_source)
    elif platform == "instagram":
        inp = build_instagram_input(stype, source.get("source_url", ""), posts_per_source)
    else:
        return []

    return run_apify_actor(actor_id, inp)
