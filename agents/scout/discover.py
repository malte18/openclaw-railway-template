#!/usr/bin/env python3
"""
Discover v2 — Broad search to find viral content + creators in a niche.
Runs hashtag/keyword searches, finds viral posts, extracts creator profiles,
seeds them into Scraping Sources.

Usage:
  python3 discover.py --niche "Peptides"
  python3 discover.py --niche "Peptides" --keywords "bpc-157,peptide therapy"
"""

import argparse, json, os, sys, time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.config import APIFY_TOKEN, APIFY_BASE, ANALYSIS_MODEL, MIN_VIEWS_FOR_DISCOVERY
from core.notion import (
    notion_query_all, notion_create_page,
    n_title, n_select, n_url, n_rich_text, n_number, n_checkbox, n_date,
    read_title, read_url,
)
from core.brand import get_niche, get_brand_profile
from core.claude import call_claude
from core.apify import run_apify_actor


# ── AI Search Term Generation ─────────────────────────────────

def generate_discovery_terms(niche_name, brand_keywords=None):
    """Use Claude to generate optimal search/hashtag terms."""
    keyword_context = f"\nExisting niche keywords: {', '.join(brand_keywords[:15])}" if brand_keywords else ""

    prompt = f"""Generate 10 TikTok/Instagram hashtags to find VIRAL content creators in the "{niche_name}" niche.

CRITICAL RULES:
- These are HASHTAG searches on TikTok/Instagram
- Must be HIGHLY SPECIFIC to "{niche_name}" — not generic
- Include: specific product names, scientific terms, niche slang, controversial topics
- Each term should be 1-2 words, no spaces (hashtag format)
- If someone posts with this hashtag, they are DEFINITELY in the {niche_name} niche
{keyword_context}

Return ONLY a comma-separated list, nothing else."""

    text = call_claude(prompt, model=ANALYSIS_MODEL, max_tokens=200)
    if text:
        terms = [t.strip().replace("#", "") for t in text.split(",") if t.strip()]
        print(f"   🤖 AI search terms: {', '.join(terms)}", file=sys.stderr)
        return terms[:10]
    return [niche_name.lower()]


# ── Apify Search ──────────────────────────────────────────────

def search_tiktok_hashtag(hashtag, limit=20):
    tag = hashtag.replace("#", "").strip()
    return run_apify_actor(
        "clockworks~tiktok-scraper",
        {"hashtags": [tag], "resultsPerPage": limit},
        max_polls=36,
    )


def search_instagram_hashtag(hashtag, limit=20):
    tag = hashtag.replace("#", "").strip()
    tag_url = f"https://www.instagram.com/explore/tags/{tag}/"
    return run_apify_actor(
        "apify~instagram-scraper",
        {"directUrls": [tag_url], "resultsLimit": limit},
        max_polls=36,
    )


# ── Extract Creators ──────────────────────────────────────────

def extract_creators(posts, platform):
    """Extract unique creators from scraped posts, sorted by best-performing."""
    creators = {}
    for post in posts:
        if platform == "tiktok":
            am = post.get("authorMeta") or {}
            name = am.get("name", "")
            views = post.get("playCount", 0) or 0
            if name:
                url = f"https://www.tiktok.com/@{name}"
                if name not in creators:
                    creators[name] = {"name": name, "platform": "tiktok", "url": url, "best_views": views, "post_count": 0}
                creators[name]["best_views"] = max(creators[name]["best_views"], views)
                creators[name]["post_count"] += 1
        elif platform == "instagram":
            name = post.get("ownerUsername", "")
            views = post.get("videoViewCount") or post.get("likesCount", 0) or 0
            if name:
                url = f"https://www.instagram.com/{name}/"
                if name not in creators:
                    creators[name] = {"name": name, "platform": "instagram", "url": url, "best_views": views, "post_count": 0}
                creators[name]["best_views"] = max(creators[name]["best_views"], views)
                creators[name]["post_count"] += 1

    filtered = [c for c in creators.values() if c["best_views"] >= MIN_VIEWS_FOR_DISCOVERY]
    filtered.sort(key=lambda x: x["best_views"], reverse=True)
    return filtered


# ── Seed Sources ──────────────────────────────────────────────

def get_existing_sources(ss_db):
    names = set()
    for p in notion_query_all(ss_db):
        name = read_title(p.get("properties", {}), "Name")
        if name:
            names.add(name.lower())
    return names


def seed_creator(ss_db, creator, existing):
    if creator["name"].lower() in existing:
        return False
    props = {
        "Name": n_title(creator["name"]),
        "Platform": n_select(creator["platform"]),
        "Type": n_select("profile"),
        "Source URL": n_url(creator["url"]),
        "Active": n_checkbox(True),
        "Min Views": n_number(1000),
        "Auto Discovered": n_checkbox(True),
    }
    result = notion_create_page(ss_db, props)
    if result:
        existing.add(creator["name"].lower())
        return True
    return False


# ── Main ──────────────────────────────────────────────────────

def run(niche_name, extra_keywords=None):
    missing = [v for v in ["APIFY_TOKEN", "NOTION_API_KEY"] if not os.environ.get(v)]
    if missing:
        print(json.dumps({"error": f"Missing: {', '.join(missing)}"}))
        sys.exit(1)

    niche = get_niche(niche_name)
    if not niche:
        print(json.dumps({"error": f"Niche '{niche_name}' not found."}))
        sys.exit(1)

    ss_db = niche["ss_db"]
    vl_db = niche["vl_db"]

    # Generate search terms
    brand = get_brand_profile(niche_name)
    keywords = generate_discovery_terms(niche_name, brand.get("keywords", []))
    if extra_keywords:
        keywords.extend([k.strip() for k in extra_keywords.split(",") if k.strip()])
    keywords = list(dict.fromkeys(keywords))[:10]

    print(f"🔍 Discovering creators for '{niche_name}' using {len(keywords)} keywords", file=sys.stderr)
    print(f"   Keywords: {', '.join(keywords[:5])}...", file=sys.stderr)

    existing = get_existing_sources(ss_db)
    print(f"   Existing sources: {len(existing)}", file=sys.stderr)

    all_creators = {}
    all_viral_posts = []

    # Search TikTok hashtags
    for kw in keywords[:5]:
        tag = kw.replace(" ", "").replace("#", "")
        print(f"   📡 TikTok #{tag}...", file=sys.stderr)
        raw_posts = search_tiktok_hashtag(tag, limit=10)
        if raw_posts:
            creators = extract_creators(raw_posts, "tiktok")
            for c in creators:
                key = f"{c['name']}_{c['platform']}"
                if key not in all_creators:
                    all_creators[key] = c
            for raw in raw_posts:
                am = raw.get("authorMeta") or {}
                views = raw.get("playCount", 0) or 0
                url = raw.get("webVideoUrl", "")
                if views >= MIN_VIEWS_FOR_DISCOVERY and url:
                    all_viral_posts.append({
                        "platform": "tiktok", "views": views,
                        "likes": raw.get("diggCount", 0) or 0,
                        "comments": raw.get("commentCount", 0) or 0,
                        "text": raw.get("text", ""), "url": url,
                        "creator": am.get("name", "unknown"),
                        "thumbnail": raw.get("videoMeta", {}).get("coverUrl", "") or "",
                    })
            print(f"      Found {len(creators)} creators", file=sys.stderr)
        else:
            print(f"      No results", file=sys.stderr)

    # Search Instagram hashtags
    for kw in keywords[:3]:
        tag = kw.replace(" ", "").replace("#", "")
        print(f"   📡 Instagram #{tag}...", file=sys.stderr)
        raw_posts = search_instagram_hashtag(tag, limit=10)
        if raw_posts:
            creators = extract_creators(raw_posts, "instagram")
            for c in creators:
                key = f"{c['name']}_{c['platform']}"
                if key not in all_creators:
                    all_creators[key] = c
            for raw in raw_posts:
                views = raw.get("videoViewCount") or raw.get("likesCount", 0) or 0
                url = raw.get("url", "")
                if views >= MIN_VIEWS_FOR_DISCOVERY and url:
                    all_viral_posts.append({
                        "platform": "instagram", "views": views,
                        "likes": raw.get("likesCount", 0) or 0,
                        "comments": raw.get("commentsCount", 0) or 0,
                        "text": raw.get("caption", ""), "url": url,
                        "creator": raw.get("ownerUsername", "unknown"),
                        "thumbnail": raw.get("displayUrl", "") or "",
                    })
            print(f"      Found {len(creators)} creators", file=sys.stderr)
        else:
            print(f"      No results", file=sys.stderr)

    print(f"\n   📊 Total: {len(all_viral_posts)} viral posts, {len(all_creators)} unique creators", file=sys.stderr)

    sorted_creators = sorted(all_creators.values(), key=lambda x: x["best_views"], reverse=True)

    # Seed top creators
    seeded = 0
    for creator in sorted_creators[:15]:
        if seed_creator(ss_db, creator, existing):
            seeded += 1
            print(f"   ✅ Source: {creator['name']} ({creator['platform']}) — {creator['best_views']:,} views", file=sys.stderr)

    # Save viral posts to library
    existing_urls = set()
    for page in notion_query_all(vl_db):
        u = read_url(page.get("properties", {}), "URL")
        if u:
            existing_urls.add(u)

    posts_saved = 0
    for post in all_viral_posts:
        if post["url"] in existing_urls:
            continue
        engagement = round((post["likes"] + post["comments"]) / post["views"] * 100, 2) if post["views"] > 0 else 0
        props = {
            "Title": n_title(post["text"][:100] if post["text"] else f"{post['creator']} - {post['views']:,} views"),
            "URL": n_url(post["url"]),
            "Platform": n_select(post["platform"]),
            "Creator": n_rich_text(post["creator"]),
            "Views": n_number(post["views"]),
            "Engagement": n_number(engagement),
            "Status": n_select("Raw"),
            "Scraped At": n_date(datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        }
        if post.get("thumbnail"):
            props["Thumbnail"] = n_url(post["thumbnail"])
        result = notion_create_page(vl_db, props)
        if result:
            posts_saved += 1
            existing_urls.add(post["url"])

    print(f"   📊 Saved {posts_saved} viral posts to library", file=sys.stderr)

    result = {
        "status": "success",
        "niche": niche_name,
        "keywords_searched": len(keywords),
        "creators_found": len(all_creators),
        "creators_seeded": seeded,
        "posts_saved": posts_saved,
        "top_creators": [{"name": c["name"], "platform": c["platform"], "views": c["best_views"]}
                        for c in sorted_creators[:10]],
        "top_posts": [{"creator": p["creator"], "views": p["views"], "url": p["url"]}
                     for p in sorted(all_viral_posts, key=lambda x: x["views"], reverse=True)[:5]],
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--niche", required=True)
    parser.add_argument("--keywords", help="Extra keywords, comma-separated")
    args = parser.parse_args()
    run(args.niche, args.keywords)
