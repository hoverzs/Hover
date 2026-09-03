"""Build the isolated Commentary DB v1 SQLite store.

No network access by default. Creates an empty v1 database, imports a
local fixture JSON, imports one or more real Calvin commentary ThML/XML
files (already on disk, or fetched on demand via --calvin-fetch using the
pinned source manifest), or builds the full production 3-source combined
store (Calvin + JFB + Matthew Henry) via --combined / --combined-fetch.
Source-independent schema: no source-specific field exists outside each
source's own import path.

The combined modes never duplicate the Calvin/JFB/Henry parsing logic —
they call the existing per-source fetch functions (``calvin_source_fetch.
fetch_all_sources``, ``jfb_source_fetch.fetch_source``, ``henry_source_
fetch.fetch_all_volumes``) and the existing generic orchestrator
(``combined_commentary.import_combined_commentary_corpus``), which itself
reuses each source's own importer and ``commentary_sqlite.
merge_commentary_documents``.

Writing directly to the production path: ``combined_commentary.
import_combined_commentary_corpus`` refuses to write straight to
``DEFAULT_DATABASE_PATH`` (a deliberate guard so test/dev combined builds
can never clobber the real production store by accident). This script
respects that guard rather than weakening it: --combined/--combined-fetch
always build into a private staging file next to the requested --output
first, then atomically ``os.replace`` that staging file onto --output only
after a full successful build AND a post-build ``commentary_runtime.
get_status()`` sanity check confirm it is a valid, available Commentary
database. A failed build never leaves a partial file at --output.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from textus_kb import commentary_runtime
from textus_kb.importers.calvin_commentary_thml import (
    CalvinCommentaryImportError,
    import_calvin_commentary_sqlite,
    import_calvin_corpus_from_manifest,
)
from textus_kb.importers.calvin_source_fetch import (
    CalvinSourceFetchError,
    fetch_all_sources as fetch_all_calvin_sources,
    load_source_manifest as load_calvin_manifest,
)
from textus_kb.importers.combined_commentary import (
    IMPORT_MODE_COMBINED_COMMENTARY,
    CombinedCommentaryImportError,
    import_combined_commentary_corpus,
)
from textus_kb.importers.commentary_sqlite import (
    DEFAULT_DATABASE_PATH,
    DEFAULT_FIXTURE_PATH,
    CommentaryImportError,
    create_empty_commentary_database,
    import_commentary_sqlite,
)
from textus_kb.importers.henry_source_fetch import (
    HenrySourceFetchError,
    fetch_all_volumes as fetch_all_henry_volumes,
    load_source_manifest as load_henry_manifest,
)
from textus_kb.importers.jfb_source_fetch import (
    JfbSourceFetchError,
    fetch_source as fetch_jfb_source,
    load_source_manifest as load_jfb_manifest,
)
from textus_kb.qa.commentary_corpus_qa import (
    format_qa_report_human,
    generate_commentary_corpus_qa,
)


def _atomic_move_into_place(staging_path: Path, output_path: Path) -> None:
    """Move a fully-built database from a private staging path onto the
    requested output path. Retries briefly on Windows PermissionError
    (a transient AV/indexer file lock), mirroring ``commentary_sqlite.
    _replace_atomically``'s own retry loop."""
    for attempt in range(5):
        try:
            os.replace(staging_path, output_path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))


def _build_combined(output: Path, *, fetch: bool, run_qa: bool) -> int:
    if fetch:
        try:
            fetch_all_calvin_sources()
        except CalvinSourceFetchError as exc:
            print(f"Calvin source fetch failed: {exc}", file=sys.stderr)
            return 1
        jfb_manifest = load_jfb_manifest()
        try:
            fetch_jfb_source(jfb_manifest.source)
        except JfbSourceFetchError as exc:
            print(f"JFB source fetch failed: {exc}", file=sys.stderr)
            return 1
        try:
            fetch_all_henry_volumes()
        except HenrySourceFetchError as exc:
            print(f"Henry source fetch failed: {exc}", file=sys.stderr)
            return 1

    calvin_entries = load_calvin_manifest()
    jfb_manifest = load_jfb_manifest()
    henry_manifest = load_henry_manifest()

    missing: list[str] = []
    missing.extend(
        f"Calvin: {e.local_path}" for e in calvin_entries if not e.local_path.is_file()
    )
    if not jfb_manifest.source.local_path.is_file():
        missing.append(f"JFB: {jfb_manifest.source.local_path}")
    missing.extend(
        f"Henry volume {v.volume}: {v.local_path}"
        for v in henry_manifest.volumes
        if not v.local_path.is_file()
    )
    if missing:
        print(
            "Missing raw source file(s) for the combined build "
            "(fetch them first, e.g. with --combined-fetch):\n  "
            + "\n  ".join(missing),
            file=sys.stderr,
        )
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    staging_fd, staging_name = tempfile.mkstemp(
        prefix=f".{output.stem}.combined-build.",
        suffix=".tmp.sqlite3",
        dir=output.parent,
    )
    os.close(staging_fd)
    staging_path = Path(staging_name)
    staging_path.unlink()  # import_commentary_sqlite must create this path itself

    try:
        try:
            report = import_combined_commentary_corpus(
                calvin_entries=calvin_entries,
                jfb_xml_path=jfb_manifest.source.local_path,
                jfb_book_entries=list(jfb_manifest.books),
                henry_manifest=henry_manifest,
                database_path=staging_path,
                atomic=True,
                import_mode=IMPORT_MODE_COMBINED_COMMENTARY,
            )
        except (CombinedCommentaryImportError, CommentaryImportError) as exc:
            print(f"Combined commentary build failed: {exc}", file=sys.stderr)
            return 1

        _atomic_move_into_place(staging_path, output)
    finally:
        if staging_path.exists():
            staging_path.unlink()

    runtime_status = commentary_runtime.get_status(output)
    if not runtime_status.available:
        print(
            "Post-build sanity check failed: commentary_runtime.get_status() "
            f"reports unavailable ({runtime_status.reason}: {runtime_status.detail}).",
            file=sys.stderr,
        )
        return 1

    payload = report.to_dict()
    payload["database_path"] = str(output)
    payload["runtime_status"] = {
        "available": runtime_status.available,
        "reason": runtime_status.reason,
        "database_path": runtime_status.database_path,
    }
    if run_qa:
        qa_report = generate_commentary_corpus_qa(output)
        payload["qa"] = asdict(qa_report)
        print(format_qa_report_human(qa_report), file=sys.stderr)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the local Commentary DB v1 SQLite store."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--empty",
        action="store_true",
        help="Create an empty v1 schema with store_metadata only.",
    )
    mode.add_argument(
        "--fixture",
        nargs="?",
        const=str(DEFAULT_FIXTURE_PATH),
        metavar="PATH",
        help=(
            "Import a local fixture JSON. "
            f"Defaults to {DEFAULT_FIXTURE_PATH.as_posix()} when PATH is omitted."
        ),
    )
    mode.add_argument(
        "--calvin-thml",
        nargs="+",
        metavar="PATH",
        help=(
            "Import one or more real Calvin commentary ThML/XML files "
            "(already on disk) into a single combined store."
        ),
    )
    mode.add_argument(
        "--calvin-fetch",
        action="store_true",
        help=(
            "Fetch every source in the Calvin commentary source manifest "
            "(textus_kb/data/calvin_commentary_source_manifest.json), "
            "verify each against its pinned raw_sha256, then import all of "
            "them into a single combined store."
        ),
    )
    mode.add_argument(
        "--combined",
        action="store_true",
        help=(
            "Build the full production 3-source store (Calvin + JFB + "
            "Matthew Henry) from raw source files already present on disk "
            "(no network access). Fails closed and lists exactly which raw "
            "files are missing rather than building a partial store."
        ),
    )
    mode.add_argument(
        "--combined-fetch",
        action="store_true",
        help=(
            "Fetch every Calvin, JFB, and Matthew Henry raw source file per "
            "their pinned manifests (verifying each against its raw_sha256), "
            "then build the full production 3-source combined store."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="Path to the generated SQLite database.",
    )
    parser.add_argument(
        "--qa",
        action="store_true",
        help=(
            "After a successful build, run the generic Commentary corpus QA "
            "and include it in the output (human-readable summary on "
            "stderr, full structured report under the 'qa' key on stdout)."
        ),
    )
    args = parser.parse_args(argv)

    if args.empty:
        report = create_empty_commentary_database(args.output)
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 0

    if args.fixture is not None:
        report = import_commentary_sqlite(
            fixture_path=args.fixture,
            database_path=args.output,
        )
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 0

    if args.combined or args.combined_fetch:
        return _build_combined(args.output, fetch=args.combined_fetch, run_qa=args.qa)

    if args.calvin_fetch:
        try:
            fetch_all_calvin_sources()
        except CalvinSourceFetchError as exc:
            print(f"Calvin source fetch failed: {exc}", file=sys.stderr)
            return 1
        entries = load_calvin_manifest()
        try:
            report, parse_reports = import_calvin_corpus_from_manifest(
                entries, database_path=args.output
            )
        except (CalvinCommentaryImportError, CommentaryImportError) as exc:
            print(f"Calvin commentary import failed: {exc}", file=sys.stderr)
            return 1
    else:
        try:
            report, parse_reports = import_calvin_commentary_sqlite(
                list(args.calvin_thml), database_path=args.output
            )
        except (CalvinCommentaryImportError, CommentaryImportError) as exc:
            print(f"Calvin commentary import failed: {exc}", file=sys.stderr)
            return 1
    payload = report.to_dict()
    payload["calvin_sources"] = [pr.to_dict() for pr in parse_reports]
    if args.qa:
        qa_report = generate_commentary_corpus_qa(args.output)
        payload["qa"] = asdict(qa_report)
        print(format_qa_report_human(qa_report), file=sys.stderr)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
