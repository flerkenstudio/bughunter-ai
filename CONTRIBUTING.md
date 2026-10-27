# Contributing

BugHunter AI is a hackathon project, but the invariants are not negotiable:

- Never report a bug from a single failed execution. Reproduce it first.
- Never mark a patch verified from a model statement. Run the tests.
- Never treat an infrastructure error or a test that did not run as a pass.
- Keep target access loopback-only unless a reviewed allowlist is added.
- Do not send secrets, cookies or credentials to a model or into logs.

## Local checks

```powershell
python -m pytest backend/tests -q
python -m pytest tests/e2e -q   # one intentional failure: the seeded bug
cd frontend; npm run build
```

Add a test with any behavioural change. The backend suite must keep passing against the broken
demo store, because the broken store is the fixture.