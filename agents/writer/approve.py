#!/usr/bin/env python3
"""
Approve or update a script in the Content Pipeline.

Usage:
  python3 approve.py --id <page_id>
  python3 approve.py --id <page_id> --status "Script Draft"
"""

import argparse, json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.notion import notion_update_page, n_select


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True, help="Content Pipeline page ID")
    parser.add_argument("--status", default="Script Approved", help="New status")
    args = parser.parse_args()

    result = notion_update_page(args.id, {"Status": n_select(args.status)})
    if result:
        print(json.dumps({"status": "updated", "page_id": args.id, "new_status": args.status}))
    else:
        print(json.dumps({"error": "Failed to update"}))
