# Publishing to GitHub

The repository is prepared locally: initial commit on `main`, tag `v0.1.0`, issue templates, PR
template, CI workflow, security policy and changelog. Once the remote URL is known, publish with the
steps below.

## 1. Create the repository

With the GitHub CLI:

```powershell
gh auth login
gh repo create OWNER/bughunter-ai --public --source . --remote origin --push
```

Or create it in the browser, then:

```powershell
git remote add origin https://github.com/OWNER/bughunter-ai.git
git push -u origin main
git push origin v0.1.0
```

## 2. Topics

```powershell
gh repo edit OWNER/bughunter-ai --add-topic ai-testing,autonomous-agents,qa-automation,browser-testing,playwright,fastapi,react,typescript,sqlite,bug-reproduction,patch-verification,hackathon,openfire,software-testing,test-automation
```

## 3. Labels

```powershell
.\scripts\github-setup.ps1 -Repo OWNER/bughunter-ai
```

The script creates (or updates) every label listed in the README and adds the release notes link.

## 4. Release

```powershell
gh release create v0.1.0 --title "v0.1.0 - failure to verified fix" --notes-file CHANGELOG.md
```

Replace `OWNER` in `CHANGELOG.md` and `README.md` if you want working release links.

## 5. Repository settings worth turning on

| Setting | Why |
| --- | --- |
| Branch protection on `main` | Require the CI check before merge |
| Secret scanning / push protection | Blocks accidental key commits |
| Dependabot alerts | Python and npm dependencies |
| "Automatically delete head branches" | Keeps the branch list clean |
| Discussions (optional) | Q&A for the demo |

## 6. Verify CI

The workflow `.github/workflows/ci.yml` runs on every push and pull request:

- **Backend** — installs Python, Playwright Chromium, and runs the 9 contract tests, including the
  full reproduce → patch → verify loop.
- **Frontend** — `npm ci` and `npm run build` (type check included).

A red backend job means an invariant broke. Do not merge with a red job.

## 7. Local pre-push checklist

```powershell
python -m pytest backend/tests -q          # 9 passed
python -m pytest tests/e2e -q              # 11 passed, 1 expected failure
cd frontend; npm run build
cd ..
git status                                 # no data/, node_modules/ or dist/
```

Never commit `data/`, `.env`, or anything under `frontend/dist/`.
