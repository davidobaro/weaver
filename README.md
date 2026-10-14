# Weaver

Weaver turns scattered notes about the people in your life into lasting memory, timely reminders, and thoughtful ways to connect.

## Status

Repository initialized for the Nebius × NVIDIA Global AI Hackathon, Personal AI track. The application and integrations are not implemented yet.

## Planned first version

- Add notes and contacts; review source-backed profile updates.
- Remember interests, important dates, shared context, and commitments across sessions.
- Suggest relevant activities, follow-ups, meetings, and introductions.
- Run birthday preparation, commitment review, and meeting preparation skills.
- Create reminders and prepare messages; require approval for external actions.
- Inspect, correct, delete, and export stored memories.

## Proposed stack

- React and TypeScript for the interface.
- Python and FastAPI for application logic and typed tools.
- SQLite for local, persistent application memory.
- Hermes Agent for skills, scheduled reviews, and tool orchestration.
- NVIDIA OpenShell for runtime access controls.
- NVIDIA Nemotron served through Nebius Token Factory for runtime inference.

Hermes/OpenShell deployment and Nebius connectivity must be verified before this stack is considered integrated. NemoClaw is a possible deployment route.

## Structure

- `frontend/`: interface implementation.
- `backend/`: application services and Weaver tools.
- `skills/`: reusable agent workflows.
- `tests/`: memory, permission, and action verification.
- `docs/`: product and architecture decisions.
- `examples/`: fictional demo notes and fixtures.

## Development

No installation or run commands exist yet. They will be added with the first runnable implementation. Copy `.env.example` to `.env` when configuring inference; keep API keys out of Git.

## Data handling

Store notes and profiles in user-controlled storage. Relevant excerpts are sent to Nebius for inference; this is not local-only processing. Keep real personal data, credentials, databases, and private uploads outside version control. Use fictional data for public examples.

## License

MIT. See [LICENSE](LICENSE).
