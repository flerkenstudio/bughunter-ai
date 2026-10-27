# Setup

## Requirements

- Python 3.11+ (3.12 tested)
- Node.js 18+ (20/24 tested) for the dashboard
- Git (verification uses worktrees; a fallback copy exists)
- Chromium installed through Playwright

## Install

```powershell
git clone <repository-url> bughunter-ai
cd bughunter-ai

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
python -m playwright install chromium

cd frontend
npm install
npm run build
cd ..
```

macOS/Linux: `python3 -m venv .venv`, `source .venv/bin/activate`, same pip/npm steps.

## Run

```powershell
uvicorn backend.app.main:app --port 8000
```

- Dashboard: <http://127.0.0.1:8000/app/>
- API docs: <http://127.0.0.1:8000/docs>
- Demo store: started on demand at <http://127.0.0.1:8090>

To work on the dashboard with hot reload, run the API and Vite separately:

```powershell
uvicorn backend.app.main:app --port 8000 --reload
cd frontend; npm run dev     # http://localhost:5173, proxies /api
```

## Verify the install

```powershell
python -m pytest backend/tests -q
```

This runs the full loop: start a run, detect and reproduce the seeded checkout bug, capture
evidence, then patch an isolated checkout and verify it. Expect roughly 60–90 seconds because two
real browser passes plus a third verification pass execute.

```powershell
python -m pytest tests/e2e -q
```

Expect **1 failed, 3 passed**. The failure is the seeded bug and is intentional.

## Configuration

Copy `.env.example` to `.env` if you want to change defaults; the app reads environment variables
only, so export them in your shell (or use your process manager).

| Variable | Default | Notes |
| --- | --- | --- |
| `BUGHUNTER_DB` | `data/bughunter.db` | SQLite file; survives restarts |
| `BUGHUNTER_ARTIFACT_DIR` | `data/artifacts` | Screenshots, traces, logs |
| `BUGHUNTER_DEMO_PORT` | `8090` | Demo store port; used as the seeded project URL |
| `BUGHUNTER_ALLOWED_PORTS` | empty | Comma-separated allowlist; empty allows any loopback port |
| `BUGHUNTER_ALLOW_EXTERNAL_TARGETS` | `1` | Accept public http/https target URLs |
| `BUGHUNTER_ALLOWED_HOSTS` | empty | Optional host allowlist; empty allows any public host |
| `BUGHUNTER_ALLOW_PRIVATE_TARGETS` | `0` | Allow private/loopback/link-local targets (dangerous) |
| `BUGHUNTER_REQUIRE_DEMO_TARGET` | `1` | Require the `X-Demo-Target: nimbus-supply` header |
| `BUGHUNTER_RUN_TIMEOUT` | `120` | Default max seconds per browser attempt |
| `BUGHUNTER_MAX_RUN_TIMEOUT` | `600` | Hard cap for a requested timeout |
| `BUGHUNTER_AI_BASE_URL` | empty | OpenAI-compatible endpoint, e.g. `http://127.0.0.1:11434/v1` |
| `BUGHUNTER_AI_API_KEY` | empty | Bearer token; never logged |
| `BUGHUNTER_AI_MODEL` | empty | Model identifier |

## Troubleshooting

- **"target did not present the approved demo-store identity marker"** — something else is
  listening on 8090. Stop it or set `BUGHUNTER_DEMO_PORT` to a free port and restart the API so the
  seeded project URL follows it.
- **Playwright browser missing** — run `python -m playwright install chromium`.
- **`git apply` fails during verification** — make sure the repo has at least one commit. The
  verifier falls back to copying the tree, but a committed HEAD is the tested revision and is
  recorded on the patch.
- **Port 8000 busy** — pass `--port 8010`; the dashboard is same-origin, so no other change is
  needed.
- **Stale runs after a crash** — delete `data/bughunter.db` (and `data/artifacts`) to start clean.