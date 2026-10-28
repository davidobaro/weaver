# Weaver reliability, processing speed and suggestion quality

Verified October 27, 2026 (local time). All benchmark writing is fictional, stored in isolated temporary SQLite databases. The user's journal database was not used for test writes.

## Results

| Measure | Baseline | Release |
| --- | ---: | ---: |
| Live acceptance cases passed | 7/8 | 8/8 |
| Median save acknowledgment | 3 ms | 2 ms |
| Median save-to-organized | 37.646 s | 12.339 s |
| Model requests | 9 | 9 |
| Prompt characters across requests | 55,867 | 31,913 |
| Existing-profile context characters | 8,079 | 494 |
| Reported total tokens | 31,404 | 28,106 |

Median organization time was 67.2% lower in this eight-entry comparison. Prompt text fell 42.9%; profile context fell 93.9%. These are sequential cloud runs, not a controlled latency guarantee. Save acknowledgment uses an in-process HTTP test client and excludes browser/network latency. Organization includes background extraction and publication. The longer entry needs two sections, so nine requests represent zero corrective retries in both final and baseline batches. The changes reduce unnecessary retry payloads and repair safe formatting locally; this batch does not demonstrate fewer calls.

## Live case matrix

| Case | Baseline | Release | Before seconds | After seconds |
| --- | --- | --- | ---: | ---: |
| mixed_names | Pass | Pass | 45.187 | 14.737 |
| correction | Pass | Pass | 27.894 | 13.211 |
| recurring_mixed | Pass | Pass | 33.501 | 10.515 |
| roles_and_completion | Fail | Pass | 50.043 | 10.774 |
| uncertain_repeat | Pass | Pass | 34.650 | 8.558 |
| aliases | Pass | Pass | 26.965 | 12.450 |
| context_heavy | Pass | Pass | 42.850 | 12.229 |
| long_journal | Pass | Pass | 40.642 | 20.996 |

The cases cover lowercase/new/accented names, birthday corrections, vague personal goals, daily/weekday/month-day recurring tasks, authored versus other-person completions, uncertain/historical/negated repeats, confirmed aliases, a profile with 75 irrelevant facts, and a long multi-section entry. Assertions inspect persisted facts, correction retirement, tasks, recurrence records, and completion effects, not only HTTP success. See benchmark.py for exact fictional text and acceptance assertions; baseline.json and release.json retain measurements and outputs.

## Reliability changes

- Fixed sentence boundaries: an unfinished intention in the following sentence no longer cancels a preceding completed action, deadline, or clear recurrence.
- Added bounded source coverage checks for omitted lowercase life updates and explicit concrete author intentions. Model retries must supply source-backed output; local code does not invent missing facts.
- Corrected literal moved-in/started-school updates to context instead of invented relationships.
- Repair quote whitespace/apostrophe formatting and harmless integer record metadata locally. Restore missing timing only from a short exact, single-intention quote that retains the action's words. Partial/compound/date-only evidence still requires validation.

Intermediate full runs each passed 7/8: optimized missed Eli's category; final omitted Eli; verified omitted rent's monthly intention. Those failures drove the category/subject/intention checks. The release batch is one fresh complete eight-case run; earlier passing cases were not combined to manufacture a pass.

## Processing changes

The extraction prompt is shorter while retaining actor, evidence, correction, timing, cadence, and duplicate requirements. Each section receives only mentioned profiles and up to twelve relevant facts per profile, with birthday and alias context retained when applicable. Full existing context remains available for final duplicate normalization. Corrective feedback sends the specific error and field guidance instead of the full schema. Model reasoning, response budget, and maximum retry safety remain enabled.

## Suggestion changes

Equivalent task wording shares one card, preserving every source quote and revision link. Different people, dates, goals, statuses, snoozes, repeat origins, and monthly anchor days remain distinct. Completing, dismissing, scheduling, snoozing, or changing a repeat applies to every grouped member in a single transaction. Search counts and browser alert claims use the same grouped feed.

The fictional quality fixture changes seven cards to six, merging two passport reminders. Its verified order is overdue bill, today's dentist call, upcoming application, undated commitment to Mira, undated passport task, then the possible connection. The browser check expanded the passport card and verified both original quotes and source buttons. See quality-results.json and quality-feed.png.

Grouping is conservative: synonyms and differently phrased semantic duplicates can still remain separate. Ranking favors overdue, current, and next-fourteen-day items before undated commitments and other tasks. Extraction remains probabilistic; eight cases prove these acceptance scenarios, not perfect recall for all writing. Automatic repeats retain their documented supported forms and manual override behavior.

## Verification and completion audit

- Reliability: all eight live scenarios pass in release.json; dedicated regression tests protect sentence boundaries, omitted details, quote repairs, category normalization, recurrence safety, and context selection.
- Speed: paired baseline/release measurements above; prompt/context/request metrics captured around actual Nebius chat completions.
- Quality: API tests cover grouping, actor/date/anchor separation, all controls, deletion survival, search totals, chronological ordering, and transaction rollback. Browser rendering confirms order and both source links.
- `.venv/bin/python -m pytest -q`: 303 passed, one existing Starlette/httpx deprecation warning.
- `node --test tests/notification_delivery.test.mjs tests/writing_drafts.test.mjs`: 12 passed.
- `npm run build --prefix frontend`: TypeScript and Vite production build passed.
- Restarted `bash start.sh` on port 8000; homepage, grouped-feed and search HTTP checks passed. The rendered preview showed overdue before today and undated tasks. The temporary fictional server was stopped.
- `git diff --check` passed; final implementation hashes match verified-source-sha256.json.

Run the opt-in live benchmark with `.venv/bin/python reports/2026-10-27-optimization/benchmark.py LABEL`. It uses the configured provider and incurs model usage. The normal deterministic tests do not require live provider calls. Baseline code snapshots are retained for comparison. Raw JSON artifacts contain fictional test data only.
