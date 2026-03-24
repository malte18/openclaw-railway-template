#!/usr/bin/env python3
"""Check if a scrape is running and its progress."""

import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from core.config import LOCK_FILE, PROGRESS_FILE

if os.path.exists(LOCK_FILE):
    progress = {}
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            progress = json.load(f)
    with open(LOCK_FILE) as f:
        lock = json.load(f)
    print(json.dumps({
        "status": "running",
        "started": lock.get("started", ""),
        "sources_done": progress.get("sources_done", 0),
        "sources_total": progress.get("sources_total", 0),
        "posts_found": progress.get("posts_found", 0),
        "current": progress.get("message", ""),
        "updated_at": progress.get("updated_at", ""),
    }, indent=2))
else:
    print(json.dumps({"status": "idle", "message": "No scrape running."}))
