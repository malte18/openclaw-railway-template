"""
Claude API helper — centralized AI calls.
"""

from core.config import ANTHROPIC_API_KEY, ANTHROPIC_BASE, ANALYSIS_MODEL, SCRIPT_MODEL
from core.http import http_request

import json


def call_claude(prompt, model=None, max_tokens=500):
    """
    Call Claude API with a simple prompt. Returns parsed response text.
    Returns None on failure.
    """
    if not ANTHROPIC_API_KEY:
        return None

    if model is None:
        model = ANALYSIS_MODEL

    resp = http_request(
        f"{ANTHROPIC_BASE}/messages",
        method="POST",
        data={
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        },
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        timeout=60,
    )

    if not resp:
        return None

    try:
        return resp["content"][0]["text"]
    except (KeyError, IndexError):
        return None


def call_claude_json(prompt, model=None, max_tokens=500):
    """
    Call Claude and parse the response as JSON.
    Handles markdown code blocks in the response.
    Returns parsed dict/list, or None on failure.
    """
    text = call_claude(prompt, model=model, max_tokens=max_tokens)
    if not text:
        return None

    try:
        # Strip markdown code blocks if present
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except (json.JSONDecodeError, IndexError) as e:
        return None
