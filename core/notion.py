"""
Notion API helpers — deduplicated from all scripts.
Single source of truth for all Notion CRUD operations.
"""

from core.config import NOTION_API_KEY, NOTION_BASE
from core.http import http_request


# === Headers ===

def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


# === CRUD Operations ===

def notion_query_all(db_id, filter_obj=None):
    """Query a Notion database with pagination. Returns all matching pages."""
    all_results = []
    cursor = None
    while True:
        body = {}
        if filter_obj:
            body["filter"] = filter_obj
        if cursor:
            body["start_cursor"] = cursor
        result = http_request(
            f"{NOTION_BASE}/databases/{db_id}/query",
            method="POST", data=body, headers=notion_headers(),
        )
        if not result:
            break
        all_results.extend(result.get("results", []))
        if not result.get("has_more"):
            break
        cursor = result.get("next_cursor")
    return all_results


def notion_create_page(db_id, properties):
    """Create a page in a Notion database."""
    return http_request(
        f"{NOTION_BASE}/pages", method="POST",
        data={"parent": {"database_id": db_id}, "properties": properties},
        headers=notion_headers(),
    )


def notion_update_page(page_id, properties):
    """Update a Notion page's properties."""
    return http_request(
        f"{NOTION_BASE}/pages/{page_id}", method="PATCH",
        data={"properties": properties},
        headers=notion_headers(),
    )


def notion_archive_page(page_id):
    """Archive (soft-delete) a Notion page."""
    return http_request(
        f"{NOTION_BASE}/pages/{page_id}", method="PATCH",
        data={"archived": True},
        headers=notion_headers(),
    )


def notion_create_database(parent_page_id, title, properties):
    """Create a new Notion database under a page."""
    return http_request(
        f"{NOTION_BASE}/databases", method="POST",
        data={
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "properties": properties,
        },
        headers=notion_headers(),
    )


def notion_update_database(db_id, properties):
    """Update a Notion database schema."""
    return http_request(
        f"{NOTION_BASE}/databases/{db_id}", method="PATCH",
        data={"properties": properties},
        headers=notion_headers(),
    )


# === Property Builders ===
# Shorthand for building Notion property values.

def n_title(t):
    return {"title": [{"text": {"content": str(t)[:2000]}}]}

def n_rich_text(t):
    return {"rich_text": [{"text": {"content": str(t)[:2000]}}]}

def n_number(v):
    return {"number": v}

def n_select(n):
    return {"select": {"name": str(n)}}

def n_url(u):
    return {"url": str(u)}

def n_date(d):
    return {"date": {"start": d}}

def n_relation(ids):
    return {"relation": [{"id": i} for i in ids]}

def n_checkbox(v):
    return {"checkbox": v}


# === Property Readers ===
# Extract values from Notion page properties.

def read_title(props, field):
    """Read a title field value."""
    return (props.get(field, {}).get("title") or [{}])[0].get("plain_text", "")

def read_text(props, field):
    """Read a rich_text field value."""
    return (props.get(field, {}).get("rich_text") or [{}])[0].get("plain_text", "")

def read_select(props, field):
    """Read a select field value."""
    return (props.get(field, {}).get("select") or {}).get("name", "")

def read_number(props, field, default=0):
    """Read a number field value."""
    return props.get(field, {}).get("number", default) or default

def read_url(props, field):
    """Read a URL field value."""
    return props.get(field, {}).get("url", "") or ""

def read_checkbox(props, field):
    """Read a checkbox field value."""
    return props.get(field, {}).get("checkbox", False)

def read_date(props, field):
    """Read a date field's start value."""
    return (props.get(field, {}).get("date") or {}).get("start", "")
