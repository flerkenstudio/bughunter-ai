# Demo walkthrough (90 seconds)

## Before recording

```powershell
# reset to a known state
Remove-Item -Recurse -Force data -ErrorAction SilentlyContinue
uvicorn backend.app.main:app --port 8000
```

Wait for the dashboard at <http://127.0.0.1:8000/app/> to show `api ok`. The demo store starts on
the first run. Keep a previously verified run visible in History as fallback evidence.

## Script

| Time | Action | What the audience sees |
| --- | --- | --- |
| 0–10 s | Say: “The checkout flow is suspect. Test it, reproduce any bug, and prove a fix.” Select **Nimbus Supply (demo)**, scope `checkout`, click **Start investigation**. | Natural-language task, status moves to `planning` with the bounded plan |
| 10–25 s | Watch `running`. Open the demo store in a second tab while tests execute. | Real Chromium runs, attempt 1 records one pass (healthy path) and one failure |
| 25–40 s | Run moves to `reproducing`; open the bug card. | Second execution fails again — the bug is confirmed, not guessed. Point at severity, root cause, reproduction steps |
| 40–55 s | Scroll the evidence strip: screenshot, console log, Playwright trace. | A screenshot of the wrong total ($115.24) and hard evidence files, each with a sha256 |
| 55–70 s | Show the proposed diff: `total = subtotal + shipping + tax` → `taxable + shipping + tax`. Click **Verify in isolated checkout**. | A reviewable one-line diff; verification runs in a temp worktree |
| 70–85 s | Verification completes: `verified`; expand the verification output. | All four tests pass on the patched checkout; failing test plus regression suite |
| 85–90 s | Close: “Evidence, not explanations. It reproduced, it patched, it proved it.” | Verified badge, run history preserved |

## Exact numbers to quote

- Cart: Pulse Headphones $89.00 + Nimbus Bottle $18.50 = **$107.50**
- SAVE10: **-$10.75** → taxable **$96.75**
- Shipping free (above $75), tax 8% = **$7.74**
- Correct charge **$104.49**; the buggy build charges **$115.24**

## Optional: prove it works on a real site (20 seconds)

1. Click `+ add` under **Targets**, register `https://example.com`.
2. Select it — scope switches to `probe` and the demo-only chips are disabled.
3. Start the investigation. The generic pack runs eight checks.
4. The result is honest: seven pass, one fails (Example Domain has no meta description), the
   failure reproduces, and evidence is attached. No patch is proposed because the repository does
   not own that site.

## Fallback

If the live environment fails:

1. Open History and select the last verified run; every artifact is already on disk.
2. If the browser is the problem, show `data/artifacts/<run>/attempt-1/*.png` and
   `pytest-output.txt` directly.
3. If the API is down, run `python -m pytest backend/tests -q` and show the passing suite output —
   it exercises the same loop against real Chromium.

## What not to claim

- Do not say a fix is verified if the verification step did not run.
- Do not call a failure a bug before the reproduction attempt.
- Do not claim Alan cloud integration is verified; see `integrations/alan/README.md`.

## Reset between takes

```powershell
Remove-Item -Recurse -Force data -ErrorAction SilentlyContinue
Get-ChildItem data -ErrorAction SilentlyContinue
```

The seeded bug is in the committed source, so resetting runtime state cannot accidentally “fix” it.