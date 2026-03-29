"""Parse pytest stdout log and emit one JSON line for Cursor stop hook."""

from __future__ import annotations

import json
import re
import sys


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: emit_pytest_ok_json.py <log_path>", file=sys.stderr)
        sys.exit(2)
    path = sys.argv[1]
    text = open(path, encoding="utf-8", errors="replace").read()

    def n(word: str) -> int:
        m = re.search(rf"\b(\d+)\s+{word}\b", text)
        return int(m.group(1)) if m else 0

    errors = 0
    for pat in (r"\b(\d+)\s+errors\b", r"\b(\d+)\s+error\b"):
        m = re.search(pat, text)
        if m:
            errors = int(m.group(1))
            break

    out = {
        "event": "stop",
        "status": "ok",
        "pytest": {
            "passed": n("passed"),
            "skipped": n("skipped"),
            "failed": n("failed"),
            "errors": errors,
        },
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
