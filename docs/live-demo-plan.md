# Live demo implementation plan

Prepared October 29, 2026. Target: a hosted Weaver demo for the Best Apps and Agents submission, with isolated temporary workspaces and no persistent disk. Session support and the deployment files are implemented and locally verified. A Docker build and hosted deployment still need verification before sharing a public URL. See [deployment instructions](live-demo.md).

## Intended experience

1. Open the demo, receive a temporary workspace, and write in Journal immediately.
2. Save an entry; background organization updates People, You, and Insights as in the local app.
3. Reload or navigate between pages without losing the active session.
4. Use Reset demo to start a new workspace. Old work cannot publish into the replacement session.
5. After expiry or a server restart, show a clear session-ended message and offer a fresh workspace without replaying submissions.

Show a short notice: “Temporary demo. Entries are cleared after inactivity or a server restart. Submitted writing is processed by Nebius. Please use fictional details.” Provide an optional fictional example through the existing example flow; do not make a model call just because someone opens the site.

Closing a tab removes ordinary tab-scoped browser storage, but does not immediately notify the server to delete its data. Server cleanup follows the expiry policy. Browser recovery/duplicate-tab behavior is not a deletion guarantee.

## Architecture and defaults

- One Render web service serves the built React app and FastAPI from the same HTTPS origin.
- Use one application process/replica. Session registry, quotas, and temporary SQLite files belong to that process; multiple replicas would require a shared session/queue design and are outside this demo scope.
- `WEAVER_MODE=local` remains the default. Local mode retains the existing SQLite database and browser draft behavior.
- `WEAVER_MODE=demo` uses only a dedicated temporary directory. No fallback to the personal database is allowed.
- The backend issues an unguessable session credential. The browser stores it in `sessionStorage` and attaches it to API calls in an authorization header. Never put credentials in query strings or logs.
- Server-side session records map credentials to server-generated workspace paths. Clients never choose database paths.
- Proposed expiry: 60 minutes without a user interaction, with a 24-hour maximum session lifetime. Background polling alone must not keep an abandoned session alive. Active jobs have leases so cleanup cannot remove their database mid-write.
- On reset/expiry, revoke the workspace, cancel queued work, prevent running work from publishing, and remove SQLite/WAL/SHM files when all leases are released. An already-started provider request may still finish and consume credits.
- Nebius credentials live only in hosting secrets. There is no persistent disk, user-account system, or personal-data migration in this release.

## 1. Isolate backend workspaces

Main files: `backend/main.py`; new workspace/session module.

- Separate application mode/configuration from database selection.
- Refactor schema initialization and database access to accept a workspace explicitly. Do not switch the global `DB_PATH` per request.
- Resolve the workspace for every data endpoint: state, notes, extraction receipts, revisions, memory editing, people/aliases/merges, Insights actions/timing/repeats, search, notifications, and export.
- Pass the workspace and its generation explicitly into every background job, including jobs triggered by edit, restore, retry, and manual extraction. Do not depend on request-local context carrying across worker threads.
- Demo startup must neither read nor resume the local personal workspace's queue.
- Reject missing, malformed, expired, and revoked credentials without creating a database implicitly. Expose session bootstrap and a minimal health endpoint separately.

Acceptance: two sessions can both have note ID 1 without sharing reads, mutations, exports, search results, or background extraction results. Existing local-mode behavior remains covered by its regression suite.

## 2. Add browser session lifecycle

Main files: `frontend/src/api.ts`, `App.tsx`, `writingDrafts.ts`, `QuickNote.tsx`, `EntryReader.tsx`, `Notifications.tsx`, and `ForYou.tsx`.

- Bootstrap the session before fetching workspace data; share the same bootstrap promise across concurrent startup requests.
- Attach session credentials centrally in the API helper. On expiry, stop stale polling, clear stale workspace state, and show a fresh-session action. Never automatically replay a POST/PATCH after session replacement.
- In demo mode, keep journal, quick-note, and entry-edit drafts in session-scoped `sessionStorage`, using a shared storage adapter. Do not migrate unrelated local drafts into the demo.
- Scope reminder settings, delivery receipts, and suggestion-change signals to the session so another workspace does not inherit state.
- Replace the direct export anchor with an authenticated download request; revoke its temporary browser URL afterward.
- Add a compact temporary-session notice and Reset demo control. Reset clears all demo drafts, cached results, and stale requests as well as replacing the backend session.
- If session storage is unavailable, retain credentials in memory and explain that refreshing starts over.

Acceptance: reload restores the same active workspace; reset clears every writing surface and stale results; another visitor gets a different workspace. Local mode retains current draft persistence.

## 3. Bound public-demo workload

- Retain the existing 5,000-character entry limit.
- Proposed initial limits: 20 saved entries and 10 organization starts per session, one outstanding organization job per session, two running jobs globally, and four waiting jobs globally. Keep these configurable.
- Count retries, edits, restores, and manual extraction toward organization limits. Resetting a session must not bypass IP/global throttles.
- Rate-limit session creation and inference-triggering routes; bound active sessions, disk usage, and request body size.
- Add a configurable global provider-call ceiling; count internal retries and section fallback calls, not only saved notes. In-process counters reset after a process restart and are not a guaranteed billing cap; use provider spending controls where available.
- Return useful busy/quota responses, preserve an unsent browser draft, and avoid partially queued work when admission fails.
- Keep health checks lightweight: no session creation, user data, or live inference. Logs contain status/timing and error categories rather than entries, provider responses, API keys, or session credentials.

Acceptance: limits apply across all inference entry points, and a rejected request starts no provider job.

## 4. Package and configure hosting

Deliverables: multi-stage `Dockerfile`, `.dockerignore`, `render.yaml`, demo environment examples, and deployment instructions.

- Build the frontend in a Node stage, install locked Python dependencies in the runtime stage, and serve both through FastAPI.
- Exclude `.env`, local databases, uploads, reports, launch-video outputs, and other private/generated files from the build context.
- Bind the hosted server to `0.0.0.0:$PORT`, one application process, using a separate hosted entry point rather than changing the loopback-only local start command.
- Configure explicit allowed host/origin values for the hosted address; retain local-mode restrictions. Do not allow arbitrary origins.
- Add `/healthz` and configure it as the service health check. Start even when no demo sessions exist; validate required demo configuration without exposing secret values.
- Use an always-on service for the judging window if budget permits, without a persistent disk. Render Free is an optional preview fallback with idle sleep/cold-start and ephemeral-data limitations, not an availability guarantee.

Acceptance: build the container from a clean checkout with no `.env` or personal database, start it with runtime secrets, and verify the app and health endpoint respond.

## 5. Test isolation, lifecycle, and full product flow

Add focused automated coverage:

- Cross-session reads/mutations/search/export/revisions/merges/notification isolation, including identical object IDs.
- Background jobs publish only to their captured workspace; reset/expiry during queued, running, and retrying work cannot resurrect a session or recreate a deleted database.
- Expiry distinguishes user activity from periodic polling; cleanup respects active database/job leases.
- Admission limits are race-safe, count every inference path, and release capacity after failure/reset. Internal provider retries obey the global ceiling.
- Malformed credentials and path-like values cannot select files. Demo mode never reads/writes the personal database.
- Draft storage, authenticated downloads, bootstrap races, reset, stale response handling, and storage-unavailable behavior.

Run the backend regression suite, JavaScript suite, and frontend production build. Then browser-test two independent sessions through Journal → extraction summary → People/You → Insights → completion → reset, plus a mobile layout check. Use only fictional data for one bounded live Nebius smoke test after the mocked tests pass.

Acceptance: no cross-session data visibility; no personal files in the build; all checks pass; temporary data loss is clearly explained.

## 6. Deploy and finish judge access

- Connect the repository to Render and set backend secrets through the dashboard.
- Deploy, verify HTTPS, health checks, session isolation, and real inference on the hosted URL.
- Test reset, inactive expiry, cold restart, export, and provider failure behavior on the deployed build.
- Keep a stable demo URL, service funding, and provider credits available through the end of judging on December 15, 2026.
- Replace the README's pending demo field with the verified URL and actual access instructions. Keep the video field pending until the public YouTube walkthrough is supplied.
- Record the walkthrough against the deployed product; do not present unimplemented persistent accounts or background notifications after the app closes.

## Delivery order and estimate

| Stage | Estimate | Exit condition |
| --- | --- | --- |
| Backend isolation and lifecycle | 2–3 hours | Two sessions and worker jobs are isolated |
| Browser session support and reset | 1–2 hours | Drafts, API calls, and exports follow the session |
| Limits and deployment package | 1–2 hours | Bounded workload; clean container starts |
| Regression, browser, and live checks | 1–2 hours | Product flow and failure cases verified |
| Hosted deployment and README access | About 1 hour | Demo URL verified externally |

Allow roughly one focused workday (6–10 hours), with a buffer for hosting/account setup and live-model failures. Video recording and submission are separate. The highest-risk work is workspace isolation and background-job lifecycle; complete and test those before polishing the demo notice.

## Hosting references

- [Render Docker deployment](https://render.com/docs/docker)
- [Render health checks](https://render.com/docs/health-checks)
- [Render Free service limitations](https://render.com/docs/free)
