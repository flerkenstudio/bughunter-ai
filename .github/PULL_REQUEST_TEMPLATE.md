## What changed

<!-- One paragraph. Link the issue if there is one. -->

## Why

<!-- What could a user not do before? -->

## Evidence

<!-- Test output, screenshots, or the run ID that proves it. -->

## Invariants

- [ ] A bug still requires a reproduced failure (two failing executions)
- [ ] A patch is still verified only by tests, never by a model statement
- [ ] A test that did not run is still counted as `not_run`, never `passed`
- [ ] No secrets, cookies or API keys are logged or sent to a model
- [ ] Target policy and patch path validation still hold

## Checks

- [ ] `python -m pytest backend/tests -q`
- [ ] `python -m pytest tests/e2e -q` (1 expected failure: the seeded bug)
- [ ] `cd frontend && npm run build`