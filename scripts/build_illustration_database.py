from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from illustration_engine.aesop_importer import import_aesop_book
from illustration_engine.arany_laszlo_importer import import_arany_laszlo_book
from illustration_engine.baldwin_importer import import_baldwin_book
from illustration_engine.book_of_300_anecdotes_importer import import_book_of_300_anecdotes
from illustration_engine.english_jests_and_anecdotes_importer import import_english_jests_book
from illustration_engine.gulistan_importer import import_gulistan_book
from illustration_engine.illustration_sqlite import (
    DEFAULT_DATABASE_PATH,
    check_integrity,
    create_schema,
)
from illustration_engine.jataka_importer import import_jataka_book
from illustration_engine.jataka_parser import JATAKA_TALES_1912, MORE_JATAKA_TALES_1922
from illustration_engine.merenyi_laszlo_importer import import_merenyi_laszlo_book
from illustration_engine.merenyi_laszlo_parser import MERENYI_1_RESZ, MERENYI_2_RESZ
from illustration_engine.paths import RAW_DATA_DIR


DEFAULT_JATAKA_TALES_SOURCE = RAW_DATA_DIR / "pg62514_jataka_tales.txt"
DEFAULT_MORE_JATAKA_TALES_SOURCE = RAW_DATA_DIR / "pg7518_more_jataka_tales.txt"
DEFAULT_AESOPS_FABLES_SOURCE = RAW_DATA_DIR / "pg21_aesops_fables.txt"
DEFAULT_ARANY_LASZLO_SOURCE = RAW_DATA_DIR / "pg38852_arany_laszlo_eredeti_nepmesek.txt"
DEFAULT_MERENYI_LASZLO_1_SOURCE = RAW_DATA_DIR / "pg39419_merenyi_laszlo_eredeti_nepmesek_1resz.txt"
DEFAULT_MERENYI_LASZLO_2_SOURCE = RAW_DATA_DIR / "pg39386_merenyi_laszlo_eredeti_nepmesek_2resz.txt"
DEFAULT_BALDWIN_SOURCE = RAW_DATA_DIR / "pg18442_baldwin_fifty_famous_stories_retold.txt"
DEFAULT_BOOK_OF_300_ANECDOTES_SOURCE = RAW_DATA_DIR / "pg15413_book_of_300_anecdotes.txt"
DEFAULT_GULISTAN_SOURCE = RAW_DATA_DIR / "pg13060_persian_literature_vol2_gulistan.txt"
DEFAULT_ENGLISH_JESTS_SOURCE = RAW_DATA_DIR / "pg49370_english_jests_and_anecdotes.txt"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build/update the local illustration SQLite database from configured sources."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="Path to the SQLite database (created if missing; existing data is kept).",
    )
    parser.add_argument(
        "--jataka-tales-source",
        type=Path,
        default=DEFAULT_JATAKA_TALES_SOURCE,
        help="Path to the raw PG #62514 'Jataka Tales' plain-text file.",
    )
    parser.add_argument(
        "--more-jataka-tales-source",
        type=Path,
        default=DEFAULT_MORE_JATAKA_TALES_SOURCE,
        help="Path to the raw PG #7518 'More Jataka Tales' plain-text file.",
    )
    parser.add_argument(
        "--aesops-fables-source",
        type=Path,
        default=DEFAULT_AESOPS_FABLES_SOURCE,
        help="Path to the raw PG #21 'Three hundred Aesop's fables' plain-text file.",
    )
    parser.add_argument(
        "--arany-laszlo-source",
        type=Path,
        default=DEFAULT_ARANY_LASZLO_SOURCE,
        help="Path to the raw PG #38852 'Eredeti népmesék' plain-text file.",
    )
    parser.add_argument(
        "--merenyi-laszlo-1-source",
        type=Path,
        default=DEFAULT_MERENYI_LASZLO_1_SOURCE,
        help="Path to the raw PG #39419 'Eredeti népmesék (1. rész)' plain-text file.",
    )
    parser.add_argument(
        "--merenyi-laszlo-2-source",
        type=Path,
        default=DEFAULT_MERENYI_LASZLO_2_SOURCE,
        help="Path to the raw PG #39386 'Eredeti népmesék (2. rész)' plain-text file.",
    )
    parser.add_argument(
        "--baldwin-source",
        type=Path,
        default=DEFAULT_BALDWIN_SOURCE,
        help="Path to the raw PG #18442 'Fifty Famous Stories Retold' plain-text file.",
    )
    parser.add_argument(
        "--book-of-300-anecdotes-source",
        type=Path,
        default=DEFAULT_BOOK_OF_300_ANECDOTES_SOURCE,
        help="Path to the raw PG #15413 'The Book of Three Hundred Anecdotes' plain-text file.",
    )
    parser.add_argument(
        "--gulistan-source",
        type=Path,
        default=DEFAULT_GULISTAN_SOURCE,
        help="Path to the raw PG #13060 'The Persian Literature, Volume 2' (Gulistan) plain-text file.",
    )
    parser.add_argument(
        "--english-jests-source",
        type=Path,
        default=DEFAULT_ENGLISH_JESTS_SOURCE,
        help="Path to the raw PG #49370 'English Jests and Anecdotes' plain-text file.",
    )
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(args.output)
    try:
        create_schema(connection)

        for spec, source_path in (
            (JATAKA_TALES_1912, args.jataka_tales_source),
            (MORE_JATAKA_TALES_1922, args.more_jataka_tales_source),
        ):
            if not source_path.exists():
                print(f"SKIP {spec.source_code}: raw source not found at {source_path}")
                continue
            report = import_jataka_book(connection, spec=spec, raw_text_path=source_path)
            print(
                f"Jataka import: source={report.source_code}, "
                f"parsed={report.parsed_count}, inserted={report.inserted_count}, "
                f"skipped_existing={report.skipped_existing_count}, "
                f"raw_sha256={report.raw_file_sha256}"
            )

        if args.aesops_fables_source.exists():
            report = import_aesop_book(connection, raw_text_path=args.aesops_fables_source)
            print(
                f"Aesop import: source={report.source_code}, "
                f"parsed={report.parsed_count}, inserted={report.inserted_count}, "
                f"skipped_existing={report.skipped_existing_count}, "
                f"raw_sha256={report.raw_file_sha256}"
            )
        else:
            print(f"SKIP PG_AESOPS_FABLES_TOWNSEND: raw source not found at {args.aesops_fables_source}")

        if args.arany_laszlo_source.exists():
            report = import_arany_laszlo_book(connection, raw_text_path=args.arany_laszlo_source)
            print(
                f"Arany László import: source={report.source_code}, "
                f"parsed={report.parsed_count}, inserted={report.inserted_count}, "
                f"skipped_existing={report.skipped_existing_count}, "
                f"raw_sha256={report.raw_file_sha256}"
            )
        else:
            print(
                f"SKIP PG_ARANY_LASZLO_EREDETI_NEPMESEK: raw source not found at "
                f"{args.arany_laszlo_source}"
            )

        for spec, source_path in (
            (MERENYI_1_RESZ, args.merenyi_laszlo_1_source),
            (MERENYI_2_RESZ, args.merenyi_laszlo_2_source),
        ):
            if not source_path.exists():
                print(f"SKIP {spec.source_code}: raw source not found at {source_path}")
                continue
            report = import_merenyi_laszlo_book(connection, spec=spec, raw_text_path=source_path)
            print(
                f"Merényi László import: source={report.source_code}, "
                f"parsed={report.parsed_count}, inserted={report.inserted_count}, "
                f"skipped_existing={report.skipped_existing_count}, "
                f"raw_sha256={report.raw_file_sha256}"
            )

        if args.baldwin_source.exists():
            report = import_baldwin_book(connection, raw_text_path=args.baldwin_source)
            print(
                f"Baldwin import: source={report.source_code}, "
                f"parsed={report.parsed_count}, inserted={report.inserted_count}, "
                f"skipped_existing={report.skipped_existing_count}, "
                f"raw_sha256={report.raw_file_sha256}"
            )
        else:
            print(
                f"SKIP PG_BALDWIN_FIFTY_FAMOUS_STORIES_RETOLD: raw source not found at "
                f"{args.baldwin_source}"
            )

        if args.book_of_300_anecdotes_source.exists():
            report = import_book_of_300_anecdotes(
                connection, raw_text_path=args.book_of_300_anecdotes_source
            )
            print(
                f"Book of 300 Anecdotes import: source={report.source_code}, "
                f"parsed={report.parsed_count}, inserted={report.inserted_count}, "
                f"skipped_existing={report.skipped_existing_count}, "
                f"raw_sha256={report.raw_file_sha256}"
            )
        else:
            print(
                f"SKIP PG_BOOK_OF_300_ANECDOTES: raw source not found at "
                f"{args.book_of_300_anecdotes_source}"
            )

        if args.gulistan_source.exists():
            report = import_gulistan_book(connection, raw_text_path=args.gulistan_source)
            print(
                f"Gulistan import: source={report.source_code}, "
                f"parsed={report.parsed_count}, inserted={report.inserted_count}, "
                f"skipped_existing={report.skipped_existing_count}, "
                f"raw_sha256={report.raw_file_sha256}"
            )
        else:
            print(f"SKIP PG_GULISTAN_SADI_ROSS: raw source not found at {args.gulistan_source}")

        if args.english_jests_source.exists():
            report = import_english_jests_book(
                connection, raw_text_path=args.english_jests_source
            )
            print(
                f"English Jests and Anecdotes import: source={report.source_code}, "
                f"parsed={report.parsed_count}, inserted={report.inserted_count}, "
                f"skipped_existing={report.skipped_existing_count}, "
                f"raw_sha256={report.raw_file_sha256}"
            )
        else:
            print(
                f"SKIP PG_ENGLISH_JESTS_AND_ANECDOTES: raw source not found at "
                f"{args.english_jests_source}"
            )

        integrity = check_integrity(connection)
        if integrity != "ok":
            raise SystemExit(f"Integrity check failed after import: {integrity}")
        connection.commit()
        print(f"Database ready: {args.output} (integrity_check={integrity})")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
