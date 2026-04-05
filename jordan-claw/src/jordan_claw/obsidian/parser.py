from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from pathlib import Path

import frontmatter

WIKI_LINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")

FOLDER_TYPE_MAP = {
    "30-Notes": "atomic-note",
    "20-Sources": "source",
    "15-Stories": "story",
}


def extract_wiki_links(text: str) -> list[str]:
    """Extract unique wiki-link targets from text, preserving first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for match in WIKI_LINK_PATTERN.finditer(text):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _title_from_path(vault_path: str) -> str:
    """Extract title from vault path by stripping folder and .md extension."""
    return Path(vault_path).stem


def _note_type_from_folder(vault_path: str) -> str:
    """Infer note type from the top-level folder in the vault path."""
    top_folder = vault_path.split("/")[0] if "/" in vault_path else ""
    return FOLDER_TYPE_MAP.get(top_folder, "note")


def _sanitize_frontmatter(fm: dict) -> dict:
    """Convert non-JSON-serializable YAML values (dates) to strings."""
    sanitized = {}
    for key, value in fm.items():
        if isinstance(value, (date, datetime)):
            sanitized[key] = value.isoformat()
        elif isinstance(value, list):
            sanitized[key] = [v.isoformat() if isinstance(v, (date, datetime)) else v for v in value]
        else:
            sanitized[key] = value
    return sanitized


def parse_note_file(raw_content: str, vault_path: str) -> dict:
    """Parse a markdown note file into structured fields.

    Args:
        raw_content: The full file content including frontmatter.
        vault_path: Relative path in the vault, e.g. '30-Notes/My Note.md'.

    Returns:
        Dict with keys: title, note_type, content, frontmatter, tags,
        wiki_links, content_hash, vault_path.
    """
    post = frontmatter.loads(raw_content)

    fm = _sanitize_frontmatter(dict(post.metadata))
    body = post.content

    title = fm.get("title") or _title_from_path(vault_path)
    note_type = fm.get("type") or _note_type_from_folder(vault_path)
    tags = fm.get("tags", [])
    if not isinstance(tags, list):
        tags = []

    # Extract wiki-links from both frontmatter sources and body
    all_text = raw_content  # Search the full file for links
    wiki_links = extract_wiki_links(all_text)

    content_hash = hashlib.sha256(raw_content.encode()).hexdigest()

    return {
        "vault_path": vault_path,
        "title": title,
        "note_type": note_type,
        "content": body,
        "frontmatter": fm,
        "tags": tags,
        "wiki_links": wiki_links,
        "content_hash": content_hash,
    }
