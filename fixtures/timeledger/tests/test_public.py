from timeledger.ledger import summarize


def test_same_day_project_summary():
    rows = [
        {"entry_id": "a", "user": "ana", "project": "alpha", "start": "2026-09-27T09:00:00+00:00", "end": "2026-09-27T10:00:00+00:00"},
        {"entry_id": "b", "user": "ben", "project": "alpha", "start": "2026-09-27T12:00:00+00:00", "end": "2026-09-27T12:30:00+00:00"},
    ]
    assert summarize(rows) == [{"day": "2026-09-27", "project": "alpha", "seconds": 5400}]
