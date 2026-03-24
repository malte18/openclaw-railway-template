"""
HTTP client with retry logic and rate limit handling.
Replaces the copy-pasted http_request() across all scripts.
"""

import json
import sys
import time
from urllib.request import urlopen, Request
from urllib.error import HTTPError


def http_request(url, method="GET", data=None, headers=None, timeout=30, retries=3):
    """
    Make an HTTP request with exponential backoff retry.
    Handles Notion's 429 rate limits and transient failures.
    """
    if headers is None:
        headers = {}
    if data is not None:
        data = json.dumps(data).encode()
        headers.setdefault("Content-Type", "application/json")

    last_error = None
    for attempt in range(retries):
        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            last_error = e
            body = e.read().decode() if hasattr(e, "read") else ""

            if e.code == 429:
                # Rate limited — back off and retry
                wait = min(2 ** attempt * 1.5, 10)
                print(f"  Rate limited (429), waiting {wait:.1f}s... (attempt {attempt + 1}/{retries})", file=sys.stderr)
                time.sleep(wait)
                continue
            elif e.code >= 500:
                # Server error — retry
                wait = 2 ** attempt
                print(f"  Server error ({e.code}), retrying in {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            else:
                # Client error (4xx except 429) — don't retry
                print(f"HTTP {e.code}: {url[:80]}\n{body[:200]}", file=sys.stderr)
                return None
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            print(f"Request failed: {e}", file=sys.stderr)
            return None

    print(f"All {retries} retries exhausted for {url[:80]}", file=sys.stderr)
    return None
