"""Held-out grouping cases, excluded from candidate workspaces."""

def row(entry_id, user, project, start, end):
    return {"entry_id": entry_id, "user": user, "project": project, "start": start, "end": end}


ROWS = [
    row("1", "ben", "p", "2026-09-27T09:00:00+00:00", "2026-09-27T10:00:00+00:00"),
    row("2", "ana", "p", "2026-09-27T09:30:00+00:00", "2026-09-27T10:00:00+00:00"),
    row("3", "ana", "q", "2026-09-27T11:00:00+00:00", "2026-09-27T11:15:00+00:00"),
]

CASES = [
    ("empty_user", {"rows": [], "group_by": "user"}, []),
    ("user_grouping", {"rows": ROWS, "group_by": "user"}, [{"day": "2026-09-27", "user": "ana", "seconds": 2700}, {"day": "2026-09-27", "user": "ben", "seconds": 3600}]),
    ("default_project", ROWS, [{"day": "2026-09-27", "project": "p", "seconds": 5400}, {"day": "2026-09-27", "project": "q", "seconds": 900}]),
    ("explicit_project", {"rows": ROWS, "group_by": "project"}, [{"day": "2026-09-27", "project": "p", "seconds": 5400}, {"day": "2026-09-27", "project": "q", "seconds": 900}]),
]
