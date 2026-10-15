# Weaver

Weaver is a journal and note taker that quietly connects what you write. Capture a passing thought or a longer reflection; people, memories, and useful next steps emerge from your entries.

## Status

First working prototype for the Nebius × NVIDIA Global AI Hackathon, Personal AI track.

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

This first version derives suggestions locally from the memories already extracted by Nemotron. Opening For you makes no additional model call. It refreshes while the page is open and when the window regains focus; it does not send notifications, contact people, create calendar events, or run a scheduled external agent.

## People: About

Each profile begins with **About**, a compact overview selected from its current source-backed memories. Background, birthdays, interests, explicit connections, and current plans retain their original wording; promises remain under **All memories**. Up to five facts are shown, with dated source links. The overview is recomputed locally as memories are added, corrected, or deleted, with no additional model call. It does not infer personality traits from anecdotes. Expand **All memories** for editing, complete categories, shared-note links, and correction history.

## People: aliases and merging

Under **Names & profiles**, add a confirmed nickname or alternate name. New notes using it join the existing profile automatically. Search matches aliases as well as profile names. Aliases cannot silently take over a name already assigned to someone else.

A small question in People highlights possible duplicate profiles, including common nicknames such as Josh/Joshua or first-name/full-name matches. **Same person** combines them under the displayed fuller name and records the other name as an alias. **Different people** remembers the distinction. This does not interrupt saving notes. Similar names with different surnames are not proposed as duplicates.

You can also select any other profile under **Merge into another profile**. All notes, memory IDs, source quotes, and previous versions are preserved. About and For you use the combined profile. Conflicting birthdays remain visible in About and do not generate date suggestions until corrected. Done/dismissed suggestions retain their actions when their source facts carry across the merge.

**Undo merge** is available under Names & profiles while the combined profile remains unchanged. Once new notes or edits change it, undo is disabled to avoid discarding subsequent work; use a memory's Edit control to move individual facts. Removing an alias affects future matching, without moving existing memories.

Identity resolution is local and uses confirmed names/aliases. Nemotron must return names as written in each new note, verified against that note, so it cannot silently expand an uncertain nickname. Unconfirmed nicknames remain separate profiles with an optional matching question. This first version cannot distinguish two people recorded under exactly the same canonical name; use distinguishing names such as full names or labels.

## Journal and quick notes

The **Journal** workspace has two writing modes in one shared flow:

- **Quick note:** capture a passing thought or conversation.
- **Journal entry:** a larger writing space, an optional title, and a chosen entry date. Entries support up to 30,000 characters and preserve paragraph breaks.

Both save immediately to the existing local database and organize in the background. Titles are included as context for extracting source-backed memories. A reflection without named people remains a complete saved entry; it does not need a profile or suggestion to be valuable. The original notes remain available as quick notes after the schema migration.

Drafts are saved in this browser's local storage on this device and restored after refreshing. The draft indicator reports when browser storage is unavailable. Saving an entry clears its draft after the server acknowledges it. Unsubmitted drafts are not included in the database export. Entries and relevant memories are sent to Nebius for inference when submitted, as with the original note flow; opening or drafting an entry does not call the model.

The entries list can be filtered by Notes/Journal and searched by title or text. Open an entry to read its full text. People, About, aliases, and For you use the same underlying memories. For a backdated journal entry, relative date phrases use its chosen entry date rather than the later capture date. This is a plain-text first version; post-save editing of entries and rich-text formatting are not implemented yet.
