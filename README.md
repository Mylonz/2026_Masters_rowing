# 2026 Masters Nationals — Regatta Logistics & Operations Portal

A mobile-first, print-friendly regatta operations dashboard for the **Wellington Rowing Club (WRC)** at the **2026 Masters Nationals**. 

The portal provides coaches, rowers, coxswains, trailer drivers, and boat loaders with instant access to the chronological race timeline, interactive rower schedule filtering, dynamic trailer rack layouts, and shed gear checklists.

---

## 🌐 Site Structure & Features

| File | Purpose | Key Features |
| :--- | :--- | :--- |
| **`index.html`** | Portal Hub & Regatta Summary | Quick statistics (entered races, boats traveling, oar sets, re-rigs), direct navigation tiles, and official Google Sheet link. |
| **`race_schedule.html`** | Chronological Race Schedule | Live rower/cox name search filter with autocomplete, day filtering (Saturday/Sunday), critical re-rig alerts filter, and segmented oar stripe tape badges. |
| **`regatta_load_plan.html`** | Logistics & Trailer Load Plan | Interactive 4-tier trailer layout (responsive 2×2 mobile view), fleet specs, oar allocation tables, and persistent shed packing checklists. |
| **`WRC_Loadmaster_responsibilities.html`** | Loadmaster Guide | Standard operating procedures for boat loading, tying, weight distribution, safety flags, and tow vehicle checks. |

---

## 📊 Data Architecture & Spreadsheet Dependency

The website architecture is completely decoupled from hardcoded data. Webpages dynamically fetch data asynchronously from standalone JSON files:

```
Google Spreadsheet (Source of Truth)
   ├── Tab 'v2' (Schedule & Crews) ───────► race_schedule.json ───► race_schedule.html
   ├── Tab 'Load Plan' (Trailer & Fleet) ──► regatta_load_plan.json ─► regatta_load_plan.html
   └── Optional Tab 'Additional Gear' ────► additional_gear.json ──► regatta_load_plan.html
```

*Note: If an `Additional Gear` tab has not yet been added to Google Sheets, `additional_gear.json` maintains its local configuration without being overwritten.*

### Official Google Spreadsheet
* **Link:** [WRC 2026 Nats Spreadsheet (Official Source of Truth)](https://docs.google.com/spreadsheets/d/1Vt7A1fwQDqtUF1455LZgacA4fy5tr2AUYojgEgrrlEM/edit?gid=1295452530#gid=1295452530)
* **Tab `v2` (`gid=1295452530`):** Contains Saturday and Sunday race blocks, times, events, categories, coxswains, crew rosters, assigned boats, and oar sets.
* **Tab `Load Plan` (`gid=1504778411`):** Contains the 4-tier trailer grid (`I2:L5`), return-trip quad slot, sweep/scull allocations, and Town/Waimarino shed gear inventories.

---

## 🔄 Synchronizing Data from Google Sheets

An automated synchronization engine (`scripts/sync_sheets.py`) pulls the live Google Sheets CSV exports and processes them using Gemini Flash via your Pi agent configuration.

### How to Run the Sync

Choose any of the following methods:

#### Method 1: Inside Pi Agent (Conversational or Skill)
Whenever you are running Pi in this repository, simply type:
```text
/skill:sync-regatta
```
or ask:
> *"Sync the regatta sheets"*

#### Method 2: From the Terminal (One-Liner)
Run the convenience wrapper script from your terminal:
```bash
# Preview changes without modifying files:
./sync-sheets.sh --check        # Fast check if spreadsheet changed
./sync-sheets.sh --dry-run      # Full extraction and diff preview (no file changes)

# Interactive review (preview diff and prompt to apply):
./sync-sheets.sh --interactive  # Shows diff and asks before updating files

# Direct sync:
./sync-sheets.sh                # Syncs and updates JSON files directly
```

#### Method 3: Non-Interactive Pi CLI
```bash
pi -p "sync the regatta sheets"
```

---

## 🧠 Automated Logic & Algorithmic Features

The sync script incorporates specialized logic to handle real-world regatta conditions:

### 1. Deterministic Re-Rig Lifecycle Algorithm
Rather than relying on human notes in the spreadsheet (which are often prone to typos and outdated race numbers), the sync engine tracks the chronological lifecycle of each shell (`Hawkins`, `Makaro`, etc.):
* **Discipline Detection:** Evaluates whether each race requires **Sculling** (`1X`, `2X`, `4X-`, `4X+`) or **Sweep** (`2-`, `4-`, `8+`).
* **Consecutive Transition Detection:** Whenever a boat's configuration changes between race $i$ and race $i+1$, it automatically flags the departing race with `rerig_required: true`.
* **Automatic Targeting:** Generates precise alert text with target event number, day, time, and turnaround window (including overnight re-rig flags):
  * **Hawkins:** Re-rig from `4X-` to `4-` after Event 38 (12:05) for Event 65 (15:10), then an **overnight re-rig** back to `4X-` for Sunday Event 78 (09:06).
  * **Makaro:** Re-rig from `2X` to `2-` after Event 73 (08:42) for Event 90 (10:28), then re-rig back to `2X` for Event 101 (11:44).

### 2. Multi-Heat Progression & Finals Handling
For events where progression is conditional on heat results (such as **Event 34** and **Event 125**), the sync engine:
* Populates both heats with their distinct crews, boats, and oar sets.
* Automatically creates dedicated **Final** race entries noting that either or both qualifying crews will contest the final.

### 3. Coxswain Detection & Badging
* Explicitly extracts coxswains from the spreadsheet's `Cox` column (e.g. `Isaac`, `Millzy`).
* Formats crew lists and highlights coxswains with an accessible, authoritative nautical teal badge (`<span class="cox-tag">COX</span>`).
* Integrates seamlessly with the search filter so searching a coxswain's name displays all races they are steering.

### 4. Segmented Oar Stripe Ribbons
Oar codes (`BGW`, `BYWW`, `BBlkW`, `BWW`, `BGY`) are rendered as tape stripe badges mimicking physical oar looms:
* **B** = Blue (`#1d4ed8`)
* **G** = Green (`#15803d`)
* **Y** = Yellow (`#facc15`)
* **W** = White (`#ffffff` with slate borders and high-contrast dark text)
* **Blk** = Black (`#0f172a`)

---

## 💻 Local Development & Testing

Modern browsers enforce CORS policies that prevent `fetch()` requests from reading local files via the `file://` protocol. To run and preview the site locally:

1. **Start a local HTTP server:**
   ```bash
   python3 -m http.server 8000
   ```
2. **Open in browser:**
   ```text
   http://localhost:8000
   ```

---

## 🚀 Deployment (GitHub Pages)

The repository is hosted and automatically deployed via **GitHub Pages**.

To publish changes:
```bash
git add .
git commit -m "Update regatta schedule and load plan"
git push origin main
```
GitHub Pages will automatically serve the updated static files and JSON data.
