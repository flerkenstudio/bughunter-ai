# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-27

First hackathon release: a complete, repeatable failure-to-verification loop.

### Added

- FastAPI backend with typed contracts: projects, runs, tests, bugs, artifacts, patches, memories.
- Run orchestrator with an enforced state machine, reproduction gate and honest terminal states
  (`failed`, `timed_out`, `inconclusive`, `runner_error`).
- Playwright browser runner driven by pytest, with JUnit parsing and per-test evidence
  (screenshot, console log, trace) hashed with sha256.
- Seeded Nimbus Supply demo store with one checkout defect and healthy paths.
- Rule-based analyst that proposes a patch derived from the file under test.
- Isolated patch verification in a system-temp git worktree with a copy fallback; only passing
  tests can mark a patch verified.
- React + TypeScript dashboard: targets, scope selection, live timeline, test outcomes, evidence
  viewer, patch diff and verification results.
- Generic site probe pack (8 checks) for any public URL, with private and metadata addresses blocked.
- Investigation history in SQLite that survives restarts, including per-test verification rows.
- Optional OpenAI-compatible analyst adapter with deterministic fallback.
- Docs: architecture, setup, security, 90-second demo walkthrough, Alan integration notes.
- GitHub scaffolding: issue templates, pull request template, CI workflow, label/topic setup.

### Known limitations

- No GitHub issue/PR creation, scheduling, parallel agents or Docker packaging.
- The generic probe is a smoke/quality pack, not a functional test suite for unknown sites.
- Patch proposal and verification apply only to the bundled demo checkout.

[0.1.0]: https://github.com/OWNER/bughunter-ai/releases/tag/v0.1.0
