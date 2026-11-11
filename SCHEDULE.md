# Scheduled refresh (Windows Task Scheduler)

Tue/Fri **7:00 AM local time**: re-fetch FRED + market data, recompute charts, export PNGs to `exports/YYYY-MM-DD/` and `exports/latest/`.

## One-time setup

1. **Ensure refresh works manually**
   - Open PowerShell, go to project root: `cd "C:\Users\...\macro-dashboard"`.
   - Run: `python refresh.py` (or `.\scripts\refresh.ps1`).
   - Check that `exports\latest\` contains the nine PNGs.

2. **Create the scheduled task**

   - Press **Win + R**, type `taskschd.msc`, Enter.
   - **Task Scheduler Library** → right‑click → **Create Task** (not “Create Basic Task” so we can set weekly + multiple days).

   **General**
   - Name: `Macro Dashboard Refresh`
   - Description: `Tue/Fri 7 AM – fetch data, export charts to exports\latest and exports\YYYY-MM-DD`
   - “Run whether user is logged on or not” or “Run only when user is logged on” (your choice).
   - ✅ Run with highest privileges (optional; usually not needed).

   **Triggers**
   - **New** → “On a schedule” → **Weekly**.
   - Start: pick a date (e.g. today); time **7:00:00 AM**.
   - Recur every **1** week.
   - ✅ **Tuesday** and **Friday** (check both).
   - OK.

   **Actions**
   - **New** → Action: **Start a program**.
   - Program/script:
     ```text
     powershell.exe
     ```
   - Add arguments:
     ```text
     -NoProfile -ExecutionPolicy Bypass -File "C:\Users\<You>\OneDrive\Desktop\Projects\macro-dashboard\scripts\refresh.ps1"
     ```
     (Replace `<You>` with your Windows username, or use the full path to `macro-dashboard`.)

   - Start in (optional but recommended):
     ```text
     C:\Users\<You>\OneDrive\Desktop\Projects\macro-dashboard
     ```
   - OK.

   **Conditions**
   - Uncheck “Start the task only if the computer is on AC power” if you want it to run on battery.
   - “Wake the computer to run this task” is optional.

   **Settings**
   - Allow task to be run on demand: ✅ (so you can run it manually).
   - If the task fails, restart every: e.g. 5 minutes, 3 times (optional).

3. **Test**
   - In Task Scheduler, right‑click **Macro Dashboard Refresh** → **Run**.
   - Check `exports\latest\` and `exports\YYYY-MM-DD\` for new PNGs.

## Alternative: run the .bat

If you prefer a batch file as the task action:

- Program/script: `C:\Users\<You>\OneDrive\Desktop\Projects\macro-dashboard\scripts\run_refresh.bat`
- Add arguments: (leave empty)
- Start in: `C:\Users\<You>\OneDrive\Desktop\Projects\macro-dashboard`

## Output locations

| Path | Contents |
|------|----------|
| `exports\latest\` | Latest run: `01_global_liquidity.png` through `09_net_liquidity.png` (see `EXPORT_NAMES` in `refresh.py`) |
| `exports\YYYY-MM-DD\` | Same nine files, dated for that run (e.g. `2026-02-28`) |

## Changing the schedule

Edit the task in Task Scheduler → **Triggers** → change days or time. To use a different lookback for the refresh, edit `refresh.py` and change the default in `run_refresh(lookback="5y")`, or pass it when running manually: `python refresh.py 10y`.

# Emailed Macro Brief (GitHub Actions, Mon/Wed/Fri)

`.github/workflows/brief.yml` runs `send_brief.py` at 5 AM Eastern (year round, DST handled) every Mon/Wed/Fri,
in the cloud, so your PC doesn't need to be on. The email body holds the whole brief as text (snapshot,
what changed since the previous brief, AI interpretation, headlines); the PDF with charts is attached.
Subject: `[Macro Brief] YYYY-MM-DD - Macro Risk NN/100 (Zone)`.

## One-time setup

1. **Gmail App Password**: Google Account → Security → 2-Step Verification (must be on) → App passwords →
   create one named "Macro Brief". Copy the 16-character password.
2. **Repo secrets**: GitHub repo → Settings → Secrets and variables → Actions → New repository secret:
   - `FRED_API_KEY`
   - `CLAUDE_API_KEY` (optional; without it the email has no AI section)
   - `SMTP_USER`: the Gmail address that sends
   - `SMTP_PASSWORD`: the App Password from step 1
   - `BRIEF_TO`: where the brief goes
3. **Test**: Actions tab → macro-brief → Run workflow. Tick "dry run" to build without sending and download
   the `.eml` from the run's artifacts, or leave it unticked to send a real email now.

Locally: `python send_brief.py --dry-run` writes `exports/brief/<date>.eml` and `.html` (needs the same
variables in `.env`; SMTP ones only when actually sending).

To change the time or days, edit both `cron` lines in `brief.yml` (UTC; one for EDT, one for EST) and the matching strings in its gate step. Note: GitHub disables scheduled
workflows in repos with no activity for 60 days; re-enable from the Actions tab if that happens.
