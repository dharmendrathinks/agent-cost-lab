"""Work-session parsing and UTC-day allocation."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone


def summarize(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    """Return project seconds by UTC day in stable day/project order.

    The initial fixture intentionally contains a midnight-allocation bug.
    """
    totals: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        start = datetime.fromisoformat(row["start"]).astimezone(timezone.utc)
        end = datetime.fromisoformat(row["end"]).astimezone(timezone.utc)
        elapsed = int((end - start).total_seconds())
        totals[(start.date().isoformat(), row["project"])] += elapsed
    return [
        {"day": day, "project": project, "seconds": seconds}
        for (day, project), seconds in sorted(totals.items())
    ]
