from __future__ import annotations

from jordan_claw.obsidian.parser import extract_wiki_links, parse_note_file


SAMPLE_SOURCE_NOTE = """\
---
type: source
title: "Test Article"
url: https://example.com
author: "Test Author"
source-type: article
captured: 2026-03-03
tags: [leadership, mindfulness]
status: processed
---

## Summary

This is a test summary.

## Key Takeaways

1. First takeaway

## Related Topics

- [[Atomic Note One]]
- [[Atomic Note Two]]

## Notes
"""

SAMPLE_ATOMIC_NOTE = """\
---
type: atomic-note
created: 2026-03-16
tags: [entrepreneurship, scaling]
sources:
  - "[[Source Document One]]"
---

This is the body of the atomic note.

## Connections

- [[Related Concept]] -- explains the relationship
- [[Another Concept]] -- another connection

## Applications

- Can be used for X
"""

SAMPLE_NO_FRONTMATTER = """\
# Just a heading

Some content without frontmatter.

Links to [[Other Note]] here.
"""


def test_parse_source_note():
    result = parse_note_file(SAMPLE_SOURCE_NOTE, "20-Sources/Test Article.md")
    assert result["title"] == "Test Article"
    assert result["note_type"] == "source"
    assert result["tags"] == ["leadership", "mindfulness"]
    assert "Atomic Note One" in result["wiki_links"]
    assert "Atomic Note Two" in result["wiki_links"]
    assert result["frontmatter"]["url"] == "https://example.com"
    assert "## Summary" in result["content"]
    assert result["content_hash"] is not None


def test_parse_atomic_note():
    result = parse_note_file(SAMPLE_ATOMIC_NOTE, "30-Notes/Test Concept.md")
    assert result["title"] == "Test Concept"
    assert result["note_type"] == "atomic-note"
    assert result["tags"] == ["entrepreneurship", "scaling"]
    assert "Related Concept" in result["wiki_links"]
    assert "Another Concept" in result["wiki_links"]
    assert "Source Document One" in result["wiki_links"]


def test_parse_note_without_frontmatter():
    result = parse_note_file(SAMPLE_NO_FRONTMATTER, "15-Stories/Story.md")
    assert result["title"] == "Story"
    assert result["note_type"] == "story"
    assert result["tags"] == []
    assert "Other Note" in result["wiki_links"]


def test_parse_note_title_fallback_from_filename():
    result = parse_note_file(SAMPLE_ATOMIC_NOTE, "30-Notes/My Note Title.md")
    # frontmatter has no title field, so falls back to filename
    assert result["title"] == "My Note Title"


def test_parse_note_title_from_frontmatter():
    result = parse_note_file(SAMPLE_SOURCE_NOTE, "20-Sources/Whatever.md")
    # source notes have title in frontmatter
    assert result["title"] == "Test Article"


def test_extract_wiki_links():
    text = "Links to [[Note A]] and [[Note B]] and [[Note A]] again"
    links = extract_wiki_links(text)
    assert links == ["Note A", "Note B"]


def test_extract_wiki_links_empty():
    assert extract_wiki_links("No links here") == []


def test_content_hash_deterministic():
    result1 = parse_note_file(SAMPLE_SOURCE_NOTE, "test.md")
    result2 = parse_note_file(SAMPLE_SOURCE_NOTE, "test.md")
    assert result1["content_hash"] == result2["content_hash"]


def test_note_type_from_folder_fallback():
    """When frontmatter has a non-standard type, use it as-is."""
    note_with_custom_type = """\
---
type: delivery-profile
updated: 2026-03-12
---

Content here.
"""
    result = parse_note_file(note_with_custom_type, "15-Stories/Profile.md")
    assert result["note_type"] == "delivery-profile"
