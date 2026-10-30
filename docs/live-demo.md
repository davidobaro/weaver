# Temporary live demo

Weaver has two runtime modes. `local` is the default and retains the original personal database and local drafts. `demo` creates isolated temporary server workspaces, with session credentials and drafts held in each browser tab. No persistent disk is needed.

## Run the demo locally

Complete the README setup, configure the root `.env` with your Nebius key, and build the interface. Then run:

```sh
sh start-demo.sh
```

Open **http://127.0.0.1:8001**. This leaves the local personal database alone. The demo starts empty; opening it makes no inference call. New independent tabs receive separate sessions, although browsers can copy session storage when duplicating a tab.

The local personal app still starts with `sh start.sh` at port 8000. After a code update, restart the backend and rebuild the frontend before testing.

## Deploy with Render

1. Review, commit, and push the deployment changes to the Weaver repository.
2. Create/sign into Render and authorize access to the repository.
3. Create a Blueprint using `render.yaml`. Review the resource plan before applying it: it specifies **one paid Starter web service**, manual deploys, and **no persistent disk**.
4. Enter `NEBIUS_API_KEY` in Render's secret environment-variable prompt. Keep the key out of the repository, frontend build, logs, and chat. The model and endpoint are specified in the Blueprint; confirm your account supports them.
5. Deploy. Render builds the Docker image and checks `/healthz`. Its own hostname is allowed automatically from `RENDER_EXTERNAL_HOSTNAME`. For a custom domain, add its exact hostname to `WEAVER_ALLOWED_HOSTS` and HTTPS origin to `WEAVER_ALLOWED_ORIGINS`.
6. Open the resulting HTTPS URL in two independent browser sessions. Verify that writing in one does not appear in the other. Test a fictional entry through Journal, its extraction summary, People/You, and Insights; then export and reset.
7. Restart the service to check the session-ended screen. Verify that a fresh session works afterward. Keep the demo URL, walkthrough link, and access instructions in the README current.

Keep exactly **one service replica and one Uvicorn process**. The two organization threads are separate from server processes. Sessions and quota counters are process-local; adding replicas requires shared session/queue infrastructure and is outside this demo design.

The hosted command binds to `0.0.0.0:$PORT`, disables access logs, and serves the API and built interface together. Nothing here changes the loopback binding of the local `start.sh`.

Render's [Docker guide](https://render.com/docs/docker), [Blueprint reference](https://render.com/docs/blueprint-spec), and [health checks](https://render.com/docs/health-checks) describe these settings. The [Free plan](https://render.com/docs/free) sleeps after inactivity and can lose session data on spin-down; use an always-on service for reliable judging access. Creating the paid service is a separate account/billing action.

## Optional container check

Requires a working Docker installation. From the repo root:

```sh
docker build -t weaver-demo .
docker run --rm --env-file .env -e WEAVER_MODE=demo -p 8001:8000 weaver-demo
```

The multi-stage build copies only backend source, its dependency lock, the compiled frontend, and the hosted start script into the runtime image. `.dockerignore` excludes secrets, personal databases, and generated artifacts. Secrets are supplied at runtime, not as build arguments. No local data volume is mounted.

## Lifecycle and limits

Defaults can be changed using backend environment variables listed in `.env.example`:

| Control | Default |
| --- | --- |
| Idle expiry | 60 minutes without explicit interaction |
| Maximum session lifetime | 24 hours |
| Active sessions | 100 |
| Saved entries per session | 20 |
| Organization starts per session | 10, including retry/edit/restore/manual extraction |
| Outstanding jobs per session | 1 |
| Organization workers / waiting jobs | 2 / 4 |
| Session starts per client network per hour | 10 |
| Organization admissions per client network per hour | 30 |
| API writes per session's originating network | 120 per minute |
| Provider-call allowance | 500 per process monotonic-day bucket |
| API request body / entry text | 64 KiB / 5,000 characters |

The provider-call allowance counts internal retries and section fallbacks. Counters reset when the process restarts; this is an abuse bound, **not a guaranteed billing cap**. Review provider spending controls/credits separately. Network limits use the server-observed client address; behind a proxy with no trusted forwarding configuration, visitors may share a conservative network limit. Do not trust arbitrary client-supplied forwarding headers.

Periodic state/Insights polling and notification checks do not extend session lifetime. Explicit interactions send a throttled activity signal. Expiry is enforced when a request/job touches the workspace; idle files are also swept every 30 seconds. An active extraction holds a lease so cleanup cannot remove its database mid-write.

Reset revokes the old session before creating another. Queued jobs are cancelled; a running provider call may finish and incur usage, but cannot publish into the revoked workspace. Files are removed after its active leases finish. A server restart/redeploy clears every workspace and causes existing tabs to show the session-ended screen. Closing a tab is not an immediate server-deletion signal; expiry remains the cleanup mechanism.

If browser session storage is unavailable, credentials/drafts are kept only in memory and refreshing starts over. Drafts, edit recovery, notification receipts, and downloads are scoped to the session. Reset clears those drafts and cached UI data. The API rejects stale responses after a session replacement and never silently replays a mutation into a new workspace.

Use fictional data. Entries and relevant context still go to Nebius for inference. HTTPS protects transport but does not make this an offline application. No user accounts or long-term recovery are provided by demo mode.

## Checks before sharing the URL

```sh
.venv/bin/python -m pytest tests -q
npm --prefix frontend test
npm --prefix frontend run build
```

The automated suites use isolated temporary storage and mocked provider calls. `tests/test_demo.py` checks API/job isolation, expiry, reset during extraction, limits, host/origin checks, and personal-database separation. `tests/demo_session.test.mjs` checks browser session/draft behavior, authenticated exports, reset failure, and stale/expired API responses.

Verify the container build and the hosted flow before describing the demo as live. Keep the hosting service and provider credits available through December 15, 2026 for judging. Session data itself is deliberately temporary.
