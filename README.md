# Weaver

A journal and note taker that quietly connects what you write.

## About

Useful details get buried in everyday writing: a friend's interests, a promise you made, or something you need to do for yourself. Weaver lets you capture the day naturally, then organizes those details into source-backed profiles and reminders without a separate tagging or review step.

Built for the **Nebius × NVIDIA Global AI Hackathon — Best Apps and Agents** track.

## Demo and judge access

| Resource | Status |
| --- | --- |
| Hosted demo or test build | Pending — URL and judge access instructions will be added here before submission. |
| Public YouTube walkthrough | Pending — a working-product walkthrough under three minutes will be linked here. |
| Source code | [github.com/davidobaro/weaver](https://github.com/davidobaro/weaver) |

The local application works using the setup below. Hosted judge access is not available yet; local setup requires your own Nebius Token Factory key. Final judge access must be free through December 15, 2026, with any required access instructions provided in the submission. See the [official rules](https://nebiusglobalaihackathon.devpost.com/rules).

## What it does

- **Journal and quick notes:** save writing immediately, organize in the background, and search, edit, or restore previous versions.
- **People and You:** collect facts about people and organize personal tasks in a persistent You profile, with links back to the writing behind each detail.
- **Insights:** surface a short digest of commitments, upcoming dates, personal reminders, and possible connections; support done, dismiss, snooze, and repeating reminders.
- **Verifiable extraction:** expand an entry's summary to inspect extracted facts and exact source quotes. Clear completion statements in later writing can close matching personal tasks.

## How it works

| Layer | Technology |
| --- | --- |
| Interface | React, TypeScript, Vite |
| Application and background organization | Python, FastAPI |
| Local storage | SQLite |
| Runtime AI | NVIDIA Nemotron 3 Nano through Nebius Token Factory |

Saving an entry queues background extraction. The backend sends the writing and relevant profile context to **Nebius Token Factory**, using `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` by default. Nemotron identifies people, facts, intentions, and completed actions; local code validates the source quotes and updates SQLite. Insights ranking, recurrence, and keyword search run locally without additional model calls.

Token Factory provides hosted inference, so development does not require running a GPU server. The current application uses Token Factory; Nebius AI Cloud, Serverless, Hermes, and OpenShell are not integrated.

## Setup

Requires **Python 3.11+**, **Node.js 20.19+ or 22.12+**, and a Nebius Token Factory key with access to the configured model. These commands target macOS/Linux.

```sh
git clone https://github.com/davidobaro/weaver.git
cd weaver
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
```

Copy `.env.example` to `.env` if you do not already have one. Set the following in the root `.env`:

```dotenv
NEBIUS_API_KEY=your_token_factory_key
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1
NEBIUS_MODEL=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B
```

Keep the key on the backend. Never commit `.env` or add the key to frontend configuration. Actual organization uses the provider API and consumes inference credits; there is no simulated AI fallback.

```sh
npm --prefix frontend ci
npm --prefix frontend run build
sh start.sh
```

Open **http://127.0.0.1:8000**. To start it again after setup, run `sh start.sh`. The local app has no accounts and is intended to stay on loopback.

For frontend development, run these in separate terminals:

```sh
.venv/bin/python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

```sh
npm --prefix frontend run dev
```

The development interface is at **http://127.0.0.1:5173** and forwards API requests to the backend.

## Try it

1. In **Journal**, save this fictional entry:

   > I met Leila after work. Leila loves pottery. I promised to send Leila the trail guide tomorrow. I need to pay the electricity bill tomorrow.

2. Wait for organization to finish. Expand the counts below the entry to verify the extracted details against their source quotes. Open **People** to inspect Leila and **You** for your personal task.
3. Open **Insights** to inspect the reminders and their sources. Save a second entry, “I paid the electricity bill.” After organization, check **Done & dismissed** for the matched personal task and completion source.

More fictional writing is available in [examples/fictional-notes.md](examples/fictional-notes.md). Processing time depends on the entry and provider response. If organization pauses, the original writing remains saved and **Retry** is available.

## Tests

```sh
.venv/bin/python -m pytest tests -q
npm --prefix frontend test
npm --prefix frontend run build
```

Automated tests use temporary databases and mocked provider responses; they do not require a live API key or spend inference credits.

## Data and limitations

Local entries and profiles persist in `data/weaver.sqlite3`, which is excluded from Git. Browser drafts are saved separately on the current device. The sidebar provides JSON export; importing exports is not implemented. Submitted writing and relevant profile context are sent to Nebius for inference, so processing is not fully offline.

Extraction can make mistakes; source quotes and editing make them inspectable. Search is keyword-based, connections are tentative topic matches, and completion matching is deliberately conservative. Browser notifications require opt-in and only work while Weaver is open. The app does not send messages, create calendar events, or run an always-on external assistant. Multi-user accounts and isolated hosted demo sessions are not implemented yet.

## Hackathon notes and technology feedback

The required runtime integration is the Token Factory inference call using NVIDIA Nemotron. Hosted inference simplified development; reliable extraction still needed source validation, bounded retries, and smaller sections for detailed entries. Model responses can omit facts, misattribute actors, lose timing, or exceed the response allowance. The backend checks these cases and preserves saved writing when organization fails.

Submission requirements and remaining judge-access/video items are tracked in [the readiness checklist](docs/hackathon-readiness.md). The [event page](https://nebiusglobalaihackathon.devpost.com/) and [official rules](https://nebiusglobalaihackathon.devpost.com/rules) describe the required demo, video, source, track selection, and technology feedback.

## Further reading

- [Updates.md](Updates.md): feature history and detailed implementation notes.
- [Design language](docs/design-language.md): shared layout and typography.
- `backend/`, `frontend/`, and `tests/`: application source and regression coverage.

## License

[MIT](LICENSE).
