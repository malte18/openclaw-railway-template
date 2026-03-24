#!/usr/bin/env python3
"""
Content Analyst v2 — Analyzes raw Viral Library entries with Claude.
Filters for relevance, then deep-analyzes relevant posts.

FIX: Now queries only Raw posts (not all posts) — huge perf improvement at scale.
FIX: Updated model to claude-3-5-haiku.
FIX: Personas are niche-agnostic (no more hardcoded beef snack personas).

Usage:
  python3 analyze.py --niche "Beef Snacks" --run
  python3 analyze.py --niche "Beef Snacks" --limit 10 --run
  python3 analyze.py --niche "Beef Snacks" --relevance-only --run
  python3 analyze.py --niche "Beef Snacks"  (default: show top results)
"""

import json, os, sys, argparse
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.config import ANALYSIS_MODEL, RELEVANCE_THRESHOLD, DEFAULT_ANALYSIS_LIMIT
from core.notion import (
    notion_query_all, notion_update_page,
    n_rich_text, n_number, n_select,
    read_title, read_text, read_select, read_number, read_url,
)
from core.brand import get_niche, get_brand_profile
from core.claude import call_claude_json


# ── Get Raw Posts (FIXED: filter at query level) ──────────────

def get_raw_posts(vl_db, limit):
    """Get only Raw posts — not ALL posts. Massive perf improvement."""
    pages = notion_query_all(vl_db, {"property": "Status", "select": {"equals": "Raw"}})
    posts = []
    for page in pages:
        props = page.get("properties", {})
        posts.append({
            "page_id": page["id"],
            "title": read_title(props, "Title"),
            "url": read_url(props, "URL"),
            "platform": read_select(props, "Platform"),
            "creator": read_text(props, "Creator"),
            "views": read_number(props, "Views"),
            "engagement": read_number(props, "Engagement"),
            "outlier_ratio": read_number(props, "Outlier Ratio"),
            "thumbnail": read_url(props, "Thumbnail"),
        })
    # Sort by outlier ratio first, then views
    posts.sort(key=lambda x: (x.get("outlier_ratio", 0), x["views"]), reverse=True)
    return posts[:limit]


# ── Claude Analysis ───────────────────────────────────────────

def score_relevance(post, niche_name, brand_ctx):
    """Quick relevance scoring with Haiku."""
    brand_desc = brand_ctx.get("niche", niche_name)

    prompt = f"""Score this social media post's relevance to the "{niche_name}" niche on a scale of 1-10.

Niche/brand context: {brand_desc}

Post:
- Creator: {post['creator']}
- Platform: {post['platform']}
- Views: {post['views']:,}
- Caption: {post['title'][:500]}
- URL: {post['url']}

Return ONLY a JSON object:
{{"score": <1-10>, "reason": "<one sentence why>"}}

Score guide:
- 8-10: Directly about products/topics core to this niche
- 6-7: Closely related content that this niche's audience would love
- 4-5: Loosely related, could work but not a strong fit
- 1-3: Not related to this niche at all

Be GENEROUS with 6-7. Think like a content strategist for a brand in this niche.
Note: Posts with high outlier ratios (3x+ their creator's average) are especially interesting."""

    return call_claude_json(prompt, model=ANALYSIS_MODEL, max_tokens=150)


def deep_analyze(post, niche_name, brand_ctx):
    """Deep analysis — extracts replicable patterns. Niche-agnostic personas."""
    brand_desc = brand_ctx.get("niche", niche_name)
    language = brand_ctx.get("language", "English")

    outlier_note = ""
    if post.get("outlier_ratio", 0) >= 2:
        outlier_note = f"\n- OUTLIER: This post got {post['outlier_ratio']}x the creator's average views."

    thumbnail_note = ""
    if post.get("thumbnail"):
        thumbnail_note = f"\n- Thumbnail URL: {post['thumbnail']}"

    prompt = f"""Analyze this viral {post['platform']} post for a brand in the "{niche_name}" niche.
Brand context: {brand_desc}
Extract patterns a content creator could replicate.

Post:
- Creator: {post['creator']}
- Views: {post['views']:,}
- Engagement: {post['engagement']}%
- Caption: {post['title'][:500]}
- URL: {post['url']}{outlier_note}{thumbnail_note}

Return ONLY valid JSON:
{{
  "hook": "<exact opening hook or first line>",
  "hook_type": "<curiosity|social_proof|bold_claim|transformation|controversy|question>",
  "content_format": "<taste_test|review|day_in_life|educational|asmr_unboxing|transformation|recipe|comparison|ugc_testimonial|challenge|other>",
  "structure": "<describe the video structure: hook → what happens → ending/CTA>",
  "visual_style": "<talking_head|broll_heavy|text_overlay|split_screen|pov|mixed>",
  "persona": "<describe the target audience persona for this niche in 2-3 words>",
  "why_viral": "<2 sentences: what psychological trigger makes this work>",
  "adaptation_brief": "<2-3 sentences: exactly how to remake this for a brand in this niche, specific product tie-in>"
}}

All text fields in {language}."""

    return call_claude_json(prompt, model=ANALYSIS_MODEL, max_tokens=800)


# ── Update Notion ─────────────────────────────────────────────

def mark_rejected(page_id, score, reason):
    notion_update_page(page_id, {
        "Status": n_select("Rejected"),
        "Relevance Score": n_number(score),
        "Theme": n_rich_text(reason),
    })


def mark_analyzed(page_id, score, analysis):
    props = {
        "Status": n_select("Analyzed"),
        "Relevance Score": n_number(score),
        "Hook": n_rich_text(analysis.get("hook", "")),
        "Hook Type": n_select(analysis.get("hook_type", "curiosity")),
        "Content Format": n_select(analysis.get("content_format", "other")),
        "Structure": n_rich_text(analysis.get("structure", "")),
        "Visual Style": n_select(analysis.get("visual_style", "mixed")),
        "Persona": n_select(analysis.get("persona", "General")),
        "Why Viral": n_rich_text(analysis.get("why_viral", "")),
        "Adaptation Idea": n_rich_text(analysis.get("adaptation_brief", "")),
    }
    notion_update_page(page_id, props)


# ── Main ──────────────────────────────────────────────────────

def run(niche_name, limit=DEFAULT_ANALYSIS_LIMIT, relevance_only=False):
    missing = [v for v in ["ANTHROPIC_API_KEY", "NOTION_API_KEY"] if not os.environ.get(v)]
    if missing:
        print(json.dumps({"error": f"Missing: {', '.join(missing)}"}))
        sys.exit(1)

    niche = get_niche(niche_name)
    if not niche:
        print(json.dumps({"error": f"Niche '{niche_name}' not found."}))
        sys.exit(1)

    vl_db = niche["vl_db"]
    brand_ctx = get_brand_profile(niche_name)
    print(f"🏷️ Brand: {brand_ctx.get('brand', '?')} | Niche: {brand_ctx.get('niche', '?')[:50]}", file=sys.stderr)

    # Get only Raw posts (FIXED: no longer loads all posts)
    posts_to_analyze = get_raw_posts(vl_db, limit)
    if not posts_to_analyze:
        print(json.dumps({"status": "empty", "message": f"No raw posts in '{niche_name}'."}))
        return

    print(f"\n🔬 Analyzing {len(posts_to_analyze)} raw posts with AI", file=sys.stderr)

    analyzed = 0
    rejected = 0
    errors = 0

    for post in posts_to_analyze:
        print(f"  📋 {post['creator']} ({post['views']:,} views)", file=sys.stderr)

        rel = score_relevance(post, niche_name, brand_ctx)
        if not rel:
            errors += 1
            continue

        score = rel.get("score", 0)
        reason = rel.get("reason", "")

        if score < RELEVANCE_THRESHOLD:
            mark_rejected(post["page_id"], score, reason)
            rejected += 1
            print(f"    ❌ Rejected (score {score}): {reason}", file=sys.stderr)
            continue

        print(f"    ✅ Relevant (score {score})", file=sys.stderr)

        if relevance_only:
            notion_update_page(post["page_id"], {
                "Status": n_select("Relevant"),
                "Relevance Score": n_number(score),
            })
            analyzed += 1
            continue

        analysis = deep_analyze(post, niche_name, brand_ctx)
        if not analysis:
            errors += 1
            continue

        mark_analyzed(post["page_id"], score, analysis)
        analyzed += 1
        print(f"    📊 {analysis.get('content_format', '?')} / {analysis.get('hook_type', '?')}", file=sys.stderr)

    result = {
        "status": "success",
        "niche": niche_name,
        "total_raw": len(posts_to_analyze),
        "analyzed": analyzed,
        "rejected_by_ai": rejected,
        "errors": errors,
    }
    print(json.dumps(result, indent=2))


def show_top(niche_name, limit=5, sort_by="views"):
    """Show top analyzed posts WITHOUT re-analyzing. Read-only."""
    import subprocess
    script_dir = os.path.dirname(os.path.abspath(__file__))
    result = subprocess.run(
        ["python3", os.path.join(script_dir, "top.py"), "--niche", niche_name, "--limit", str(limit), "--sort", sort_by],
        capture_output=True, text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--niche", required=True, help="Niche name")
    parser.add_argument("--limit", type=int, default=DEFAULT_ANALYSIS_LIMIT)
    parser.add_argument("--relevance-only", action="store_true")
    parser.add_argument("--run", action="store_true", help="Actually run AI analysis")
    parser.add_argument("--sort", choices=["views", "outlier"], default="views")
    args = parser.parse_args()

    if args.relevance_only or args.run:
        run(args.niche, args.limit, args.relevance_only)
    else:
        show_top(args.niche, args.limit, args.sort)
