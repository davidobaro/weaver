# Weaver hackathon readiness

Checked October 27, 2026. Target: **Best Apps and Agents**, chosen by the project owner.

**Official deadline: October 30, 2026, 10:00 a.m. Pacific / 1:00 p.m. EDT (New York).** Aim to finish the package October 29 and submit by 11:00 a.m. New York time October 30.

Sources: [event overview](https://nebiusglobalaihackathon.devpost.com/) and [official rules](https://nebiusglobalaihackathon.devpost.com/rules), especially sections 1, 4, and 6. The rules take precedence if other event material differs.

## Verified implementation

| Item | Evidence | Status |
|---|---|---|
| Runtime Nebius use | Inference calls Token Factory; a fictional live extraction succeeded on October 27 | Ready |
| NVIDIA model | NVIDIA Nemotron 3 Nano in the inference configuration | Ready |
| Working application | Journal, People, You, For you, source links, editing/history, personal tasks and completion matching | Implemented |
| Public source and license | Public GitHub repository; GitHub detects MIT | Ready |
| Complete source | Required personal-reminder module and regression tests are now committed | Ready |
| Reproducible setup | Committed source copied to a clean temporary directory; new Python environment and locked dependencies installed; npm ci and frontend build succeeded | Verified |
| Automated verification | All 145 tests passed in that isolated environment; one existing dependency deprecation warning | Verified |
| Startup | Built frontend and API both returned HTTP 200 with an empty isolated database | Verified |

Repository inspected: `d3e03064ebccdce735afb4a8a928df186bc7a5fb`. Logs and fictional live results are in `reports/2026-10-27-hackathon/`. The tests did not edit the user's journal.

## Remaining submission requirements

- [ ] Supply a URL where judges can access a working demo or test build. The rules permit either, so a full public SaaS launch is unnecessary.
- [ ] Keep judge access free and functional through the end of judging, December 15, 2026. Judge access should not depend on the developer's laptop or require purchasing API credits.
- [ ] Record a working-product walkthrough, preferably about 2 minutes 30 seconds and strictly under 3 minutes. Show the real app and explain its actual Nebius/NVIDIA use.
- [ ] Upload that walkthrough as a **public YouTube video** and put its URL in Devpost. The existing promotional MP4 files are not evidence of a public upload or a complete runtime walkthrough.
- [ ] Finish the project description: audience/problem, demonstrated features, architecture, impact, limitations, and technology use.
- [ ] Add judge-specific access and testing instructions to the README when the access method is ready.
- [ ] Provide honest feedback on Token Factory and the NVIDIA model, based on observed use.
- [ ] Select Best Apps and Agents on the actual Devpost form; verify registration, team and entrant details.
- [ ] Review and submit every required field before the official cutoff.

The repository starts October 14, within the August 26–October 30 submission period. If any submitted project actually predates that period, include the required explanation of significant updates.

## Highest-priority blocker: judge access

The current application is intentionally local. `start.sh` binds to loopback; the middleware rejects non-local hosts and browser origins. It has no user accounts. An external address cannot simply be placed in front of it and assumed to work safely.

Recommended next task: prepare an isolated judge demo using fictional entries, server-side inference credentials, access protection, request/queue limits, and persistent storage. A packaged test build is also allowed; choose a route that judges can run freely and consistently. Do not expose the personal journal database or put the Nebius key in browser code or the repository.

No deployment or external publication was performed during this audit.

## Track and feature scope

The required stack is a runtime Nebius call or Nebius compute, plus an NVIDIA open-source model. Token Factory inference satisfies the Nebius part; hosting the UI on Nebius is not an additional requirement.

Best Apps and Agents fits the demonstrated journal/productivity workflow. The Personal AI track describes a broader always-on assistant with memory, reusable skills and tools. Its named framework examples do not establish a requirement to install every framework. For the selected track, Hermes, OpenShell, calendar sync and new notifications are not submission blockers.

Focus the demo on writing one entry, inspecting its people facts and personal task with sources, then showing completion from a later entry. Be explicit that notes persist locally by default but submitted text and relevant context are sent to Nebius for inference; do not claim fully offline processing.

Judging balances implementation, coherent design, real-world impact and originality. Demonstrate these rather than adding disconnected features.

## Deadline plan

| Date | Outcome |
|---|---|
| Oct 27 | Requirements verified; choose and start judge-access implementation |
| Oct 28 | Judge demo/test build usable; fictional walkthrough rehearsed; fix blockers |
| Oct 29 | Final video uploaded publicly; description, feedback and README complete; submission reviewed |
| Oct 30 before 11 a.m. New York | Submit and verify links; preserve a two-hour buffer before the official cutoff |
