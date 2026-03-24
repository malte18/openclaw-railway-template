#!/usr/bin/env python3
"""
Show top analyzed posts from a niche's Viral Library. Read-only.

Usage:
  python3 top.py --niche "Beef Snacks"
  python3 top.py --niche "Beef Snacks" --limit 5 --sort outlier
"""

import argparse, json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.notion import (
    notion_query_all,
    read_title, read_text, read_select, read_number, read_url,
)
from core.brand import get_niche


def get_top(niche_name, limit=5, sort_by="views"):
    niche = get_niche(niche_name)
    if not niche:
        print(json.dumps({"error": f"Niche '{niche_name}' not found."}))
        return

    vl_db = niche["vl_db"]
    pages = notion_query_all(vl_db, {"property": "Status", "select": {"equals": "Analyzed"}})

    posts = []
    for p in pages:
        pr = p["properties"]
        posts.append({
            "title": read_title(pr, "Title"),
            "url": read_url(pr, "URL"),
            "creator": read_text(pr, "Creator"),
            "views": read_number(pr, "Views"),
            "engagement": read_number(pr, "Engagement"),
            "outlier_ratio": read_number(pr, "Outlier Ratio"),
            "relevance_score": read_number(pr, "Relevance Score"),
            "hook": read_text(pr, "Hook"),
            "hook_type": read_select(pr, "Hook Type"),
            "content_format": read_select(pr, "Content Format"),
            "visual_style": read_select(pr, "Visual Style"),
            "persona": read_select(pr, "Persona"),
            "why_viral": read_text(pr, "Why Viral"),
            "adaptation": read_text(pr, "Adaptation Idea"),
        })

    if sort_by == "outlier":
        posts.sort(key=lambda x: x["outlier_ratio"], reverse=True)
    else:
        posts.sort(key=lambda x: x["views"], reverse=True)

    shown = posts[:limit]
    print(f"🏆 Top {len(shown)} Analyzed Posts — {niche_name} ({len(posts)} total analyzed)\n")
    for i, p in enumerate(shown, 1):
        outlier = f" | 🔥 {p['outlier_ratio']}x outlier" if p.get("outlier_ratio", 0) >= 2 else ""
        print(f"{i}. @{p['creator']} — {p['views']:,} views (score {p['relevance_score']}/10){outlier}")
        print(f"   🪝 Hook: \"{p['hook'][:100]}\"")
        print(f"   🎬 Format: {p['content_format']} | Style: {p['visual_style']} | Persona: {p['persona']}")
        print(f"   🔗 {p['url']}")
        print(f"   💡 {p['adaptation'][:150]}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--niche", required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--sort", choices=["views", "outlier"], default="views")
    args = parser.parse_args()
    get_top(args.niche, args.limit, args.sort)
