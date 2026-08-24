"""One-off upstream size audit for Phase 4D documentation."""
from __future__ import annotations

import json
from pathlib import Path

from textus_kb.paths import PROJECT_ROOT

SN_ROOT = PROJECT_ROOT / "_upstream_audit" / "AquiferOpenStudyNotes" / "eng"
DICT_ROOT = PROJECT_ROOT / "_upstream_audit" / "AquiferOpenBibleDictionary" / "eng"


def audit_study_notes() -> dict:
    json_dir = SN_ROOT / "json"
    total_bytes = 0
    article_count = 0
    passage_links = 0
    books: set[int] = set()
    for path in sorted(json_dir.glob("*.content.json")):
        total_bytes += path.stat().st_size
        articles = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(articles, list):
            continue
        for article in articles:
            if not isinstance(article, dict):
                continue
            article_count += 1
            idx = str(article.get("index_reference") or "")
            if len(idx) >= 2 and idx[:2].isdigit():
                books.add(int(idx[:2]))
            for passage in article.get("associations", {}).get("passage", []):
                if passage.get("start_ref"):
                    passage_links += 1
    return {
        "article_count": article_count,
        "content_bytes": total_bytes,
        "passage_link_count": passage_links,
        "book_count": len(books),
        "content_files": len(list(json_dir.glob("*.content.json"))),
    }


def audit_dictionary() -> dict:
    json_dir = DICT_ROOT / "json"
    total_bytes = 0
    article_count = 0
    passage_links = 0
    acai_links = 0
    index_refs: set[str] = set()
    for path in sorted(json_dir.glob("*.content.json")):
        total_bytes += path.stat().st_size
        articles = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(articles, list):
            continue
        for article in articles:
            if not isinstance(article, dict):
                continue
            article_count += 1
            index_refs.add(str(article.get("index_reference") or ""))
            for passage in article.get("associations", {}).get("passage", []):
                if passage.get("start_ref"):
                    passage_links += 1
            for link in article.get("associations", {}).get("acai", []):
                if link.get("id") or link.get("entity_id"):
                    acai_links += 1
    return {
        "article_count": article_count,
        "unique_index_references": len(index_refs),
        "content_bytes": total_bytes,
        "passage_link_count": passage_links,
        "acai_link_count": acai_links,
        "content_files": len(list(json_dir.glob("*.content.json"))),
    }


if __name__ == "__main__":
    print(json.dumps({"study_notes": audit_study_notes(), "dictionary": audit_dictionary()}, indent=2))
