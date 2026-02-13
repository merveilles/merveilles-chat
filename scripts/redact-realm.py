#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SENSITIVE = re.compile(
    r"(secret|password|private[_-]?key|token|credential)", re.IGNORECASE
)


def redact(node: Any) -> Any:
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if isinstance(value, str) and value and SENSITIVE.search(str(key)):
                out[key] = "__PLACEHOLDER__"
            else:
                out[key] = redact(value)
        return out

    if isinstance(node, list):
        return [redact(item) for item in node]

    return node


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Redact sensitive fields in a Keycloak realm export JSON file"
    )
    parser.add_argument("input", type=Path, help="Input JSON file path")
    parser.add_argument("output", type=Path, help="Output JSON file path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    content = json.loads(args.input.read_text())
    redacted = redact(content)
    args.output.write_text(json.dumps(redacted, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
