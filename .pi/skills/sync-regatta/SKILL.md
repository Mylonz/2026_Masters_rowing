---
name: sync-regatta
description: Sync 2026 Masters Nationals race schedule and trailer load plan from Google Sheets into local JSON files.
---

# Sync Regatta Data

Extracts and synchronizes the live data from the Google Spreadsheet into `race_schedule.json` and `regatta_load_plan.json`.

## Special Regatta Progression Rules

When interpreting the sheet data:
- **Event 34 (Saturday W Mst D 2X):**
  - Heat 1 at 11:55: Ange & Vivienne in Moa (BYWW Pinks).
  - Heat 2 at 12:00: Liz & Claire in Matiu (BYWW x 1; BWW x 1). (Row in CSV has blank event number).
  - Final at 12:30: In the sheet, boat/oar columns are left blank because qualification is pending. Include the 12:30 Final entry noting either/both crews may qualify (Moa: Ange & Vivienne / Matiu: Liz & Claire).
- **Event 125 (Sunday W Mst D 4X-):**
  - Heat 1 at 13:53 (Mahanga) and Heat 2 at 13:59 (Hawkins); Final at 14:29.
- **Event 86 (Sunday W MNw 2X):**
  - Heat at 10:14 / 10:20 (Matiu) and Final at 11:14 (Matiu).
- **Event 78 (Sunday W Mst C 4X-):**
  - Heat at 8:30 (Hawkins) and Final at 9:30 (Hawkins).

### Corrections for Known Spreadsheet Re-Rig Errors:
- **Makaro Sequence (Sunday):**
  - Event 73 (08:42/08:48, 2X): Re-rig note must be `"RE-RIG AS PAIR (2- SWEEP) FOR EVENT 90"` (spreadsheet mistakenly says race 93).
  - Event 90 (10:26, 2-): Re-rig note must be `"RE-RIG BACK TO DOUBLE (2X SCULL) FOR EVENT 101"` (spreadsheet mistakenly says after race 78 / for race 102).
  - Event 101 (11:43, 2X): `"Double Scull (2X) - Must have been re-rigged back to double following Event 90"`.
- **Hawkins Sequence (Saturday to Sunday):**
  - Event 38 (Saturday 12:15, 4X-): Re-rig note must be `"RE-RIG AS COXLESS 4 (SWEEP) FOR EVENT 65"`.
  - Event 65 (Saturday 15:10, 4-): Re-rig note must be `"OVERNIGHT RE-RIG: Re-rig back to Quad (4X- scull) for Sunday Event 78 (08:30)"` (spreadsheet mistakenly says after race 51).
  - Event 78 (Sunday 08:30, 4X-): `"Scull (4X-) - Re-rigged back to quad overnight following Event 65; Final at 09:30"`.



Run the sync script from the repository root:

```bash
python3 scripts/sync_sheets.py
```

After running, inspect the changes with `git diff --stat` and summarize the updates (e.g. newly added/modified races, boat assignments, re-rig alerts, or trailer changes) for the user.
