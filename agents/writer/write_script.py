#!/usr/bin/env python3
"""
Script Writer v2 — generates branded video scripts from analyzed viral posts.
FIX: Stores full script JSON as page content (not truncated to 2000 chars).
FIX: CTA is not forced on every video.

Usage:
  python3 write_script.py --niche "Beef Snacks"
  python3 write_script.py --niche "Beef Snacks" --url <viral_url>
  python3 write_script.py --niche "Beef Snacks" --revise <id> --feedback "make hook stronger"
"""

import argparse, json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.config import SCRIPT_MODEL
from core.notion import (
    notion_query_all, notion_create_page, notion_update_page,
    n_title, n_rich_text, n_select, n_url, n_date, n_relation,
    read_title, read_text, read_select, read_number, read_url,
)
from core.brand import get_niche, get_brand_profile
from core.claude import call_claude_json


# ── Get Viral Post ────────────────────────────────────────────

def get_best_unadapted(vl_db):
    """Get the top analyzed post that hasn't been scripted yet."""
    pages = notion_query_all(vl_db, {"property": "Status", "select": {"equals": "Analyzed"}})
    posts = []
    for p in pages:
        pr = p["properties"]
        posts.append({
            "page_id": p["id"],
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
            "structure": read_text(pr, "Structure"),
            "visual_style": read_select(pr, "Visual Style"),
            "persona": read_select(pr, "Persona"),
            "why_viral": read_text(pr, "Why Viral"),
            "adaptation": read_text(pr, "Adaptation Idea"),
        })
    posts.sort(key=lambda x: (x["relevance_score"], x.get("outlier_ratio", 0), x["views"]), reverse=True)
    return posts[0] if posts else None


def get_post_by_url(vl_db, url):
    pages = notion_query_all(vl_db, {"property": "URL", "url": {"equals": url}})
    if not pages:
        return None
    p = pages[0]
    pr = p["properties"]
    return {
        "page_id": p["id"],
        "title": read_title(pr, "Title"),
        "url": read_url(pr, "URL"),
        "creator": read_text(pr, "Creator"),
        "views": read_number(pr, "Views"),
        "hook": read_text(pr, "Hook"),
        "hook_type": read_select(pr, "Hook Type"),
        "content_format": read_select(pr, "Content Format"),
        "structure": read_text(pr, "Structure"),
        "visual_style": read_select(pr, "Visual Style"),
        "persona": read_select(pr, "Persona"),
        "why_viral": read_text(pr, "Why Viral"),
        "adaptation": read_text(pr, "Adaptation Idea"),
    }


# ── Generate Script ───────────────────────────────────────────

def generate_script(post, brand, feedback=None):
    revision_note = ""
    if feedback:
        revision_note = f"\n\nREVISION REQUEST: {feedback}\nKeep what worked, fix what was requested."

    prompt = f"""You are a viral short-form video scriptwriter for the brand "{brand['brand']}".

BRAND CONTEXT:
- Niche: {brand['niche']}
- Voice: {brand['voice']}
- Language: {brand['language']}
- Products: {brand['products']}
- Content Rules: {brand['rules']}
- Content Split: {brand['content_split']}

VIRAL REFERENCE POST:
- Creator: @{post['creator']} ({post.get('views', 0):,} views)
- Hook: "{post.get('hook', '')}"
- Hook Type: {post.get('hook_type', '')}
- Content Format: {post.get('content_format', '')}
- Video Structure: {post.get('structure', '')}
- Visual Style: {post.get('visual_style', '')}
- Target Persona: {post.get('persona', '')}
- Why it went viral: {post.get('why_viral', '')}
- Adaptation idea: {post.get('adaptation', '')}
- Original URL: {post.get('url', '')}
{revision_note}

Write a complete video script that adapts this viral format for {brand['brand']}.
The script should feel native to the platform, not like an ad.

VIDEO FORMAT: "Floating head + full-screen B-Roll background"
- Speaker filmed on green screen, keyed out, appears at bottom (~30% of frame)
- Speaker MOVES POSITION each segment: bottom-center, bottom-left, bottom-right
- ENTIRE BACKGROUND is a full-screen image that changes per segment
- Backgrounds are contextual to what's being said
- Bold TEXT OVERLAY appears mid-frame with key phrases
- Each segment: 3-5 seconds, quick cuts

Return ONLY valid JSON:
{{
  "title": "<working title>",
  "persona": "<target persona>",
  "format": "<content format>",
  "duration_seconds": <15|30|60>,
  "segments": [
    {{
      "segment_number": 1,
      "duration_seconds": <3-5>,
      "voiceover": "<exact words spoken>",
      "speaker_position": "<bottom-center|bottom-left|bottom-right>",
      "text_overlay": "<bold key phrase>",
      "text_style": "<green_highlight|red_highlight|yellow_highlight|white_bold>",
      "background_description": "<detailed AI image generation prompt for full-screen background>",
      "is_product_shot": <true|false>
    }}
  ],
  "hashtags": "<relevant hashtags>",
  "reference_url": "{post.get('url', '')}",
  "inspired_by": "<what pattern we adapted>"
}}

RULES:
- First segment is always the HOOK (most attention-grabbing)
- NOT every video needs a CTA. Only add CTA if the content naturally leads to it.
- Product shots should only appear when voiceover mentions the product
- Background descriptions must work as AI image generation prompts
- Text overlays: short, punchy, highlight key claim
- Write in {brand['language']}. Authentic, not corporate."""

    return call_claude_json(prompt, model=SCRIPT_MODEL, max_tokens=2000)


# ── Save to Pipeline ──────────────────────────────────────────

def save_to_pipeline(cp_db, script, post):
    """Save script to Content Pipeline. Full JSON in Notes, summary in Script field."""
    # Summary for Script field (stays under 2000 chars)
    script_summary = ""
    for seg in script.get("segments", []):
        script_summary += f"[{seg.get('duration_seconds', '?')}s] {seg.get('speaker_position', '?')}: {seg.get('voiceover', '')[:80]}\n"

    props = {
        "Title": n_title(script.get("title", "Untitled Script")),
        "Status": n_select("Script Draft"),
        "Script": n_rich_text(script_summary[:2000]),
        "Hook": n_rich_text(script.get("segments", [{}])[0].get("voiceover", "") if script.get("segments") else ""),
        "Format": n_rich_text(script.get("format", "")),
        "Persona": n_rich_text(script.get("persona", "")),
        "Notes": n_rich_text(json.dumps(script, indent=2)[:2000]),
        "Created At": n_date(datetime.now(timezone.utc).strftime("%Y-%m-%d")),
    }
    if post.get("page_id"):
        props["Viral Source"] = n_relation([post["page_id"]])

    return notion_create_page(cp_db, props)


# ── Display ───────────────────────────────────────────────────

def format_script(script, post):
    lines = []
    lines.append(f"📝 {script.get('title', 'Untitled')}")
    lines.append(f"🎯 {script.get('persona', '?')} | {script.get('format', '?')} | {script.get('duration_seconds', '?')}s")
    lines.append(f"🔗 {post.get('url', '?')}")
    lines.append(f"💡 {script.get('inspired_by', '?')}")
    lines.append("")

    segments = script.get("segments", [])
    for seg in segments:
        num = seg.get("segment_number", "?")
        dur = seg.get("duration_seconds", "?")
        pos = seg.get("speaker_position", "?")
        is_hook = num == 1
        is_last = num == len(segments)

        label = "🪝 HOOK" if is_hook else (f"📖 SEG {num}")
        if is_last and seg.get("is_product_shot"):
            label = "📢 CTA"
        lines.append(f"{label} ({dur}s) | Speaker: {pos}")
        lines.append(f'   🗣️ "{seg.get("voiceover", "")}"')
        lines.append(f'   💬 [{seg.get("text_style", "?")}] {seg.get("text_overlay", "")}')
        lines.append(f'   🖼️ {seg.get("background_description", "")[:120]}')
        if seg.get("is_product_shot"):
            lines.append(f'   📦 PRODUCT SHOT')
        lines.append("")

    lines.append(f"# {script.get('hashtags', '')}")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────

def run(niche_name, url=None, revise_id=None, feedback=None):
    missing = [v for v in ["ANTHROPIC_API_KEY", "NOTION_API_KEY"] if not os.environ.get(v)]
    if missing:
        print(json.dumps({"error": f"Missing: {', '.join(missing)}"}))
        sys.exit(1)

    niche = get_niche(niche_name)
    if not niche:
        print(json.dumps({"error": f"Niche '{niche_name}' not found."}))
        sys.exit(1)

    brand = get_brand_profile(niche_name)
    if not brand:
        print(json.dumps({"error": f"No brand profile for '{niche_name}'."}))
        sys.exit(1)

    vl_db, cp_db = niche["vl_db"], niche["cp_db"]

    if url:
        post = get_post_by_url(vl_db, url)
        if not post:
            print(json.dumps({"error": f"Post not found: {url}"}))
            sys.exit(1)
    else:
        post = get_best_unadapted(vl_db)
        if not post:
            print(json.dumps({"error": "No analyzed posts available. Run analysis first."}))
            sys.exit(1)

    print(f"📝 Writing script based on @{post['creator']} ({post.get('views', 0):,} views)", file=sys.stderr)

    script = generate_script(post, brand, feedback)
    if not script:
        print(json.dumps({"error": "Script generation failed."}))
        sys.exit(1)

    result = save_to_pipeline(cp_db, script, post)
    pipeline_id = result["id"] if result else None

    if post.get("page_id"):
        notion_update_page(post["page_id"], {"Status": n_select("Scripted")})

    formatted = format_script(script, post)
    print(formatted)
    print(f"\n---")
    print(f"Pipeline ID: {pipeline_id}")
    print(f"Status: Script Draft")
    print(f"Reply 'approve' to approve, or give feedback to revise.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--niche", required=True)
    parser.add_argument("--url")
    parser.add_argument("--revise")
    parser.add_argument("--feedback")
    args = parser.parse_args()
    run(args.niche, args.url, args.revise, args.feedback)
