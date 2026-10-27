# Security policy

## Reporting a vulnerability

Do not open a public issue for a security problem. Report it privately to the maintainers (repository
owners) with:

- the affected version or commit,
- a minimal reproduction,
- the impact you believe it has.

The most serious class of bug here is **evidence integrity**: anything that makes the system report
a bug without a reproduced failure, or mark a patch verified without passing tests. Treat that as a
security issue, not a regular bug.

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |

## Scope of the threat model

The application runs locally and has no authentication. The controls that matter:

- **Target policy** — public http/https URLs only; private, loopback (except the bundled demo),
  link-local, reserved and cloud-metadata addresses rejected after DNS resolution.
- **Execution bounds** — curated test pack, per-run timeout, hard cap.
- **Patch isolation** — a disposable system-temp checkout; path validation rejects traversal, hidden
  config, keys and files outside the allowed roots.
- **Secret handling** — the AI adapter receives test names and assertion text only.
- **Honest status** — infrastructure errors and non-reproduced failures never become bugs.

## Known residual risks

- No authentication and no rate limiting: do not expose the API beyond localhost.
- DNS rebinding between validation and navigation is theoretically possible; do not submit untrusted
  URLs from an untrusted network.
- The browser runs as the current user; there is no process-level sandbox (no Docker image yet).
- A configured language model can produce a wrong explanation; verification is still performed by
  tests, and severity is advisory.

See [`docs/security.md`](docs/security.md) for the full control table.
