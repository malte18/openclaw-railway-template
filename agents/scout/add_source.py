#!/usr/bin/env python3
"""
Add/manage scraping sources in Notion.

Usage:
  python3 add_source.py --niche "Beef Snacks" --name "Chomps" --platform tiktok --type profile --url "https://www.tiktok.com/@chomps"
  python3 add_source.py --niche "Beef Snacks" --list
  python3 add_source.py --niche "Beef Snacks" --deactivate "page_id"
"""

import argparse, json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.notion import (
    notion_query_all, notion_create_page, notion_update_page,
    n_title, n_select, n_url, n_rich_text, n_number, n_checkbox,
    read_title, read_select, read_checkbox,
)
from core.brand import get_niche


def check_duplicate(db_id, name, platform, source_type):
    filter_obj = {"and": [
        {"property": "Name", "title": {"equals": name}},
        {"property": "Platform", "select": {"equals": platform}},
    ]}
    if source_type in ("hashtag", "keyword"):
        filter_obj["and"].append({"property": "Type", "select": {"equals": source_type}})
    result = notion_query_all(db_id, filter_obj)
    return len(result) > 0


def add_source(db_id, name, platform, source_type, url=None, search_term=None, min_views=50000):
    if check_duplicate(db_id, name, platform, source_type):
        print(json.dumps({"status": "duplicate", "message": f"'{name}' already exists."}))
        return

    props = {
        "Name": n_title(name),
        "Platform": n_select(platform),
        "Type": n_select(source_type),
        "Active": n_checkbox(True),
        "Min Views": n_number(min_views),
        "Auto Discovered": n_checkbox(False),
    }
    if url:
        props["Source URL"] = n_url(url)
    if search_term:
        props["Search Term"] = n_rich_text(search_term)

    result = notion_create_page(db_id, props)
    if result:
        print(json.dumps({"status": "added", "name": name, "platform": platform, "type": source_type, "page_id": result["id"]}))
    else:
        print(json.dumps({"status": "error", "message": f"Failed to add {name}"}))


def list_sources(db_id):
    pages = notion_query_all(db_id)
    sources = []
    for page in pages:
        props = page.get("properties", {})
        sources.append({
            "name": read_title(props, "Name"),
            "platform": read_select(props, "Platform"),
            "type": read_select(props, "Type"),
            "active": read_checkbox(props, "Active"),
            "auto_discovered": read_checkbox(props, "Auto Discovered"),
            "page_id": page["id"],
        })
    print(json.dumps({"status": "success", "count": len(sources), "sources": sources}, indent=2))


def deactivate_source(page_id):
    result = notion_update_page(page_id, {"Active": n_checkbox(False)})
    if result:
        print(json.dumps({"status": "deactivated", "page_id": page_id}))
    else:
        print(json.dumps({"status": "error"}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name")
    parser.add_argument("--platform", choices=["tiktok", "instagram"])
    parser.add_argument("--type", choices=["profile", "hashtag", "keyword"], dest="source_type")
    parser.add_argument("--url")
    parser.add_argument("--search-term")
    parser.add_argument("--min-views", type=int, default=50000)
    parser.add_argument("--niche", required=True)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--deactivate")
    args = parser.parse_args()

    niche = get_niche(args.niche)
    if not niche:
        print(json.dumps({"status": "error", "message": f"Niche '{args.niche}' not found."}))
        sys.exit(1)
    db_id = niche["ss_db"]

    if args.list:
        list_sources(db_id)
    elif args.deactivate:
        deactivate_source(args.deactivate)
    elif args.name and args.platform and args.source_type:
        add_source(db_id, args.name, args.platform, args.source_type, args.url, args.search_term, args.min_views)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
