# Weaver

Weaver is a journal and note taker that quietly connects what you write. Capture a passing thought or a longer reflection; people, memories, and useful next steps emerge from your entries.

## Status

Working prototype for the Nebius × NVIDIA Global AI Hackathon, targeting the Best Apps and Agents track.

See the [hackathon readiness checklist](docs/hackathon-readiness.md) for verified requirements, remaining submission items, and the October 30 deadline.

Drop in a note → Weaver saves it immediately → Nemotron connects people, categorizes details, and updates profiles in the background. Notes, profiles, organization status, and correction history persist in SQLite. No review or approval step is required for remembering notes. Inference runs on NVIDIA Nemotron through Nebius Token Factory; there is no simulated AI fallback.

This version also supports automatic birthday updates and duplicate consolidation, shared-note links to people, optional editing after organization, source notes, deleting a note and its memories, and JSON export. Plans and explicit relationships have their own categories.

## Planned first version

- Drop in notes; automatically connect people and organize source-backed profile updates.
- Remember interests, important dates, shared context, and commitments across sessions.
- Suggest relevant activities, follow-ups, meetings, and introductions.
- Run birthday preparation, commitment review, and meeting preparation skills.
- Create reminders and prepare messages; require approval for external actions.
- Inspect, correct, delete, and export stored memories.

## Stack

- React and TypeScript for the interface.
- Python and FastAPI for application logic and typed tools.
- SQLite for local, persistent application memory.
- NVIDIA Nemotron served through Nebius Token Factory for runtime inference.

Hermes Agent, OpenShell, reminders, and scheduled workflows are planned; they are not integrated in this prototype. The For you page provides a first set of local, source-backed suggestions.

## Structure

- `frontend/`: interface implementation.
- `backend/`: application services and Weaver tools.
- `skills/`: reusable agent workflows.
- `tests/`: memory, permission, and action verification.
- `docs/`: product and architecture decisions.
- `examples/`: fictional demo notes and fixtures.

## Run locally

Requires Python 3.11+ and Node.js 20.19+ or 22.12+. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
cp .env.example .env  # Only if you do not already have .env.
```

Set `NEBIUS_API_KEY` in `.env`. Never commit your key. The provided model and endpoint must be available to your Token Factory account.

Build the interface and start Weaver:

```sh
npm --prefix frontend install
npm --prefix frontend run build
sh start.sh
```

Open **http://127.0.0.1:8000**. The app runs locally, without accounts. Do not expose this prototype to the public internet.

For interface development, run the backend and frontend in separate terminals:

```sh
.venv/bin/python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

```sh
npm --prefix frontend run dev
```

Open **http://127.0.0.1:5173**. The development server forwards `/api` to the backend. Keep the key exclusively in the root `.env`; do not put it in frontend configuration.

## Try the first flow

1. Choose a fictional sample note or paste one from `examples/fictional-notes.md`.
2. Select **Save note**. The note is saved immediately; keep writing while organization runs in the background.
3. Weaver extracts details with source quotes, connects them to named people, assigns categories, and saves profiles automatically.
4. Click a person's chip below a completed note, or open **People**, to see the resulting profile.
5. Use **Edit** on a saved memory if you want to change its person, category, or text. Prior versions and original source quotes remain available.
6. Refresh or restart Weaver: saved profiles persist, and unfinished automatic work resumes.

Categories include important dates, lasting interests, one-off plans, commitments, explicit relationships, and shared context. “Joshua wants to go to the mall” is a plan, not a lasting interest. Known profiles and relevant active memories are supplied to Nemotron to connect canonical names, identify repeated facts, and recognize corrections. Only profiles whose name tokens occur in the new note are included as context.

Names match case-insensitively with normalized whitespace; Confirmed aliases connect alternate names to their canonical profile; similarity alone never merges people. People with identical names are not distinguished in this prototype. Model interpretation can be wrong: inspect sources or edit memories whenever needed. Dates remain text; reminders and external actions are not implemented.

Repeated facts retain provenance from each note with one active copy. A new birthday replaces the old birthday, while other categories only replace memories when the model identifies a specific correction. Replaced details remain in history. Deleting a replacement note restores the nearest available prior memory.

If organization fails, the note remains saved with **Retry**. Older pending reviews offer **Organize** (using the current model and categorization rules) and optional **Inspect**. The manual review API remains available via `automatic: false`, but the app defaults to automatic organization. Processing uses one local background worker and a durable SQLite queue. Failed notes wait for an explicit retry to avoid repeated API charges; queued/interrupted work resumes after restart.

## Validation

```sh
.venv/bin/python -m pytest tests -q
npm --prefix frontend run build
```

Tests use temporary databases and a stubbed model response; they do not spend API credits. Live app submissions use the configured Nebius model and incur its normal usage charges.

The default database is `data/weaver.sqlite3` (excluded from Git). Back it up to preserve your workspace. JSON export is available in the sidebar; importing exports is not implemented yet.

## Data handling

Store notes and profiles in user-controlled storage. Submitted notes and relevant existing profile memories are sent to Nebius for inference; this is not local-only processing. Keep real personal data, credentials, databases, and private uploads outside version control. Use fictional data for public examples.

## License

MIT. See [LICENSE](LICENSE).

## For you

Open **For you** in the sidebar for a short list of source-backed suggestions:

- **Follow-ups:** active commitments, including undated promises. A passed date is a cue to check whether the commitment is done, not a claim that it was missed.
- **Dates:** birthdays within 30 days and dated plans within 14 days. Birthday month/day values recur annually. Relative phrases use the source note’s local date; “next week” remains a Monday–Sunday range rather than an invented day. Ambiguous numeric dates and uncertain dates are not scheduled. Supported dates include month names, ISO dates, today, tomorrow, this/next week, clear weekday references such as “on Friday,” and “in N days.” Ambiguous “next Friday” is left undated. Month/day plans without a year use the calendar occurrence nearest the source note date.
- **Connections:** tentative matches between different people's explicit plans and interests across a small set of activity topics. These are local topic-based suggestions, not inferred friendships or a general semantic recommendation agent.

Each suggestion shows the underlying memory, its reason, and expandable source quotes with links to the note and person. **Mark done** and **Dismiss** hide a card; **Done & dismissed → Restore** brings it back. Actions persist across restarts and are included in JSON export. Corrected/inactive memories and deleted source notes stop contributing suggestions. Birthday actions apply to that occurrence, so a birthday can surface again next year.

This first version derives suggestions locally from the memories already extracted by Nemotron. Opening For you makes no additional model call. It refreshes while the page is open and when the window regains focus; optional browser alerts can notify you while Weaver is open. It does not contact people, create calendar events, or run a scheduled external agent.

## People: About

Each profile begins with **About**, a compact overview selected from its current source-backed memories. Background, birthdays, interests, explicit connections, and current plans retain their original wording; promises remain under **All memories**. Up to five facts are shown, with dated source links. The overview is recomputed locally as memories are added, corrected, or deleted, with no additional model call. It does not infer personality traits from anecdotes. Expand **All memories** for editing, complete categories, shared-note links, and correction history.

## People: aliases and merging

Under **Names & profiles**, add a confirmed nickname or alternate name. New notes using it join the existing profile automatically. Search matches aliases as well as profile names. Aliases cannot silently take over a name already assigned to someone else.

A small question in People highlights possible duplicate profiles, including common nicknames such as Josh/Joshua or first-name/full-name matches. **Same person** combines them under the displayed fuller name and records the other name as an alias. **Different people** remembers the distinction. This does not interrupt saving notes. Similar names with different surnames are not proposed as duplicates.

You can also select any other profile under **Merge into another profile**. All notes, memory IDs, source quotes, and previous versions are preserved. About and For you use the combined profile. Conflicting birthdays remain visible in About and do not generate date suggestions until corrected. Done/dismissed suggestions retain their actions when their source facts carry across the merge.

**Undo merge** is available under Names & profiles while the combined profile remains unchanged. Once new notes or edits change it, undo is disabled to avoid discarding subsequent work; use a memory's Edit control to move individual facts. Removing an alias affects future matching, without moving existing memories.

Identity resolution is local and uses confirmed names/aliases. Nemotron must return names as written in each new note, verified against that note, so it cannot silently expand an uncertain nickname. Unconfirmed nicknames remain separate profiles with an optional matching question. This first version cannot distinguish two people recorded under exactly the same canonical name; use distinguishing names such as full names or labels.

## Journal and quick notes

The **Journal** workspace opens directly into a journal entry. Quick capture is secondary:

- **Journal entry:** a larger writing space, an optional title, and a chosen entry date. New entries and edits support up to 5,000 characters and preserve paragraph breaks. Both writing modes show a live character counter; over-limit drafts remain intact, with saving disabled until shortened or split. Existing saved entries and their history are preserved.
- **Quick note:** the small button in the journal editor’s toolbar opens a popup. Capture a passing thought without replacing the journal editor. Closing the popup preserves its draft.

Both save immediately to the existing local database and organize in the background. Titles are included as context for extracting source-backed memories. A reflection without named people remains a complete saved entry; it does not need a profile or suggestion to be valuable. The original notes remain available as quick notes after the schema migration.

Journal and quick-note drafts are saved separately in this browser's local storage on this device and restored after refreshing. Saving or closing one does not alter the other. Existing shared drafts migrate to their original journal or quick-note surface. The draft indicator reports when browser storage is unavailable. Saving an entry clears its draft after the server acknowledges it. Unsubmitted drafts are not included in the database export. Entries and relevant memories are sent to Nebius for inference when submitted, as with the original note flow; opening or drafting an entry does not call the model.

The entries list can be filtered by Notes/Journal and searched by title or text. Open an entry to read its full text. People, About, aliases, and For you use the same underlying memories. For a backdated journal entry, relative date phrases use its chosen entry date rather than the later capture date. This is a plain-text first version; saved entries support editing and version history. Rich-text formatting is not implemented yet.

## Editing and version history

Open an entry and choose **Edit entry** to change its title, type, date, or body. **Save changes** immediately saves a new revision and updates connected information in the background. Identical content does not create another revision. Edits made from a stale tab return a conflict instead of overwriting a newer version.

**Version history** opens previous versions. **Restore this version** copies the selected version into a new revision; it does not erase later history. Version history is included in JSON export, and deleting an entry removes all of its versions.

Automatic facts from revised text are retired immediately so stale suggestions do not linger during processing or an inference failure. Re-extraction reads the new revision, and an older in-flight response cannot publish facts into a newer revision. If processing fails, the edited writing and its history remain saved; retry from the entry list.

Manually corrected memories are retained with their original source revision. Re-extraction does not overwrite that entry's manually corrected person/category slots, so additional automatic facts in those slots may be skipped. Use All memories to revise a manual correction. Source links from profiles, About, and For you open the actual entry version used as evidence. Relative dates in retained manual memories continue to use that source version's entry date.

Editing drafts are saved locally in this browser. Closing the reader preserves a draft; Cancel edit discards it. If a draft predates the current entry, it can be reviewed and explicitly recovered. Version history and source snapshots are stored in SQLite; private writing is excluded from Git.

### Reliable entry processing

Weaver partitions long entries into exact source sections of up to 1,200 characters, preferring paragraph and sentence boundaries. A section that reaches the response limit is split further, with a bounded fallback. Nemotron 3 Nano extraction enables reasoning to improve actor attribution and interpretation of short, casual entries. Only its structured final answer is parsed and stored; processing can take longer in the background, while the writing is saved immediately. The same section sizes, response allowance, and bounded retries apply. Connection failures, timeouts, and transient provider errors are retried up to three times with short backoff; authentication failures stop immediately. Invalid source quotes, structured responses, clear actor mistakes, or lost personal deadlines receive corrective retries with specific feedback, with profile facts removed from retry context to prevent source confusion. Persistent validation failures also use the bounded smaller-section fallback and stop if the source still cannot be verified.

Section results are source-checked, deduplicated, and published in one transaction only after every section succeeds. A failed section never leaves half a set of new memories. Saved writing, revision history, and manual corrections remain intact. Interrupted queued work resumes on server restart. More than 40 distinct facts produces a clear message asking for smaller entries rather than silently dropping facts.

### Personal reminders and profile tasks

Automatic organization now extracts the author's own tasks, plans, loose reminders, and goals alongside named-person memories. Personal items require exact source quotes and never create a person record. New entries extract both kinds together; existing writing remains intact. Personal reminders are versioned through their source entries and retired when the source is revised or deleted. Repeated equivalent personal wording shares suggestion status and can retain several source links.

For you and the journal sidebar have All / Personal / Others filters, alongside suggestion-type filters. People always includes a You tab, even before any other profiles exist. You lists personal intentions; other profiles list the plans and commitments involving that person, including undated plans outside the main suggestion feed's date windows. Profile tasks use compact rows grouped by date passed, upcoming, and anytime, with small check and dismiss buttons plus source links. Done, dismissed, and restored statuses are shared across views. Optional browser alerts are available; no calendar changes are made.

### Due dates and snooze

Use the small calendar button on a task to set a due date. Leaving the date empty moves it to Anytime; **Use date from writing** restores the original inferred date or date range. Manual dates change when a task needs attention without rewriting its source entry or resetting Done/Dismiss status.

The clock button snoozes a reminder until Tomorrow, In 3 days, Next week, or a custom future day. Its due date stays unchanged. Snoozed items remain accessible in a separate **Snoozed** section, with **Bring back** to return them immediately. They rejoin the active list on the selected local calendar day; open views refresh on focus and at least once a minute. Marking done, dismissing, or restoring clears a pending snooze.

Timing changes persist in SQLite and are shared by For you, the journal sidebar, You, and individual profiles. Open views and tabs refresh after changes; when browser storage is unavailable the periodic refresh remains a fallback. Duplicate sources share timing, profile merges preserve it, and inactive/deleted source facts do not appear just because an old timing setting exists. Timing settings are included in JSON export. Birthdays and possible connections are not editable task reminders. Optional browser notifications can surface due and returning snoozed reminders; calendar integration is not enabled.

### Completion from journal entries

New entries can record explicit completed personal actions, such as “I renewed my passport.” Weaver matches the action and object conservatively against existing one-off personal tasks, plans, and reminders. Exact source quotes and the surrounding sentence are checked; uncertain, negated, future, third-party, vague, and recurring-goal completions do not close tasks. Ambiguous matches to separate scheduled obligations are left open. Matching is intentionally limited to clear supported action forms rather than fuzzy semantic guesses.

Automatic completions appear under Done & dismissed with a Completion source link. They are source-backed events rather than manual status changes. Editing, restoring, or deleting a completion entry reconciles its automatic effect; stale in-flight extraction cannot publish a completion after an edit. Explicit Done, Dismiss, and Restore actions take precedence, and Restore stays open across reloads. New reminders written after an earlier completion remain open. Completed actions are not recreated as reminders from the same source passage.

Typographic apostrophe variants in extracted names and quotes are mapped back to the exact original source spelling; paraphrased quotes and expanded names remain invalid. Exact existing facts are normalized as duplicates, without turning real corrections into duplicates or merging similar names.

### Optional browser alerts

Use the bell in the top bar to enable or turn off alerts for this browser. Nothing requests notification permission until you click **Enable alerts**. Supported desktop browsers require localhost or HTTPS and browser/OS notification permission. Mobile browsers may not support this first version.

While Weaver is open, it checks once a minute and on focus or suggestion changes. Due and overdue reminders, including dated birthdays, and returning snoozed items are grouped into a single alert. Undated items wait until they have a due date or a snooze return date; completed, dismissed, currently snoozed items and suggested connections do not alert. Dates have day precision: delivery starts on the relevant local calendar day, with no specific time of day. Browser suspension or device sleep can delay alerts until Weaver resumes.

Alerts contain only a count; clicking one opens For you. SQLite stores device-scoped receipts so tabs/reloads do not repeat the same due-date or snooze occurrence. Unacknowledged delivery reservations expire after two minutes; network acknowledgment failures are retried before new alerts. Delivery is best effort: browser/OS suppression and a crash between showing and recording an alert cannot be fully detected. Opt-in and a random device identifier live in browser storage; clearing it resets that browser's preference and delivery identity. Notifications do not work after Weaver is closed; there is no push service or background scheduler.

Notification tests: `.venv/bin/python -m pytest tests/test_notifications.py -q` and `node --test tests/notification_delivery.test.mjs`.

### Repeating reminders

Use the small repeat icon beside a task's calendar and snooze controls in For you, the journal sidebar, You, or a person's profile. Choose **Daily**, **Weekly**, or **Monthly** and a next due date. Clear recurring intentions in newly organized writing can also create schedules automatically. The repeat editor identifies schedules set from writing and lets you change or stop them.

**Mark done** or **Skip** archives that occurrence and schedules the next date after both its current due date and today in your chosen timezone. Daily/weekly repeats preserve their calendar cadence. Monthly repeats preserve the chosen day (January 31 → February 28/29 → March 31). An unresolved occurrence stays pending/overdue; missed periods do not create an accumulating backlog when you handle it. Completing a future occurrence early advances from that scheduled date.

**More → Dismiss repeat** stops the schedule and moves the reminder to Done & dismissed. The small × in the journal sidebar and profile task cards does the same for a repeating reminder. **More → Skip once** only advances one occurrence. The More dropdown also contains due date, repeat and snooze settings, leaving Mark done as the primary card action. A dismissed schedule stays off after reprocessing; Restore brings back a one-time reminder, and you can explicitly enable repeating again. Previous completed/skipped occurrences remain in history.

Snoozing hides the current occurrence without changing its cadence. Editing a repeating task's due date changes the anchor for subsequent repeats. Choose **Doesn't repeat** to keep the pending occurrence as a one-off reminder. Completed/skipped occurrences remain in Done & dismissed with their dates; Restore reopens only that historical occurrence without changing the ongoing schedule. Restored historical occurrences have check/dismiss controls, rather than editable dates/repeats.

Repeating reminders are completed explicitly with the check button; completion statements extracted from writing do not automatically advance a repeat. Source links are preserved, deleting/retiring all source facts removes the series from views, and profile merges/undo retain the schedule and occurrence history. Schedules and occurrence history persist in SQLite and are included in JSON export. Optional browser notifications apply separately to each due occurrence.

Recurrence tests: `.venv/bin/python -m pytest tests/test_recurrence.py -q`.

### Workspace search

Use **Search** in the top bar (or **⌘K / Ctrl+K**) from any page. Search spans current entries, profiles and confirmed aliases, active person memories, and personal/people tasks, including done, dismissed, snoozed, and past recurring occurrences. The persistent You profile is included. Filters show totals for Entries, People, Memories, and Tasks; results link to profiles and source entries, retaining the exact source revision for extracted facts.

This is local keyword search, with case/accent normalization, word-prefix matching, and all query words matched in any order. Exact names/titles rank higher; open tasks rank ahead of otherwise equivalent completed occurrences. It does not use embeddings, synonyms, or natural-language question answering, and makes no Nebius/Nemotron calls. Entries awaiting organization are searchable as writing; retired facts are excluded from memory/profile/task matches while the original writing remains searchable as an entry. Deleted entries disappear from results.

Queries are limited to 200 characters, results initially show 20, and Show more expands up to 100 before asking for a narrower query. Query/filter state lives only in the mounted search component. Debouncing and stale-response guards prevent old requests from replacing newer results. The existing journal entry filter and People name filter remain available. Search tests: `.venv/bin/python -m pytest tests/test_search.py -q`.

### Repeats from your writing

New and re-organized entries recognize clear author intentions such as “I need to water the plants every Saturday,” “Stretch daily,” “Pay rent on the first of each month,” and “I need to call Mira every Friday.” Nemotron preserves the cadence and an exact source quote; local code validates the surrounding source sentence and creates the schedule in the same transaction as the organized facts. Merely opening a page never creates or resets a schedule, and old organized entries are not automatically backfilled.

Supported schedules include every/each day or daily, one explicit weekday (every Saturday / on Saturdays), and an explicit numeric/ordinal day of each month (including its last day). Bare weekly/monthly phrases need an explicit supported start date; the source entry's date anchors relative dates. Monthly day 31 uses a shorter month's last day and returns to day 31 afterward. Unresolved past occurrences stay overdue until handled, following the existing repeat behavior. Quick notes use Weaver's existing America/New_York source-day convention; the resulting automatic schedule stays stable when viewed in another timezone.

Uncertain, negated, historical, third-party habits, questions, multi-day patterns, alternate weeks, bounded periods, and specific clock times do not create automatic repeat schedules. Unsupported wording remains available as a regular task/goal when extracted; the repeat control remains available for manual scheduling. Automatic detection uses a conservative set of author-intention/action forms, rather than claiming to understand every possible phrasing.

Changing repeat frequency or its due-date anchor makes the schedule manual. Turning it off is remembered, including after reprocessing, source restore, and profile merge/undo, so the same source fact does not silently re-enable it. Current occurrence progress and completion history are preserved when a supported source fact is re-organized unchanged. The inferred schedule remains linked to its source entry; retired/deleted facts leave the active views. Schedule origin and manual-choice records are included in JSON export.

Tests: `.venv/bin/python -m pytest tests/test_auto_recurrence.py -q`.

### Organization and suggestion quality

Extraction sends only relevant profile context for each entry section, validates source quotes and actor/timing consistency, and retries explicit omissions rather than silently accepting them. Equivalent task cards retain all source links; their completion, date, snooze and repeat controls update the grouped sources together. Different people, schedules and monthly anchors stay separate. For you prioritizes overdue items, today, upcoming dates and commitments ahead of open-ended suggestions.

See the [October 27 optimization report](reports/2026-10-27-optimization/report.md) for the eight-case live benchmark, measured processing times, limitations and regression coverage.
