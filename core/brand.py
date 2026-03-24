"""
Brand profile and niche lookups — unified from 3 different implementations.
Single function to get all brand context for any niche.
"""

from core.config import NICHE_REGISTRY_DB, BRAND_PROFILE_DB
from core.notion import notion_query_all, read_title, read_text, read_select, read_checkbox


def get_brand_profile(niche_name):
    """
    Get full brand profile for a niche. Matches on Brand Name, Niche, or Niche ID.
    Returns all brand context: voice, language, keywords, products, rules, content_split.
    """
    pages = notion_query_all(BRAND_PROFILE_DB)
    niche_lower = niche_name.lower()

    for page in pages:
        props = page.get("properties", {})
        brand = read_title(props, "Brand Name")
        niche = read_text(props, "Niche")
        niche_id = read_text(props, "Niche ID")

        # Fuzzy match: exact name, brand name, niche ID, or niche field contains name
        if (niche_lower == brand.lower() or
            niche_lower == niche_id.lower() or
            niche_lower == niche.lower() or
            niche_lower in niche.lower() or
            niche_lower.replace(" ", "-") == niche_id.lower()):

            kw_text = read_text(props, "Keywords")
            keywords = [k.strip().lower() for k in kw_text.split(",") if k.strip()] if kw_text else []

            return {
                "brand": brand,
                "niche": niche,
                "niche_id": niche_id,
                "voice": read_text(props, "Voice"),
                "language": read_select(props, "Language") or "English",
                "keywords": keywords,
                "products": read_text(props, "Product Catalog"),
                "rules": read_text(props, "Content Rules"),
                "content_split": read_text(props, "Content Split"),
                "avatar_id": read_text(props, "Avatar ID"),
                "voice_id": read_text(props, "Voice ID"),
            }

    # Fallback: return minimal profile
    return {
        "brand": niche_name,
        "niche": niche_name,
        "niche_id": niche_name.lower().replace(" ", "-"),
        "voice": "",
        "language": "English",
        "keywords": [],
        "products": "",
        "rules": "",
        "content_split": "",
        "avatar_id": "",
        "voice_id": "",
    }


def get_niche(niche_name):
    """
    Get niche database IDs from the Niche Registry.
    Returns: {"niche": str, "ss_db": str, "vl_db": str, "cp_db": str, "page_id": str}
    """
    pages = notion_query_all(
        NICHE_REGISTRY_DB,
        {"property": "Niche", "title": {"equals": niche_name}},
    )
    if not pages:
        return None

    props = pages[0].get("properties", {})
    return {
        "niche": niche_name,
        "ss_db": read_text(props, "Scraping Sources DB"),
        "vl_db": read_text(props, "Viral Library DB"),
        "cp_db": read_text(props, "Content Pipeline DB"),
        "page_id": read_text(props, "Page ID"),
        "brand_profile_id": read_text(props, "Brand Profile ID"),
        "active": read_checkbox(props, "Active"),
    }


def get_all_niches(active_only=True):
    """Get all niches from the Niche Registry."""
    filter_obj = {"property": "Active", "checkbox": {"equals": True}} if active_only else None
    pages = notion_query_all(NICHE_REGISTRY_DB, filter_obj)

    niches = []
    for page in pages:
        props = page.get("properties", {})
        ss = read_text(props, "Scraping Sources DB")
        vl = read_text(props, "Viral Library DB")
        cp = read_text(props, "Content Pipeline DB")
        if ss and vl:
            niches.append({
                "niche": read_title(props, "Niche"),
                "ss_db": ss,
                "vl_db": vl,
                "cp_db": cp,
                "page_id": read_text(props, "Page ID"),
                "active": read_checkbox(props, "Active"),
            })
    return niches
