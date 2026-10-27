# Security and reliability

BugHunter AI executes browser code against a target and applies patches to a checkout. Both
operations are constrained by design; this document states the controls and the residual risk
honestly.

## Controls

| Risk | Control | Where |
| --- | --- | --- |
| Testing arbitrary hosts | Loopback-only host allowlist; optional port allowlist; `http/https` only; embedded credentials rejected | `backend/app/security.py` |
| Testing an unrelated local service | Identity handshake: `/health` must return `X-Demo-Target: nimbus-supply` | `probe_target` |
| Unbounded execution | Curated test catalog, per-run timeout, hard cap, single orchestrated worker per request | `catalog.py`, `orchestrator.py` |
| Patch escaping the workspace | Path validation rejects absolute paths, `..`, backslashes, drive letters, `.env`, `.git`, `.pem`, `secrets`, and anything outside `demo-store/ backend/ tests/ frontend/ docs/` | `validate_patch` |
| Editing the real tree | Patches apply in a system-temp git worktree; the working tree is never touched | `PatchVerifier` |
| Leaking credentials to a model | The adapter sends test keys, names, statuses and truncated assertion text only; no headers, cookies, env or source | `ai/provider.py` |
| Prompt injection from the page | The model never acts; it may only describe observed failures, and its patch passes the same path validation and test verification | `ai/provider.py`, `validate_patch` |
| False evidence | Screenshots/console/traces are produced by the browser; artifact sha256 and tested revision are recorded | runner, artifacts |
| Fake fixes | Verification is a real test run; only `PatchVerifier` can set `verified` | `orchestrator.py` |
| Losing history | SQLite with WAL and foreign keys; artifacts on disk | `db.py` |

## Honest statuses

- A failure that does not repeat on the second execution → `inconclusive`, no bug.
- A target that is down or fails the identity handshake → `failed` with `error_kind=infrastructure`,
  no bug.
- A suite that exceeds the limit → `timed_out`; unfinished cases are `not_run`, never `passed`.
- A patch that fails the suite → `verification_status=failed`; a patch that cannot apply →
  `verification_status=error` with the tool output preserved.

## Residual risks

1. **No authentication, no rate limiting.** Anyone who can reach the API can start runs against any
   allowed target. Keep it on localhost or put an authenticated proxy in front of it.
2. **DNS rebinding window.** The policy resolves the host once before the run. A hostile DNS server
   could answer differently for the browser request, so do not point this at untrusted URLs from an
   untrusted network.
3. **Cookies and authenticated sessions.** The probe loads pages anonymously; it never injects
   credentials. Do not feed it URLs whose query string contains secrets.
4. **No process-level sandbox.** The browser and pytest run as the current user. The timeout and
   catalog bound work, but this is not a container or VM boundary. Docker packaging was left out to
   protect demo time.
5. **Model output quality.** A configured model can produce a wrong root cause. Severity is
   advisory and the report cites evidence; a wrong patch fails verification.
6. **Synchronous verification.** A verification request blocks for the duration of the suite. That
   is acceptable for a single-operator demo and would need a queue for multi-user use.
7. **Seeded-knowledge advantage.** The deterministic analyst knows the demo bug precisely. That is
   disclosed in the UI source (`rule-based`) and in the README, and other failures are not
   embellished.

## Reporting

If you find a way to make the system report a bug without a reproduced failure, or mark a patch
verified without passing tests, that is a security-relevant bug. Please open an issue with the run
ID and the evidence trail.