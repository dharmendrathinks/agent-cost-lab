"""Private reference algorithm for fixture validation; not shipped to candidates."""

from collections import defaultdict
from datetime import datetime, time, timedelta, timezone


def summarize(rows, group_by="project"):
    if group_by not in ("project", "user"):
        raise ValueError("unsupported grouping")
    totals = defaultdict(int)
    seen = set()
    for index, row in enumerate(rows, start=2):
        try:
            if any(not isinstance(row.get(k), str) or not row[k].strip() for k in ("entry_id", "user", "project")):
                raise ValueError("missing identifier")
            if row["entry_id"] in seen:
                raise ValueError("duplicate entry_id")
            cursor = datetime.fromisoformat(row["start"])
            end = datetime.fromisoformat(row["end"])
            if cursor.tzinfo is None or end.tzinfo is None or cursor.utcoffset() is None or end.utcoffset() is None:
                raise ValueError("timezone is required")
            cursor = cursor.astimezone(timezone.utc)
            end = end.astimezone(timezone.utc)
            if end <= cursor:
                raise ValueError("non-positive interval")
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"row {index}: {exc}") from exc
        seen.add(row["entry_id"])
        while cursor < end:
            boundary = datetime.combine(cursor.date() + timedelta(days=1), time.min, tzinfo=timezone.utc)
            next_cursor = min(boundary, end)
            totals[(cursor.date().isoformat(), row[group_by])] += int((next_cursor - cursor).total_seconds())
            cursor = next_cursor
    return [{"day": day, group_by: group, "seconds": seconds} for (day, group), seconds in sorted(totals.items())]
