# Weaver

Weaver turns scattered notes about the people in your life into lasting memory, timely reminders, and thoughtful ways to connect.

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

Hermes Agent, OpenShell, reminders, scheduled workflows, and recommendations are planned; they are not integrated in this prototype.

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

Names match case-insensitively with normalized whitespace; Nemotron can use canonical names from relevant profiles when unambiguous. People with identical names are not distinguished in this prototype. Model interpretation can be wrong: inspect sources or edit memories whenever needed. Dates remain text; reminders and external actions are not implemented.

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
