#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path


def main() -> None:
    raw = os.environ.get("SKILLIT_INPUT_JSON", "{}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {}

    base = Path(payload.get("path", ".")).resolve()
    max_items = int(payload.get("max_items", 100))
    items = []
    for p in sorted(base.rglob("*")):
        if len(items) >= max_items:
            break
        rel = p.relative_to(base)
        items.append({"path": str(rel), "is_dir": p.is_dir()})

    out = {"base": str(base), "count": len(items), "items": items}
    sys.stdout.write(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
