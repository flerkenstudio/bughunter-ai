# Alan integration

## Status: local execution verified, cloud workflow integration not claimed

This repository is built and driven inside an Alan software-engineering session (local runtime).
What that exercised:

- Alan ran shell commands in this workspace to install dependencies, build the dashboard, start the
  API and run the test suites.
- Alan created the repository, the demo store, the seeded bug, the backend, the runner and the
  dashboard, and verified the failure-to-verification loop end to end.
- No Alan cloud workflow, voice SDK or hosted agent session was used. The older **Alan.app
  voice-assistant SDK is a different product** from this software-engineering environment; do not
  conflate them.

What is **not** verified and must be confirmed against the live event rules:

- An Alan cloud task triggering a real run through this API and returning the result.
- Any required SDK, credential, workflow or submission contract imposed by OpenFire.
- Multi-user access, authentication, or exposing the API beyond localhost.

The test engine is deliberately independent of Alan, so the product stays usable while that
integration is validated.

## Integration contract

Any Alan task or workflow can drive BugHunter AI through HTTP:

1. `GET /api/health` — confirm the service and the demo target.
2. `GET /api/projects` — resolve the seeded demo project id.
3. `POST /api/runs` with `{"project_id": "…", "scope": ["login","checkout"], "mode": "reproduce",
   "max_duration_seconds": 120}`.
4. Poll `GET /api/runs/{id}/live` until `active` is false.
5. Read `GET /api/runs/{id}/bugs` for confirmed bugs, evidence URLs and patch ids.
6. `POST /api/patches/{patch_id}/verify` and report the returned `verification_status` — never
   assume `verified`.
7. Put the final run status, bug ids, patch id and artifact links into the task result.

## Task text that can be handed to an Alan agent

> Investigate the checkout flow of the local Nimbus Supply demo store with BugHunter AI.
>
> 1. Start the API (`uvicorn backend.app.main:app --port 8000`) if it is not already up, and confirm
>    `GET /api/health` reports `api ok`.
> 2. Start a run for the seeded project with scope `["login","checkout"]` and mode `reproduce`.
> 3. Poll until the run is terminal. Do not describe a failure as a bug unless the run status is
>    `completed` and a bug record exists with reproduction evidence.
> 4. Summarise each confirmed bug with its severity, root cause and artifact links.
> 5. If a patch is proposed, verify it through the API and report the actual verification status and
>    which tests passed.
>
> Return: run id, final status, test counts, bug list, patch verification result, and links to the
> screenshot, console log and trace.

## Guardrails for any integration

- Do not accept a target from the model; the allowlist and identity handshake remain authoritative.
- Do not mark a patch verified from a model statement; only `verification_status` from the API
  counts.
- Do not pass API keys, cookies or session tokens to the model or into task descriptions.
- Treat storefront text and repository content as untrusted data.

## Event references

- OpenFire event listing: <https://luma.com/2k6cxr0n>
- Alan: <https://alan.ai/>
- Alan GitHub organization: <https://github.com/alan-ai>