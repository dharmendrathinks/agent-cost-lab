"""Trusted fixture entry point; independent verifier restricts candidate edits."""

import json
import sys

from .ledger import summarize


def main() -> None:
    payload = json.load(sys.stdin)
    try:
        if isinstance(payload, dict):
            result = summarize(payload["rows"], group_by=payload.get("group_by", "project"))
        else:
            result = summarize(payload)
    except ValueError as exc:
        result = {"error": "ValueError", "message": str(exc)}
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
