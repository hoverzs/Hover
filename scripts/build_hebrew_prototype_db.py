from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bible_engine.hebrew_sqlite import (  # noqa: E402
    DEFAULT_TAHOT_DATABASE_PATH,
    DEFAULT_TBESH_DATABASE_PATH,
    import_tahot_database,
    import_tbesh_lexicon_database,
)
from bible_engine.paths import GENERATED_DATA_DIR, project_path  # noqa: E402


def _default_full_tahot_sources() -> list[Path]:
    temp = Path(os.environ.get("TEMP", ""))
    return [
        temp / "TAHOT_Gen-Deu.txt",
        temp / "TAHOT_Jos-Est.txt",
        temp / "TAHOT_Job-Sng.txt",
        temp / "TAHOT_Isa-Mal.txt",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the TAHOT Hebrew/Aramaic OT SQLite database."
    )
    parser.add_argument(
        "--tahot-source",
        type=Path,
        action="append",
        default=None,
        help="TAHOT source file. Pass four times for full production build.",
    )
    parser.add_argument(
        "--tbesh-source",
        type=Path,
        default=Path(os.environ.get("TEMP", "")) / "TBESH.txt",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_TAHOT_DATABASE_PATH)
    parser.add_argument("--tbesh-output", type=Path, default=DEFAULT_TBESH_DATABASE_PATH)
    parser.add_argument(
        "--audit-output",
        type=Path,
        default=GENERATED_DATA_DIR / "tahot_ot_import_audit.json",
    )
    parser.add_argument("--prototype-fixtures", action="store_true")
    args = parser.parse_args()

    if args.prototype_fixtures:
        tahot_sources = [project_path("tests", "fixtures", "tahot_ruth_psa_sample.tsv")]
        tbesh_source = project_path("tests", "fixtures", "tbesh_ruth_psa_sample.tsv")
        require_all_books = False
        dataset_name = "TAHOT Ruth/Psalm 23 prototype"
    else:
        tahot_sources = args.tahot_source or _default_full_tahot_sources()
        tbesh_source = args.tbesh_source
        require_all_books = True
        dataset_name = "TAHOT Hebrew/Aramaic OT"

    missing_sources = [path for path in [*tahot_sources, tbesh_source] if not path.exists()]
    if missing_sources:
        missing = "\n".join(str(path) for path in missing_sources)
        raise FileNotFoundError(f"Missing Hebrew source file(s):\n{missing}")

    tbesh_count = import_tbesh_lexicon_database(tbesh_source, args.tbesh_output)
    report = import_tahot_database(
        tahot_sources,
        args.output,
        tbesh_source_path=tbesh_source,
        dataset_name=dataset_name,
        source_version="STEPBible-Data master snapshot",
        require_all_books=require_all_books,
        atomic=True,
        audit_output_path=args.audit_output,
    )

    print(f"TAHOT database: {report.database_path}")
    print(f"TAHOT rows read: {report.rows_read}")
    print(f"Surface words imported: {report.tokens_imported}")
    print(f"Embedded TBESH matches: {report.lexicon_entries_imported}")
    print(f"TBESH database: {args.tbesh_output}")
    print(f"TBESH entries imported: {tbesh_count}")
    print(f"Books: {', '.join(report.books)}")


if __name__ == "__main__":
    main()
