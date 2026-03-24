#!/usr/bin/env python3
"""
Niche Manager v2 — create, list, get, delete niches.
FIX: Uses core/ modules, niche-agnostic personas.

Usage:
  python3 niche.py --list
  python3 niche.py --create "Skin Care"
  python3 niche.py --get "Beef Snacks"
  python3 niche.py --delete "Beef Snacks"
"""

import argparse, json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.config import (
    NICHE_REGISTRY_DB, BRAND_PROFILE_DB, PARENT_PAGE, ANALYSIS_MODEL,
)
from core.notion import (
    notion_query_all, notion_create_page, notion_update_page, notion_archive_page,
    notion_create_database, notion_update_database,
    n_title, n_rich_text, n_select, n_checkbox, n_number,
    read_title, read_text, read_select, read_checkbox,
)
from core.http import http_request
from core.claude import call_claude


# ── AI Generation ─────────────────────────────────────────────

def generate_niche_keywords(niche_name):
    """Generate niche-specific filter keywords using Claude."""
    prompt = f"""Generate a comma-separated list of 30-50 keywords for filtering social media content in the "{niche_name}" niche.

Rules:
- Keywords must be SPECIFIC to this niche, not generic
- Include: product names, ingredient names, brand names, creator names, diet/lifestyle terms
- Each keyword should be lowercase
- Think: what words would ONLY appear in content about "{niche_name}"?

Return ONLY the comma-separated list, nothing else."""

    text = call_claude(prompt, model=ANALYSIS_MODEL, max_tokens=500)
    return text.strip() if text else niche_name.lower()


def generate_starter_sources(niche_name):
    """Generate starter scraping sources for a new niche."""
    prompt = f"""Generate starter scraping sources for discovering viral social media content in the "{niche_name}" niche.

Return ONLY a valid JSON array. Each source must have:
- "name": the EXACT social media handle or hashtag
- "platform": "tiktok" or "instagram"
- "type": "profile", "hashtag", or "keyword"
- "url": full URL for profiles, empty "" for hashtags/keywords
- "search_term": for keyword type only, "" otherwise
- "min_views": 1000 for profiles, 5000 for hashtags/keywords

IMPORTANT: Focus on HASHTAGS and KEYWORDS first (8-10). Only add profiles you are SURE exist (3-5 max).
Only return the JSON array, nothing else."""

    from core.claude import call_claude_json
    return call_claude_json(prompt, model=ANALYSIS_MODEL, max_tokens=2000) or []


def seed_sources(ss_db, sources):
    added = 0
    for s in sources:
        props = {
            "Name": n_title(s["name"]),
            "Platform": n_select(s["platform"]),
            "Type": n_select(s["type"]),
            "Active": n_checkbox(True),
            "Min Views": n_number(s.get("min_views", 1000)),
            "Auto Discovered": n_checkbox(False),
        }
        if s.get("url"):
            props["Source URL"] = {"url": s["url"]}
        if s.get("search_term"):
            props["Search Term"] = n_rich_text(s["search_term"])

        result = notion_create_page(ss_db, props)
        if result:
            added += 1
            print(f"  ✅ {s['name']} ({s['platform']}/{s['type']})", file=sys.stderr)
    return added


# ── CRUD Operations ───────────────────────────────────────────

def list_niches():
    pages = notion_query_all(NICHE_REGISTRY_DB)
    niches = []
    for page in pages:
        props = page["properties"]
        niches.append({
            "niche": read_title(props, "Niche"),
            "active": read_checkbox(props, "Active"),
            "scraping_sources_db": read_text(props, "Scraping Sources DB"),
            "viral_library_db": read_text(props, "Viral Library DB"),
            "content_pipeline_db": read_text(props, "Content Pipeline DB"),
            "page_id": page["id"],
        })
    print(json.dumps({"status": "success", "niches": niches}, indent=2))


def get_niche_info(name):
    pages = notion_query_all(NICHE_REGISTRY_DB, {"property": "Niche", "title": {"equals": name}})
    if not pages:
        print(json.dumps({"status": "not_found", "niche": name}))
        return
    props = pages[0]["properties"]
    print(json.dumps({
        "status": "found",
        "niche": name,
        "active": read_checkbox(props, "Active"),
        "scraping_sources_db": read_text(props, "Scraping Sources DB"),
        "viral_library_db": read_text(props, "Viral Library DB"),
        "content_pipeline_db": read_text(props, "Content Pipeline DB"),
    }, indent=2))


def create_niche(name):
    """Create a full niche setup: page + 3 databases + registry entry + brand profile."""
    print(f"Creating niche: {name}", file=sys.stderr)

    # Create niche sub-page
    page = notion_create_page.__wrapped__(PARENT_PAGE, {"title": n_title(name)}) if hasattr(notion_create_page, '__wrapped__') else None
    # Use raw Notion API for page creation under a page (not a database)
    from core.notion import notion_headers
    page = http_request(
        f"https://api.notion.com/v1/pages", method="POST",
        data={"parent": {"page_id": PARENT_PAGE}, "properties": {"title": n_title(name)}},
        headers=notion_headers(),
    )
    if not page:
        print(json.dumps({"status": "error", "message": "Failed to create page"}))
        return
    page_id = page["id"]

    # Create Scraping Sources DB
    ss = notion_create_database(page_id, "Scraping Sources", {
        "Name": {"title": {}},
        "Platform": {"select": {"options": [{"name": "tiktok", "color": "blue"}, {"name": "instagram", "color": "pink"}]}},
        "Type": {"select": {"options": [{"name": "profile", "color": "green"}, {"name": "hashtag", "color": "orange"}, {"name": "keyword", "color": "yellow"}]}},
        "Source URL": {"url": {}},
        "Search Term": {"rich_text": {}},
        "Active": {"checkbox": {}},
        "Min Views": {"number": {"format": "number"}},
        "Auto Discovered": {"checkbox": {}},
        "Last Scraped": {"date": {}},
    })
    ss_id = ss["id"] if ss else "FAILED"

    # Create Viral Library DB
    vl = notion_create_database(page_id, "Viral Content Library", {
        "Title": {"title": {}},
        "URL": {"url": {}},
        "Platform": {"select": {"options": [{"name": "tiktok", "color": "blue"}, {"name": "instagram", "color": "pink"}]}},
        "Creator": {"rich_text": {}},
        "Views": {"number": {"format": "number"}},
        "Engagement": {"number": {"format": "percent"}},
        "Status": {"select": {"options": [
            {"name": "Raw", "color": "gray"}, {"name": "Relevant", "color": "blue"},
            {"name": "Rejected", "color": "red"}, {"name": "Analyzed", "color": "green"},
            {"name": "Scripted", "color": "purple"},
        ]}},
        "Relevance Score": {"number": {"format": "number"}},
        "Hook": {"rich_text": {}},
        "Hook Type": {"select": {"options": [
            {"name": "curiosity", "color": "purple"}, {"name": "social_proof", "color": "blue"},
            {"name": "bold_claim", "color": "red"}, {"name": "transformation", "color": "green"},
            {"name": "controversy", "color": "orange"}, {"name": "question", "color": "yellow"},
        ]}},
        "Content Format": {"select": {"options": [
            {"name": "taste_test", "color": "orange"}, {"name": "review", "color": "blue"},
            {"name": "day_in_life", "color": "green"}, {"name": "educational", "color": "purple"},
            {"name": "asmr_unboxing", "color": "pink"}, {"name": "transformation", "color": "yellow"},
            {"name": "recipe", "color": "red"}, {"name": "comparison", "color": "default"},
            {"name": "ugc_testimonial", "color": "brown"}, {"name": "challenge", "color": "blue"},
            {"name": "other", "color": "gray"},
        ]}},
        "Structure": {"rich_text": {}},
        "Visual Style": {"select": {"options": [
            {"name": "talking_head", "color": "blue"}, {"name": "broll_heavy", "color": "green"},
            {"name": "text_overlay", "color": "orange"}, {"name": "split_screen", "color": "purple"},
            {"name": "pov", "color": "pink"}, {"name": "mixed", "color": "gray"},
        ]}},
        "Persona": {"select": {}},
        "Theme": {"rich_text": {}},
        "Why Viral": {"rich_text": {}},
        "Adaptation Idea": {"rich_text": {}},
        "Scraped At": {"date": {}},
        "Outlier Ratio": {"number": {"format": "number"}},
        "Thumbnail": {"url": {}},
    })
    vl_id = vl["id"] if vl else "FAILED"

    # Add Source relation
    if ss and vl:
        notion_update_database(vl_id, {"Source": {"relation": {"database_id": ss_id, "single_property": {}}}})

    # Create Content Pipeline DB
    cp = notion_create_database(page_id, "Content Pipeline", {
        "Title": {"title": {}},
        "Status": {"select": {"options": [
            {"name": "Script Draft", "color": "gray"}, {"name": "Script Approved", "color": "blue"},
            {"name": "Audio", "color": "purple"}, {"name": "Video", "color": "orange"},
            {"name": "Review", "color": "yellow"}, {"name": "Revision", "color": "red"},
            {"name": "Approved", "color": "green"}, {"name": "Posted", "color": "default"},
        ]}},
        "Script": {"rich_text": {}},
        "Hook": {"rich_text": {}},
        "Format": {"rich_text": {}},
        "Persona": {"rich_text": {}},
        "Audio URL": {"url": {}},
        "Video URL": {"url": {}},
        "Notes": {"rich_text": {}},
        "Created At": {"date": {}},
    })
    cp_id = cp["id"] if cp else "FAILED"

    # Add Viral Source relation
    if vl and cp:
        notion_update_database(cp_id, {"Viral Source": {"relation": {"database_id": vl_id, "single_property": {}}}})

    # Generate niche keywords
    keywords = generate_niche_keywords(name)

    # Create Brand Profile entry
    notion_create_page(BRAND_PROFILE_DB, {
        "Brand Name": n_title(name),
        "Niche": n_rich_text(name),
        "Keywords": n_rich_text(keywords),
        "Niche ID": n_rich_text(name.lower().replace(" ", "-")),
    })
    print(f"  Keywords: {keywords[:100]}...", file=sys.stderr)

    # Register in Niche Registry
    notion_create_page(NICHE_REGISTRY_DB, {
        "Niche": n_title(name),
        "Active": n_checkbox(True),
        "Scraping Sources DB": n_rich_text(ss_id),
        "Viral Library DB": n_rich_text(vl_id),
        "Content Pipeline DB": n_rich_text(cp_id),
        "Brand Profile ID": n_rich_text(BRAND_PROFILE_DB),
        "Page ID": n_rich_text(page_id),
    })

    # Auto-seed starter sources
    print(f"\n  Generating starter sources...", file=sys.stderr)
    starter_sources = generate_starter_sources(name)
    sources_added = seed_sources(ss_id, starter_sources) if starter_sources else 0
    print(f"  Added {sources_added} starter sources", file=sys.stderr)

    print(json.dumps({
        "status": "created", "niche": name, "page_id": page_id,
        "scraping_sources_db": ss_id, "viral_library_db": vl_id,
        "content_pipeline_db": cp_id,
        "keywords_generated": len(keywords.split(",")),
        "sources_seeded": sources_added,
    }, indent=2))


def delete_niche(name):
    """Delete a niche: archive registry entry, brand profile, and niche page."""
    print(f"Deleting niche: {name}", file=sys.stderr)

    pages = notion_query_all(NICHE_REGISTRY_DB, {"property": "Niche", "title": {"equals": name}})
    if not pages:
        print(json.dumps({"status": "not_found", "message": f"Niche '{name}' not found."}))
        return

    reg_page = pages[0]
    props = reg_page["properties"]
    page_id = read_text(props, "Page ID")

    # Archive the niche page (cascades to child databases)
    if page_id:
        notion_archive_page(page_id)
        print(f"  Archived niche page", file=sys.stderr)

    # Archive registry entry
    notion_archive_page(reg_page["id"])
    print(f"  Archived registry entry", file=sys.stderr)

    # Archive brand profile entry
    bp_pages = notion_query_all(BRAND_PROFILE_DB)
    for bp in bp_pages:
        bp_props = bp.get("properties", {})
        bp_name = read_title(bp_props, "Brand Name")
        bp_niche_id = read_text(bp_props, "Niche ID")
        if bp_name.lower() == name.lower() or bp_niche_id.lower() == name.lower().replace(" ", "-"):
            notion_archive_page(bp["id"])
            print(f"  Archived brand profile", file=sys.stderr)
            break

    print(json.dumps({"status": "deleted", "niche": name}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--get", help="Get niche by name")
    parser.add_argument("--create", help="Create new niche")
    parser.add_argument("--delete", help="Delete a niche")
    args = parser.parse_args()

    if args.list:
        list_niches()
    elif args.get:
        get_niche_info(args.get)
    elif args.create:
        create_niche(args.create)
    elif args.delete:
        delete_niche(args.delete)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
