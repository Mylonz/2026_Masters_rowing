#!/usr/bin/env python3
"""
Sync regatta data from Google Sheets into race_schedule.json and regatta_load_plan.json.
Supports --dry-run / --check / -n to preview changes before applying them,
and --interactive / -i to prompt for confirmation before updating.
"""

import os
import sys
import json
import re
import hashlib
import urllib.request
import urllib.error

SPREADSHEET_ID = "1Vt7A1fwQDqtUF1455LZgacA4fy5tr2AUYojgEgrrlEM"
GID_SCHEDULE = "1295452530"   # 'v2' tab
GID_LOAD_PLAN = "1504778411"  # 'Load Plan' tab

def get_api_key():
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key

    auth_file = os.path.expanduser("~/.pi/agent/auth.json")
    if os.path.exists(auth_file):
        try:
            with open(auth_file, "r", encoding="utf-8") as f:
                auth = json.load(f)
                key = auth.get("google", {}).get("key")
                if key:
                    return key
        except Exception:
            pass

    return None

def fetch_sheet_csv(gid):
    url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={gid}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8")

def call_gemini(api_key, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.0
        }
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        text = res["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)

def get_boat_config(event_class="", event_name="", oars=""):
    text = f"{event_class} {event_name} {oars}".lower()
    if "4x" in text: return "Quad (4X- Scull)"
    if "2x" in text: return "Double (2X Scull)"
    if "1x" in text: return "Single (1X Scull)"
    if "8+" in text or "eight" in text: return "Eight (8+ Sweep)"
    if "4-" in text or "4+" in text or "four" in text: return "Four (4- Sweep)"
    if "2-" in text or "2+" in text or "pair" in text: return "Pair (2- Sweep)"
    return None

def compute_rerigs(races):
    """
    Deterministically computes all boat re-rigging requirements by tracking
    the chronological lifecycle of each shell, completely ignoring human typos
    in spreadsheet comments.
    """
    for r in races:
        r["rerig_required"] = False
        r["rerig_note"] = None

    boat_timeline = {}
    for i, race in enumerate(races):
        boat_str = race.get("boat", "")
        if not boat_str or boat_str.upper() in ["TBC", "(EMPTY)"]:
            continue

        boats = [b.strip() for b in re.split(r"&|/|\band\b", boat_str) if b.strip()]
        for b in boats:
            clean_b = re.sub(r"\s*\(.*?\)", "", b).strip()
            if "tarakaena" in clean_b.lower():
                clean_b = "Tarakena"
            if clean_b not in boat_timeline:
                boat_timeline[clean_b] = []
            
            cfg = get_boat_config(
                race.get("event_class", ""),
                race.get("event_name", ""),
                race.get("oars_assigned", "")
            )
            boat_timeline[clean_b].append({
                "race_index": i,
                "race": race,
                "config": cfg
            })

    rerig_count = 0
    for boat, timeline in boat_timeline.items():
        for k in range(len(timeline) - 1):
            curr = timeline[k]
            nxt = timeline[k + 1]
            if curr["config"] and nxt["config"] and curr["config"] != nxt["config"]:
                curr_race = curr["race"]
                nxt_race = nxt["race"]

                is_overnight = curr_race.get("day") != nxt_race.get("day")
                nxt_day_str = f"{nxt_race.get('day')} " if is_overnight else ""
                
                if is_overnight:
                    note = f"OVERNIGHT RE-RIG: Re-rig {boat} from {curr['config']} to {nxt['config']} for {nxt_day_str}Event {nxt_race.get('event_number')} ({nxt_race.get('time')})"
                else:
                    note = f"RE-RIG: Re-rig {boat} from {curr['config']} to {nxt['config']} for Event {nxt_race.get('event_number')} ({nxt_race.get('time')})"

                curr_race["rerig_required"] = True
                curr_race["rerig_note"] = note
                rerig_count += 1

    return rerig_count

def diff_schedule(old_data, new_data):
    def race_key(r):
        return (r.get("day"), r.get("event_number"), r.get("boat") or r.get("time"))

    old_races = {race_key(r): r for r in old_data.get("races", [])}
    new_races = {race_key(r): r for r in new_data.get("races", [])}

    diffs = []
    for k, nr in new_races.items():
        if k not in old_races:
            diffs.append(f"➕ [NEW RACE] Event {nr.get('event_number')} ({nr.get('day')} {nr.get('time')}): {nr.get('event_class')} in {nr.get('boat')}")
        else:
            orace = old_races[k]
            f_diffs = []
            for f in ["time", "crew", "oars_assigned", "rerig_required", "rerig_note", "notes"]:
                if orace.get(f) != nr.get(f):
                    f_diffs.append(f"{f}: '{orace.get(f)}' -> '{nr.get(f)}'")
            if f_diffs:
                diffs.append(f"✏️  [MODIFIED] Event {nr.get('event_number')} ({nr.get('day')} {nr.get('boat')}): " + "; ".join(f_diffs))

    for k, orace in old_races.items():
        if k not in new_races:
            diffs.append(f"❌ [REMOVED RACE] Event {orace.get('event_number')} ({orace.get('day')} {orace.get('time')}): {orace.get('boat')}")

    return diffs

def diff_load_plan(old_data, new_data):
    diffs = []
    old_cfg = old_data.get("trailer_load_configuration", {})
    new_cfg = new_data.get("trailer_load_configuration", {})
    old_tiers = old_cfg.get("tiers", []) if isinstance(old_cfg, dict) else old_cfg
    new_tiers = new_cfg.get("tiers", []) if isinstance(new_cfg, dict) else new_cfg

    for idx in range(min(len(old_tiers), len(new_tiers))):
        ot = old_tiers[idx]
        nt = new_tiers[idx]
        tlabel = ot.get("tier_label") or ot.get("tier") or f"Tier {4 - idx}"
        obays = ot.get("bays", [])
        nbays = nt.get("bays", [])
        for b_idx in range(min(len(obays), len(nbays))):
            ob = obays[b_idx]
            nb = nbays[b_idx]
            ob_name = ob.get("boat_name") if isinstance(ob, dict) else str(ob)
            nb_name = nb.get("boat_name") if isinstance(nb, dict) else str(nb)
            if ob_name != nb_name:
                diffs.append(f"🚛 [{tlabel} Bay {b_idx + 1}] '{ob_name}' -> '{nb_name}'")
    return diffs

def sync_schedule(api_key, root_dir, dry_run=False):
    print("📥 Downloading Schedule CSV from Google Sheets (tab: v2)...")
    csv_data = fetch_sheet_csv(GID_SCHEDULE)
    csv_hash = hashlib.sha256(csv_data.encode("utf-8")).hexdigest()

    sched_path = os.path.join(root_dir, "race_schedule.json")
    current_data = {}
    if os.path.exists(sched_path):
        with open(sched_path, "r", encoding="utf-8") as f:
            current_data = json.load(f)

    print("🤖 Processing Schedule with Gemini Flash...")
    prompt = f"""You are an expert rowing regatta data extraction engine.
Extract the schedule and rowers from the following Google Sheet CSV into the exact JSON schema provided.

Reference schema and current structure:
{json.dumps(current_data, indent=2)[:1200]}

Rules:
1. Preserve metadata with regatta, venue, dates, total_races_entered, total_club_boats, total_guest_boats, total_oar_sets.
2. Maintain 'rowers' array of unique participant names.
3. In 'races' array, every entry must have:
   - day: 'Saturday' or 'Sunday'
   - block: integer
   - time: string (e.g. '8:30')
   - hands_on_time: string (e.g. '8:00', always exactly 30 minutes prior to race start time)
   - event_number: integer
   - event_class: string (e.g. 'W Mst C 2X (Final)')
   - boat: string
   - oars_assigned: string (e.g. 'BYWW (Pinks)', 'BGW (Yellow)')
   - cox: string or null (e.g. 'Isaac', 'Millzy', or null if uncoxed)
   - crew: string (e.g. 'Ellie, Jacinda' or 'COX: Isaac, JoY, Deb, Paula, Jolanda')
   - notes: string
   - rerig_required: boolean
   - rerig_note: string or null
   - lane: integer or null (e.g. 2, 4, or null if unassigned)
   - race_letter: string or null (e.g. 'A', 'U', or null if unassigned)
   - race_code: string or null (e.g. 'A2', 'U7', or null if unassigned)
4. COXSWAIN HANDLING:
   - The CSV column 'Cox' specifies the coxswain (e.g., Isaac, Millzy).
   - In 'crew', for any coxed race (like 4X+ or 8+ in events 19, 29, 53, 111), always prefix the crew string with 'COX: <Name>, ' (e.g. 'COX: Isaac, JoY, Deb, Paula, Jolanda').
   - Also set the 'cox' field to the coxswain's name (e.g. "Isaac" or "Millzy").
5. Preserve existing re-rig warnings and notes where applicable.
6. If the 'Oars' column is blank or empty in the CSV, set 'oars_assigned' to 'TBC' unless explicitly specified in the special rules below. Do not assume or invent oar allocations (e.g., do not invent 'Avon RC oars').
7. STABILITY: Do NOT rephrase or cosmetically edit 'notes', 'event_class', or other fields for races already present in the reference JSON unless there is a genuine, material change in the CSV source data. Keep existing phrasing intact.
8. If a race has entered crew members but the boat column is blank, set boat to 'TBC'. Do not omit the race.
9. Note: Event 5 (M Mst F 2X) has been scratched/withdrawn and should NOT be included.

SPECIAL REGATTA HEATS & PROGRESSIONS HANDLING:
- Event 28 (Saturday Mx D-F 4X-):
  * Division 2 at 10:55 (Hawkins).

- Event 34 (Saturday W Mst D 2X):
  * Heat 1 (11:40): Ange, Vivienne in Moa (oars: BYWW (Pinks)).
  * Heat 2 (11:45): Liz, Claire in Matiu (oars: BYWW x 1; BWW x 1) (note: row in CSV has blank event number, but it is Event 34 Heat 2).
  * Final (12:30): In the sheet, boat/oar columns are left blank because either or both crews may qualify. You MUST include a distinct entry for the 12:30 Final:
    - day: "Saturday", block: 3, time: "12:30", event_number: 34, event_class: "W Mst D 2X (Final)"
    - boat: "Moa & Matiu"
    - oars_assigned: "Moa: BYWW (Pinks)\\nMatiu: BYWW x 1, BWW x 1"
    - crew: "Moa: Ange, Vivienne\\nMatiu: Liz, Claire"
    - notes: "Final: Either or both crews race subject to qualification from 11:40/11:45 heats"
    - rerig_required: false, rerig_note: null

- Event 38 (Saturday Mx A-C 4X-):
  * Division 2 at 12:10 (Hawkins).

- Event 125 (Sunday W Mst D 4X-):
  * Heat 1 (13:10): Mahanga, oars BWW x 4; BYWW x 4 (Ange, Jolanda, Jacinda, Paula).
  * Heat 2 (13:15): Hawkins, oars BWW x 4; BYWW x 4 (Liz, Deb, Deidre, Claire).
  * Final (13:45): In the sheet, boat/oar columns are left blank because either or both crews may qualify. Include the Final at 13:45:
    - day: "Sunday", block: 10, time: "13:45", event_number: 125, event_class: "W Mst D 4X- (Final)"
    - boat: "Mahanga & Hawkins"
    - oars_assigned: "Mahanga: BWW x 4, BYWW x 4\\nHawkins: BWW x 4, BYWW x 4"
    - crew: "Mahanga: Ange, Jolanda, Jacinda, Paula\\nHawkins: Liz, Deb, Deidre, Claire"
    - notes: "Final: Either or both crews race subject to qualification from 13:10/13:15 heats"
    - rerig_required: false, rerig_note: null

- Event 86 (Sunday W MNw 2X):
  * Include Heat at 09:35 / 09:40 (Matiu) and Final at 10:25 (Matiu).

- Event 78 (Sunday W Mst C 4X-):
  * Straight Final at 08:30 (Hawkins). No heats.

Input CSV Data:
{csv_data}
"""

    result = call_gemini(api_key, prompt)

    # Reconcile with current_data to eliminate cosmetic LLM paraphrasing
    current_by_key = {
        (r.get("day"), r.get("event_number"), r.get("boat") or r.get("time")): r
        for r in current_data.get("races", [])
    }
    for r in result.get("races", []):
        k = (r.get("day"), r.get("event_number"), r.get("boat") or r.get("time"))
        if k in current_by_key:
            old = current_by_key[k]
            # If crew, boat, and time are unchanged, preserve canonical notes and event_class
            if old.get("crew") == r.get("crew") and old.get("time") == r.get("time"):
                r["notes"] = old.get("notes")
                r["event_class"] = old.get("event_class")
                if "lane" in old and "lane" not in r:
                    r["lane"] = old.get("lane")
                if "race_letter" in old and "race_letter" not in r:
                    r["race_letter"] = old.get("race_letter")
                if "race_code" in old and "race_code" not in r:
                    r["race_code"] = old.get("race_code")

    rerigs = compute_rerigs(result.get("races", []))
    if "metadata" in result:
        result["metadata"]["total_rerigs"] = rerigs

    # Ensure hands_on_time is always computed deterministically (30m prior)
    for r in result.get("races", []):
        if r.get("time") and not r.get("hands_on_time"):
            try:
                parts = str(r["time"]).split(":")
                mins = int(parts[0]) * 60 + int(parts[1]) - 30
                r["hands_on_time"] = f"{mins // 60}:{mins % 60:02d}"
            except Exception:
                pass

    diffs = diff_schedule(current_data, result)

    if not dry_run:
        with open(sched_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

    return diffs, len(result.get("races", [])), len(result.get("rowers", [])), csv_hash

def sync_load_plan(api_key, root_dir, dry_run=False):
    print("📥 Downloading Load Plan CSV from Google Sheets (tab: Load Plan)...")
    csv_data = fetch_sheet_csv(GID_LOAD_PLAN)
    csv_hash = hashlib.sha256(csv_data.encode("utf-8")).hexdigest()

    plan_path = os.path.join(root_dir, "regatta_load_plan.json")
    current_data = {}
    if os.path.exists(plan_path):
        with open(plan_path, "r", encoding="utf-8") as f:
            current_data = json.load(f)

    print("🤖 Processing Load Plan with Gemini Flash...")
    prompt = f"""You are an expert rowing regatta data extraction engine.
Extract the trailer load plan, oar loading allocations, fleet specifications, and shed checklists from the following Google Sheet CSV into the exact schema of regatta_load_plan.json.

Reference target schema:
{json.dumps(current_data, indent=2)}

Rules:
1. Output MUST be valid JSON matching the exact structure above.
2. trailer_load_configuration must be an OBJECT with 'tiers' array (4 tiers), 'oar_racks' object, and 'loading_notes' array.
3. Each tier must contain 'bays' array of 4 bay objects (bay_number 1 to 4, side, position, boat_name, details, slot_type).
4. fleet_specifications must be array of boat objects (boat_name, seats, riggers_required, rigger_tape, notes, requires_re_rig). Preserve rigger_tape colors (flange, centre, gate) for each boat.
5. oar_loading_plan must contain 'sweep_oars' and 'sculling_oars' with total_summary and allocations array (oar_set, quantity, assignments).
6. pre_regatta_maintenance_checklists must contain 'waimarino_shed' and 'town_shed' arrays of objects with id, item, tasks, and rigger_tape where applicable. Ensure each set of riggers has its own check item with its tape ID colors.
7. safety_and_spares must contain 'safety_mandates' and 'spares_box_checklist'.
8. Use Island Bay for the 2- (not Whanganui).
9. Island Bay takes Both (Sweep & Scull) riggers (pack scull riggers as backup spares for other doubles). Ensure town_shed checklist includes scull riggers for Island Bay.

Input CSV Data:
{csv_data}
"""

    result = call_gemini(api_key, prompt)

    # Reconcile fleet specifications to preserve rigger_tape if missing from LLM response
    current_fleet_map = {b.get("boat_name"): b for b in current_data.get("fleet_specifications", [])}
    for b in result.get("fleet_specifications", []):
        old_b = current_fleet_map.get(b.get("boat_name"))
        if old_b and "rigger_tape" in old_b and "rigger_tape" not in b:
            b["rigger_tape"] = old_b["rigger_tape"]

    diffs = diff_load_plan(current_data, result)

    if not dry_run:
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

    tier_count = len(result.get("trailer_load_configuration", {}).get("tiers", [])) if isinstance(result.get("trailer_load_configuration"), dict) else len(result.get("trailer_load_configuration", []))
    boat_count = len(result.get("fleet_specifications", []))
    return diffs, tier_count, boat_count, csv_hash

def sync_additional_gear(api_key, root_dir, dry_run=False):
    gear_path = os.path.join(root_dir, "additional_gear.json")

    try:
        url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req).read().decode("utf-8", errors="ignore")

        gear_gid = None
        for candidate in ["Additional Gear", "Regatta Gear", "Gear", "Equipment"]:
            idx = html.find(f"0,0,\\\"{candidate}\\\"")
            if idx != -1:
                chunk = html[max(0, idx - 100):idx]
                m = re.findall(r"\\\"(\d{8,12})\\\"", chunk)
                if m:
                    gear_gid = m[-1]
                    print(f"📋 Found '{candidate}' tab in spreadsheet (gid: {gear_gid})")
                    break

        if not gear_gid:
            print("ℹ️  No 'Additional Gear' tab in spreadsheet yet; preserving local additional_gear.json.")
            return [], 0

        print("📥 Downloading Additional Gear CSV from Google Sheets...")
        csv_data = fetch_sheet_csv(gear_gid)

        prompt = f"""You are an expert equipment inventory extraction engine.
Extract all additional regatta equipment and team camp gear from the following CSV into a JSON array of objects.

Target Schema:
[
  {{
    "id": "gear-1",
    "item": "Rowing Ergs",
    "quantity": "2",
    "category": "Warm-up / Training",
    "notes": "Concept2 ergs; verify monitor batteries and check slide rails",
    "assigned_to": null
  }}
]

CSV Data:
{csv_data}
"""
        result = call_gemini(api_key, prompt)
        if isinstance(result, list) and len(result) > 0 and not dry_run:
            with open(gear_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            print(f"✅ Updated additional_gear.json ({len(result)} items)")
        return [], len(result) if isinstance(result, list) else 0

    except Exception as e:
        print(f"⚠️ Note on Additional Gear sync: {e}")
        return [], 0

def check_csv_hashes(cache_file):
    if not os.path.exists(cache_file):
        return False, None, None

    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache = json.load(f)
        
        # Download and compare hashes
        sched_csv = fetch_sheet_csv(GID_SCHEDULE)
        plan_csv = fetch_sheet_csv(GID_LOAD_PLAN)
        
        h_sched = hashlib.sha256(sched_csv.encode("utf-8")).hexdigest()
        h_plan = hashlib.sha256(plan_csv.encode("utf-8")).hexdigest()

        is_same = (h_sched == cache.get("schedule_hash") and h_plan == cache.get("load_plan_hash"))
        return is_same, h_sched, h_plan
    except Exception:
        return False, None, None

def print_diff_report(sched_diffs, plan_diffs):
    print("\n" + "=" * 60)
    print("📋 GOOGLE SHEETS CHANGE REVIEW REPORT")
    print("=" * 60)

    total_changes = len(sched_diffs) + len(plan_diffs)
    if total_changes == 0:
        print("✨ No changes detected! Local files match the Google Spreadsheet.")
    else:
        if sched_diffs:
            print(f"\n⏱️  Schedule Changes ({len(sched_diffs)}):")
            for d in sched_diffs:
                print(f"   {d}")
        if plan_diffs:
            print(f"\n🚛 Trailer Load Plan Changes ({len(plan_diffs)}):")
            for d in plan_diffs:
                print(f"   {d}")

    print("=" * 60 + "\n")
    return total_changes

def main():
    args = sys.argv[1:]
    dry_run = any(arg in args for arg in ["--dry-run", "--check", "-n"])
    interactive = any(arg in args for arg in ["--interactive", "-i"])
    force = any(arg in args for arg in ["--force", "-f"])

    key = get_api_key()
    if not key:
        print("❌ Error: No Gemini API key found.")
        print("Please set GEMINI_API_KEY environment variable or ensure ~/.pi/agent/auth.json exists.")
        sys.exit(1)

    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_file = os.path.join(root_dir, "scripts", ".sheet_cache.json")

    # Fast hash check unless forcing
    if not force:
        print("🔍 Checking Google Sheets for changes...")
        is_same, h1, h2 = check_csv_hashes(cache_file)
        if is_same:
            print("✨ Google Sheets has NOT changed since the last sync.")
            print("   (CSV content is identical. Pass --force to run full re-extraction anyway.)")
            return

    mode_label = "DRY RUN PREVIEW" if dry_run else ("INTERACTIVE REVIEW" if interactive else "FULL SYNC")
    print(f"🚀 Starting {mode_label}...")

    try:
        # Run in dry_run mode first if reviewing
        is_review = dry_run or interactive
        sched_diffs, races_cnt, rowers_cnt, sched_hash = sync_schedule(key, root_dir, dry_run=is_review)
        plan_diffs, tiers_cnt, boats_cnt, plan_hash = sync_load_plan(key, root_dir, dry_run=is_review)
        sync_additional_gear(key, root_dir, dry_run=is_review)

        total_changes = print_diff_report(sched_diffs, plan_diffs)

        if dry_run:
            print("ℹ️  Dry run preview complete. No files were modified.")
            print("   To apply changes, run: ./sync-sheets.sh")
            return

        if interactive:
            if total_changes == 0:
                print("No changes to apply.")
                return
            response = input("👉 Do you want to apply these changes to the files? [y/N]: ").strip().lower()
            if response not in ["y", "yes"]:
                print("❌ Sync aborted by user. Files left unchanged.")
                return
            # Apply changes
            print("💾 Applying changes to JSON files...")
            sync_schedule(key, root_dir, dry_run=False)
            sync_load_plan(key, root_dir, dry_run=False)
            sync_additional_gear(key, root_dir, dry_run=False)

        # Save cache hashes
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({"schedule_hash": sched_hash, "load_plan_hash": plan_hash}, f)
        except Exception:
            pass

        print("🎉 Sync complete! All JSON files updated.")

    except Exception as e:
        print(f"\n❌ Error during sync: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
