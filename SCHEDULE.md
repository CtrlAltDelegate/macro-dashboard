# Scheduled refresh (Windows Task Scheduler)

Tue/Fri **7:00 AM local time**: re-fetch FRED + market data, recompute charts, export PNGs to `exports/YYYY-MM-DD/` and `exports/latest/`.

## One-time setup

1. **Ensure refresh works manually**
   - Open PowerShell, go to project root: `cd "C:\Users\...\RiskCycle"`.
   - Run: `python refresh.py` (or `.\scripts\refresh.ps1`).
   - Check that `exports\latest\` contains the four PNGs.

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
     -NoProfile -ExecutionPolicy Bypass -File "C:\Users\<You>\OneDrive\Desktop\Projects\RiskCycle\scripts\refresh.ps1"
     ```
     (Replace `<You>` with your Windows username, or use the full path to `RiskCycle`.)

   - Start in (optional but recommended):
     ```text
     C:\Users\<You>\OneDrive\Desktop\Projects\RiskCycle
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

- Program/script: `C:\Users\<You>\OneDrive\Desktop\Projects\RiskCycle\scripts\run_refresh.bat`
- Add arguments: (leave empty)
- Start in: `C:\Users\<You>\OneDrive\Desktop\Projects\RiskCycle`

## Output locations

| Path | Contents |
|------|----------|
| `exports\latest\` | Latest run: `01_valuation_pressure_index.png`, `02_macro_risk_raw_roc.png`, `03_risk_thermostat.png`, `04_risk_cascade_rotation.png` |
| `exports\YYYY-MM-DD\` | Same four files, dated for that run (e.g. `2026-02-28`) |

## Changing the schedule

Edit the task in Task Scheduler → **Triggers** → change days or time. To use a different lookback for the refresh, edit `refresh.py` and change the default in `run_refresh(lookback="5y")`, or pass it when running manually: `python refresh.py 10y`.
