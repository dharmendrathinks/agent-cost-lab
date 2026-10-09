"""Held-out validation cases, excluded from candidate workspaces."""

def row(entry_id="a", user="ana", project="p", start="2026-09-27T09:00:00+00:00", end="2026-09-27T10:00:00+00:00"):
    return {"entry_id": entry_id, "user": user, "project": project, "start": start, "end": end}


CASES = [
    ("missing_id", [row(entry_id="")], {"error": "ValueError", "contains": "row 2"}),
    ("blank_user", [row(user="  ")], {"error": "ValueError", "contains": "row 2"}),
    ("missing_project", [{k: v for k, v in row().items() if k != "project"}], {"error": "ValueError", "contains": "row 2"}),
    ("naive_second_row", [row(), row(entry_id="b", start="2026-09-27T11:00:00")], {"error": "ValueError", "contains": "row 3"}),
    ("invalid_date", [row(start="not-a-date")], {"error": "ValueError", "contains": "row 2"}),
    ("nonpositive", [row(end="2026-09-27T09:00:00+00:00")], {"error": "ValueError", "contains": "row 2"}),
    ("duplicate", [row(), row()], {"error": "ValueError", "contains": "row 3"}),
    ("first_error_wins", [row(project=""), row(entry_id="")], {"error": "ValueError", "contains": "row 2"}),
    ("valid_offsets", [row(start="2026-09-27T11:00:00+02:00", end="2026-09-27T12:00:00+02:00")], [{"day": "2026-09-27", "project": "p", "seconds": 3600}]),
]
