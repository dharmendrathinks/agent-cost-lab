# timeledger

`timeledger` reads work sessions and returns elapsed seconds grouped by UTC day and project. Each entry has `entry_id`, `user`, `project`, `start`, and `end`. Timestamps must include an offset. A session occupies the half-open interval `[start, end)`. UTC dates, not the timestamp's written local date, determine allocation. An endpoint exactly at midnight contributes no time to the next day. Each entry is allocated independently: overlapping entries add their own elapsed time rather than being merged or de-duplicated. For each entry, the sum of allocated seconds equals its elapsed duration. Same-day results must remain unchanged.

The initial version puts every session on its starting UTC date and has limited input validation and grouping options. Each task manifest declares one requested change and its public requirements. Edit only `timeledger/ledger.py` for the assigned task. The public development test covers normal same-day behavior. Independent acceptance tests run outside the candidate workspace.

Input rows are CSV with columns `entry_id,user,project,start,end`. The interface accepts timestamp strings with ISO 8601 offsets. See `sample.csv`.
