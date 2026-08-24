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
    if command == "context":
        from textus_kb.context_builder import main as context_main

        return context_main(rest)
    if command == "entity":
        from textus_kb.entity_cli import main as entity_main

        return entity_main(rest)
    if command == "shadow":
        from textus_kb.shadow import main as shadow_main

        return shadow_main(rest)
    if command == "shadow-report":
        from textus_kb.shadow_report import main_report

        return main_report(rest)
    if command == "shadow-compare":
        from textus_kb.shadow_report import main_compare

        return main_compare(rest)
    if command == "prompt-preview":
        from textus_kb.prompt_composer import main as prompt_preview_main

        return prompt_preview_main(rest)

    print(
        f"Unknown command: {command!r}. "
        "Use: python -m textus_kb [health|retrieve|context|entity|shadow|"
        "shadow-report|shadow-compare|prompt-preview] ...",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
