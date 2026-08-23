import json
from pathlib import Path

from textus_kb.context_builder import build_context_from_evidence
from textus_kb.context_profiles import PROFILE_EXEGESIS
from textus_kb.retrieval import retrieve, retrieve_to_json

packet = json.loads(retrieve_to_json("Jn 4,1-42"))
packet["aquifer_evidence_count"] = sum(
    1 for item in packet["evidence_items"] if item["relation_type"] == "exegetical_note"
)
Path("tests/fixtures/kb/john_4_1_42_packet_with_aquifer.json").write_text(
    json.dumps(packet, indent=2, ensure_ascii=False),
    encoding="utf-8",
)
context = build_context_from_evidence(retrieve("Jn 4,1-42"), PROFILE_EXEGESIS).to_dict()
Path("tests/fixtures/kb/john_4_1_42_exegesis_context_phase3a.json").write_text(
    json.dumps(context, indent=2, ensure_ascii=False),
    encoding="utf-8",
)
print("packet aquifer", packet["aquifer_evidence_count"])
print("context tokens", context["estimated_tokens"])
