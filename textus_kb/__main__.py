"""CLI entry point: ``python -m textus_kb``."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        from textus_kb.health import main as health_main

        return health_main([])

    command = args[0]
    rest = args[1:]

    if command in {"health", "check"}:
        from textus_kb.health import main as health_main

        return health_main(rest)
    if command == "retrieve":
        from textus_kb.retrieval import main as retrieve_main

        return retrieve_main(rest)

    print(
        f"Unknown command: {command!r}. "
        "Use: python -m textus_kb [health|retrieve] ...",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
