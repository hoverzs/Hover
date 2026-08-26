"""Read-only adapters over existing Textus data sources."""

from textus_kb.adapters.lexicon import LexiconAdapter
from textus_kb.adapters.places import PlacesAdapter
from textus_kb.adapters.tagnt import TagntAdapter

__all__ = ["LexiconAdapter", "PlacesAdapter", "TagntAdapter"]
