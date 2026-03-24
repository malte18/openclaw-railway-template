#!/usr/bin/env python3
"""
Content Scout v5 — Scrapes TikTok + Instagram via Apify, filters by views + niche keywords,
saves raw entries to Notion Viral Library with Status=Raw.

Refactored: uses core/ modules, zero duplicated code.
"""

import json, os, sys, argparse, fcntl
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.config import (
    LOCK_FILE, PROGRESS_FILE,
    DEFAULT_POSTS_PER_SOURCE, PROFILE_MAX_AGE_DAYS, SEARCH_MAX_AGE_DAYS,
    AUTO_DISCOVER_MIN_VIEWS, MAX_AUTO_DISCOVER_PER_RUN,
)
from core.notion import (
    notion_query_all, notion_create_page, notion_update_page,
    n_title, n_rich_text, n_number, n_select, n_url, n_date, n_relation, n_checkbox,
    read_title, read_text, read_select, read_number, read_url, read_checkbox, read_date,
)
from core.brand import get_all_niches, get_brand_profile
from core.apify import scrape_source


# ── Post Normalization ────────────────────────────────────────

def normalize_post(raw, platform):
    if platform == "tiktok":
        am = raw.get("authorMeta") or {}
        ct = raw.get("createTimeISO") or ""
        if not ct and raw.get("createTime"):
            try:
                ct = datetime.fromtimestamp(int(raw["createTime"]), tz=timezone.utc).isoformat()
            except:
                ct = ""
        return {
            "platform": "tiktok",
            "views": raw.get("playCount", 0) or 0,
            "likes": raw.get("diggCount", 0) or 0,
            "comments": raw.get("commentCount", 0) or 0,
            "shares": raw.get("shareCount", 0) or 0,
            "text": raw.get("text", ""),
            "url": raw.get("webVideoUrl", ""),
            "creator": am.get("name", "unknown"),
            "creator_url": f"https://www.tiktok.com/@{am.get('name', '')}" if am.get("name") else "",
            "thumbnail": raw.get("videoMeta", {}).get("coverUrl", "") or raw.get("covers", {}).get("default", "") or "",
            "created_at": ct,
        }
    elif platform == "instagram":
        views = raw.get("videoViewCount") or raw.get("likesCount") or 0
        creator = raw.get("ownerUsername", "unknown")
        return {
            "platform": "instagram",
            "views": views,
            "likes": raw.get("likesCount", 0) or 0,
            "comments": raw.get("commentsCount", 0) or 0,
            "shares": 0,
            "text": raw.get("caption", ""),
            "url": raw.get("url", ""),
            "creator": creator,
            "creator_url": f"https://www.instagram.com/{creator}/" if creator != "unknown" else "",
            "thumbnail": raw.get("displayUrl", "") or raw.get("previewUrl", "") or "",
            "created_at": raw.get("timestamp", ""),
        }
    return None


def is_within_timeframe(post, source_type):
    created = post.get("created_at", "")
    if not created:
        return True
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except:
        return True
    max_age = timedelta(days=PROFILE_MAX_AGE_DAYS if source_type == "profile" else SEARCH_MAX_AGE_DAYS)
    return (datetime.now(timezone.utc) - dt) <= max_age


def matches_niche_keywords(post, keywords):
    """Lightweight niche filter on caption text."""
    if not keywords:
        return True
    text = (post.get("text", "") + " " + post.get("creator", "")).lower()
    return any(kw.lower() in text for kw in keywords)


# ── Sources ───────────────────────────────────────────────────

def get_active_sources(db_id):
    pages = notion_query_all(db_id, {"property": "Active", "checkbox": {"equals": True}})
    sources = []
    for page in pages:
        props = page.get("properties", {})
        sources.append({
            "page_id": page["id"],
            "name": read_title(props, "Name"),
            "platform": read_select(props, "Platform").lower(),
            "type": read_select(props, "Type").lower() or "profile",
            "source_url": read_url(props, "Source URL"),
            "search_term": read_text(props, "Search Term"),
            "min_views": read_number(props, "Min Views"),
            "last_scraped": read_date(props, "Last Scraped"),
        })
    sources.sort(key=lambda x: x["last_scraped"] or "0000")
    return sources


# ── Dedup + Auto-discover ─────────────────────────────────────

def get_existing_urls(db_id):
    urls = set()
    for page in notion_query_all(db_id):
        u = read_url(page.get("properties", {}), "URL")
        if u:
            urls.add(u)
    return urls


def get_known_creators(db_id):
    creators = set()
    for page in notion_query_all(db_id):
        props = page.get("properties", {})
        name = read_title(props, "Name")
        if name:
            creators.add(name.lower())
        u = read_url(props, "Source URL")
        if u:
            creators.add(u.lower())
    return creators


def auto_discover_creator(post, known, ss_db, count):
    if count >= MAX_AUTO_DISCOVER_PER_RUN:
        return False
    if not post.get("creator") or post["creator"] == "unknown":
        return False
    if not post.get("creator_url"):
        return False
    if post["creator"].lower() in known or post["creator_url"].lower() in known:
        return False
    if post["views"] < AUTO_DISCOVER_MIN_VIEWS:
        return False
    result = notion_create_page(ss_db, {
        "Name": n_title(post["creator"]),
        "Platform": n_select(post["platform"]),
        "Type": n_select("profile"),
        "Source URL": n_url(post["creator_url"]),
        "Active": n_checkbox(False),
        "Min Views": n_number(AUTO_DISCOVER_MIN_VIEWS),
        "Auto Discovered": n_checkbox(True),
    })
    if result:
        known.add(post["creator"].lower())
        known.add(post["creator_url"].lower())
        return True
    return False


# ── Save Raw ──────────────────────────────────────────────────

def save_raw(post, vl_db, source_page_id):
    engagement = round((post["likes"] + post["comments"]) / post["views"] * 100, 2) if post["views"] > 0 else 0
    props = {
        "Title": n_title(post["text"][:100] if post["text"] else f"{post['creator']} - {post['views']:,} views"),
        "URL": n_url(post["url"]),
        "Platform": n_select(post["platform"]),
        "Creator": n_rich_text(post["creator"]),
        "Views": n_number(post["views"]),
        "Engagement": n_number(engagement),
        "Outlier Ratio": n_number(post.get("outlier_ratio", 1.0)),
        "Status": n_select("Raw"),
        "Source": n_relation([source_page_id]),
        "Scraped At": n_date(datetime.now(timezone.utc).strftime("%Y-%m-%d")),
    }
    if post.get("thumbnail"):
        props["Thumbnail"] = n_url(post["thumbnail"])
    return notion_create_page(vl_db, props)


# ── Progress ──────────────────────────────────────────────────

def update_progress(msg, sources_done=0, sources_total=0, posts_found=0):
    progress = {
        "message": msg,
        "sources_done": sources_done,
        "sources_total": sources_total,
        "posts_found": posts_found,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f)
    print(f"  [{sources_done}/{sources_total}] {msg} ({posts_found} posts so far)", file=sys.stderr)


# ── Main ──────────────────────────────────────────────────────

def run(niche_filter=None, posts_per_source=DEFAULT_POSTS_PER_SOURCE, niche_keywords=None):
    # Check if already running
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE) as f:
                lock_data = json.load(f)
            started = lock_data.get("started", "")
            print(json.dumps({"status": "already_running", "message": f"A scrape is already running (started {started})."}))
            sys.exit(0)
        except:
            pass  # stale lock, proceed

    # Create lock
    with open(LOCK_FILE, "w") as f:
        json.dump({"started": datetime.now(timezone.utc).isoformat(), "pid": os.getpid()}, f)

    try:
        _run_inner(niche_filter, posts_per_source, niche_keywords)
    finally:
        try: os.remove(LOCK_FILE)
        except: pass
        try: os.remove(PROGRESS_FILE)
        except: pass


def _run_inner(niche_filter=None, posts_per_source=DEFAULT_POSTS_PER_SOURCE, niche_keywords=None):
    missing = [v for v in ["APIFY_TOKEN", "NOTION_API_KEY"] if not os.environ.get(v)]
    if missing:
        print(json.dumps({"error": f"Missing: {', '.join(missing)}"}))
        sys.exit(1)

    niches = get_all_niches()
    if niche_filter:
        niches = [n for n in niches if n["niche"].lower() == niche_filter.lower()]
    if not niches:
        print(json.dumps({"error": "No active niches found."}))
        sys.exit(1)

    all_results = []
    for niche in niches:
        # Load niche keywords from brand profile if not provided
        keywords = niche_keywords
        if not keywords:
            brand = get_brand_profile(niche["niche"])
            keywords = brand.get("keywords", [])
        result = run_niche(niche, posts_per_source, keywords)
        if result:
            all_results.append(result)

    print(json.dumps({"status": "success", "niches": len(all_results), "results": all_results}, indent=2))


def run_niche(niche, posts_per_source, keywords):
    ss_db, vl_db = niche["ss_db"], niche["vl_db"]
    print(f"\n{'='*40}\n🔍 {niche['niche']}\n{'='*40}", file=sys.stderr)

    sources = get_active_sources(ss_db)
    if not sources:
        print(f"  No active sources", file=sys.stderr)
        return {"niche": niche["niche"], "status": "no_sources"}

    print(f"  {len(sources)} active sources", file=sys.stderr)

    existing_urls = get_existing_urls(vl_db)
    known_creators = get_known_creators(ss_db)
    print(f"  {len(existing_urls)} existing entries, {len(known_creators)} known creators", file=sys.stderr)

    all_posts = []
    sources_scraped = 0

    for idx, source in enumerate(sources):
        update_progress(f"Scraping {source['name']}", idx, len(sources), len(all_posts))
        raw = scrape_source(source, posts_per_source)
        if not raw:
            print(f"    No results", file=sys.stderr)
            continue
        sources_scraped += 1
        count = 0
        for r in raw:
            post = normalize_post(r, source["platform"])
            if not post or not post["url"]:
                continue
            if not is_within_timeframe(post, source["type"]):
                continue
            if post["views"] < source["min_views"]:
                continue
            if post["url"] in existing_urls:
                continue
            if not matches_niche_keywords(post, keywords):
                continue
            post["_source_pid"] = source["page_id"]
            post["_source_type"] = source["type"]
            all_posts.append(post)
            count += 1
        print(f"    {count} posts passed filters", file=sys.stderr)

        notion_update_page(source["page_id"], {"Last Scraped": n_date(datetime.now(timezone.utc).strftime("%Y-%m-%d"))})

    # Calculate outlier scores per creator
    creator_views = {}
    for post in all_posts:
        c = post["creator"]
        if c not in creator_views:
            creator_views[c] = []
        creator_views[c].append(post["views"])

    creator_avg = {}
    for c, views_list in creator_views.items():
        creator_avg[c] = sum(views_list) / len(views_list) if views_list else 1

    for post in all_posts:
        avg = creator_avg.get(post["creator"], 1)
        post["outlier_ratio"] = round(post["views"] / avg, 2) if avg > 0 else 1.0

    # Sort by outlier ratio (most overperforming first), then by views
    all_posts.sort(key=lambda x: (x.get("outlier_ratio", 1), x["views"]), reverse=True)
    print(f"\n  📊 {len(all_posts)} total posts to save", file=sys.stderr)

    for p in all_posts[:5]:
        print(f"    🔥 {p['creator']} | {p['views']:,} views | {p['outlier_ratio']}x outlier", file=sys.stderr)

    # Save all as Raw
    saved = 0
    discovered = 0
    for post in all_posts:
        result = save_raw(post, vl_db, post["_source_pid"])
        if result:
            saved += 1
            existing_urls.add(post["url"])
        if post.get("_source_type") in ("hashtag", "keyword"):
            if auto_discover_creator(post, known_creators, ss_db, discovered):
                discovered += 1

    print(f"  ✅ Saved {saved} raw entries, discovered {discovered} creators", file=sys.stderr)

    return {
        "niche": niche["niche"], "status": "success",
        "sources_active": len(sources), "sources_scraped": sources_scraped,
        "posts_found": len(all_posts), "posts_saved": saved,
        "creators_discovered": discovered,
        "top_5": [{"creator": p["creator"], "views": p["views"], "url": p["url"]} for p in all_posts[:5]],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--niche", help="Specific niche to scrape")
    parser.add_argument("--posts-per-source", type=int, default=DEFAULT_POSTS_PER_SOURCE)
    parser.add_argument("--keywords", nargs="*", help="Niche keywords for caption filtering")
    args = parser.parse_args()
    run(niche_filter=args.niche, posts_per_source=args.posts_per_source, niche_keywords=args.keywords)
