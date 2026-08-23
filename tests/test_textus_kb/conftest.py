"""Shared fixtures for textus_kb tests."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from textus_kb.importers.aquifer_bible_dictionary import AQUIFER_DICTIONARY_SOURCE_ID
from textus_kb.importers.aquifer_study_notes import AQUIFER_SOURCE_ID
from textus_kb.manifest import KnowledgeBaseManifest, load_manifest


@pytest.fixture(name="phase2a_manifest")
def phase2a_manifest_fixture() -> KnowledgeBaseManifest:
    base = json.loads(Path("textus_kb/data/kb_manifest.json").read_text(encoding="utf-8"))
    payload = deepcopy(base)
    for source in payload["sources"]:
        if source["id"] in {AQUIFER_SOURCE_ID, AQUIFER_DICTIONARY_SOURCE_ID}:
            source["enabled"] = False
    path = Path("tests/fixtures/kb/tmp_manifest_phase2a.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return load_manifest(path)
