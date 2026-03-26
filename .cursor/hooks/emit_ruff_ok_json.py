"""Parse ruff format+check log and emit one JSON line for Cursor afterFileEdit hook."""  # noqa: E501

from __future__ import annotations

import json
import re
import sys


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: emit_ruff_ok_json.py <log_path>", file=sys.stderr)
        sys.exit(2)
    path = sys.argv[1]
    text = open(path, encoding="utf-8", errors="replace").read()

    reformatted = 0
    unchanged = 0
    m = re.search(r"(\d+)\s+files?\s+reformatted", text)
    if m:
        reformatted = int(m.group(1))
    m = re.search(r"(\d+)\s+files?\s+left\s+unchanged", text)
    if m:
        unchanged = int(m.group(1))

    check_passed = bool(re.search(r"All checks passed!|Found 0 errors\.", text, re.I))  # noqa: E501

    out = {
        "event": "afterFileEdit",
        "status": "ok",
        "ruff": {
            "format": {"reformatted": reformatted, "unchanged": unchanged},
            "check": {"passed": check_passed},
        },
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
