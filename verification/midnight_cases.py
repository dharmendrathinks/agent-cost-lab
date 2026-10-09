"""Held-out examples and expected results; never copied into candidate workspaces."""

CASES = [
    (
        "cross_midnight",
        [{"entry_id": "1", "user": "a", "project": "p", "start": "2026-09-27T23:30:00+00:00", "end": "2026-09-28T00:30:00+00:00"}],
        [{"day": "2026-09-27", "project": "p", "seconds": 1800}, {"day": "2026-09-28", "project": "p", "seconds": 1800}],
    ),
    (
        "exact_midnight",
        [{"entry_id": "2", "user": "a", "project": "p", "start": "2026-09-27T23:00:00+00:00", "end": "2026-09-28T00:00:00+00:00"}],
        [{"day": "2026-09-27", "project": "p", "seconds": 3600}],
    ),
    (
        "offset_and_three_days",
        [{"entry_id": "3", "user": "a", "project": "p", "start": "2026-09-28T01:30:00+02:00", "end": "2026-09-30T02:30:00+02:00"}],
        [{"day": "2026-09-27", "project": "p", "seconds": 1800}, {"day": "2026-09-28", "project": "p", "seconds": 86400}, {"day": "2026-09-29", "project": "p", "seconds": 86400}, {"day": "2026-09-30", "project": "p", "seconds": 1800}],
    ),
    (
        "overlap_additive",
        [
            {"entry_id": "4", "user": "a", "project": "p", "start": "2026-09-27T23:30:00+00:00", "end": "2026-09-28T00:30:00+00:00"},
            {"entry_id": "5", "user": "b", "project": "p", "start": "2026-09-27T23:45:00+00:00", "end": "2026-09-28T00:15:00+00:00"},
        ],
        [{"day": "2026-09-27", "project": "p", "seconds": 2700}, {"day": "2026-09-28", "project": "p", "seconds": 2700}],
    ),
    (
        "same_day_preserved",
        [{"entry_id": "6", "user": "a", "project": "q", "start": "2026-09-27T10:00:00-04:00", "end": "2026-09-27T11:00:00-04:00"}],
        [{"day": "2026-09-27", "project": "q", "seconds": 3600}],
    ),
]
