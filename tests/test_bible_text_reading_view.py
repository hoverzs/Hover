"""Formázott Bibliai szöveg olvasónézet — escape és versparser tesztek."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bible_text_ui import (
    build_formatted_bible_text_html,
    parse_passage_text_blocks,
)

errors: list[str] = []


def ok(cond: bool, msg: str) -> None:
    if not cond:
        errors.append(msg)


def main() -> None:
    # Versszám formák
    blocks = parse_passage_text_blocks(
        "17 Ti azonban, szeretteim...\n"
        "18. Azt mondták ugyanis...\n"
        "19  Ezek szakadásokat okoznak...\n"
        "Bevezető megjegyzés sortörés nélkül\n"
        "20 Ti azonban, szeretteim..."
    )
    ok(blocks[0] == ("17", "Ti azonban, szeretteim..."), f"b0 {blocks[0]}")
    ok(blocks[1] == ("18", "Azt mondták ugyanis..."), f"b1 {blocks[1]}")
    ok(blocks[2] == ("19", "Ezek szakadásokat okoznak..."), f"b2 {blocks[2]}")
    ok(blocks[3] == (None, "Bevezető megjegyzés sortörés nélkül"), f"b3 {blocks[3]}")
    ok(blocks[4] == ("20", "Ti azonban, szeretteim..."), f"b4 {blocks[4]}")

    # HTML escape
    markup = build_formatted_bible_text_html('16 <script>alert("x")</script> & "idézet"')
    ok("<script>" not in markup, "script tag must be escaped")
    ok("&lt;script&gt;" in markup, "escaped script")
    ok("&amp;" in markup, "amp escaped")
    ok("bible-verse-num" in markup and "bible-verse-text" in markup, "structure")
    ok("alert" in markup, "text preserved escaped")

    # Üres
    ok(build_formatted_bible_text_html("   \n  ") == "", "empty")

    # Hosszú sor — struktúra megmarad
    long = "1 " + ("szó " * 80)
    m = build_formatted_bible_text_html(long)
    ok("bible-verse-text" in m, "long verse")
    ok("table" not in m.lower(), "no table")

    # Júd jellegű 4 vers
    jude = (
        "17 Ti azonban, szeretteim, emlékezzetek meg...\n"
        "18 Azt mondták ugyanis...\n"
        "19 Ezek szakadásokat okoznak...\n"
        "20 Ti azonban, szeretteim, épüljetek..."
    )
    jb = parse_passage_text_blocks(jude)
    ok(len(jb) == 4, "jude 4")
    ok([n for n, _ in jb] == ["17", "18", "19", "20"], "jude nums")

    if errors:
        print("FAIL")
        for e in errors:
            print(" -", e)
        raise SystemExit(1)
    print("OK bible reading view tests passed")


if __name__ == "__main__":
    main()
