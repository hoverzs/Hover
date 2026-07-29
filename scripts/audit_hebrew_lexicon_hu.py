from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bible_engine.hebrew_lexicon_translation_workflow import audit_hebrew_lexicon_hu  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the production Hebrew Hungarian lexicon JSON.")
    parser.add_argument("--lexicon", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit_hebrew_lexicon_hu(args.lexicon), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
