#!/usr/bin/env python3
import json
import os
import sys


def main() -> None:
    raw = os.environ.get("SKILLIT_INPUT_JSON", "{}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {}

    text = str(payload.get("text", ""))
    lines = [ln for ln in text.splitlines() if ln.strip()]
    out = {
        "line_count": len(lines),
        "preview": lines[:20],
        "hint": "Provide this summary to coding skill for faster review.",
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
