"""
Centralized configuration — single source of truth for all constants.
All DB IDs, API endpoints, model names, and defaults live here.
"""

import os

# === API Keys ===
APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")

# === API Endpoints ===
NOTION_BASE = "https://api.notion.com/v1"
ANTHROPIC_BASE = "https://api.anthropic.com/v1"
APIFY_BASE = "https://api.apify.com/v2"

# === Notion Database IDs ===
NICHE_REGISTRY_DB = os.environ.get("NOTION_NICHE_REGISTRY_DB", "329c88bb-9edb-8197-a2d1-d97caec4971e")
BRAND_PROFILE_DB = os.environ.get("NOTION_BRAND_PROFILE_DB", "329c88bb-9edb-8139-b979-d1fdd0368281")
PARENT_PAGE = os.environ.get("NOTION_PARENT_PAGE", "329c88bb-9edb-8071-8a5e-e5706df574cf")

# === AI Models ===
ANALYSIS_MODEL = "claude-3-5-haiku-20241022"  # cheap + fast for relevance scoring
SCRIPT_MODEL = "claude-sonnet-4-20250514"      # quality for script writing

# === Apify Actor IDs ===
APIFY_ACTORS = {
    "tiktok_profile": "clockworks~tiktok-scraper",
    "tiktok_hashtag": "clockworks~tiktok-scraper",
    "tiktok_keyword": "clockworks~tiktok-scraper",
    "instagram_profile": "apify~instagram-scraper",
    "instagram_hashtag": "apify~instagram-scraper",
}

# === Defaults ===
DEFAULT_POSTS_PER_SOURCE = 5
PROFILE_MAX_AGE_DAYS = 28
SEARCH_MAX_AGE_DAYS = 14
AUTO_DISCOVER_MIN_VIEWS = 100_000
MAX_AUTO_DISCOVER_PER_RUN = 5
MIN_VIEWS_FOR_DISCOVERY = 10_000
RELEVANCE_THRESHOLD = 4  # 1-10, below = Rejected
DEFAULT_ANALYSIS_LIMIT = 50

# === File Paths ===
LOCK_FILE = "/tmp/scout_running.lock"
PROGRESS_FILE = "/tmp/scout_progress.json"
RESULTS_FILE = "/tmp/scout_last_result.txt"
