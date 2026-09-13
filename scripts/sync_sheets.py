#!/usr/bin/env python3
"""
Sync regatta data from Google Sheets into race_schedule.json and regatta_load_plan.json.
Uses Google Gemini via ~/.pi/agent/auth.json or GEMINI_API_KEY.
"""

import os
import sys
import json
import re
import urllib.request
import urllib.error

SPREADSHEET_ID = "1Vt7A1fwQDqtUF1455LZgacA4fy5tr2AUYojgEgrrlEM"
GID_SCHEDULE = "1295452530"   # 'v2' tab
GID_LOAD_PLAN = "1504778411"  # 'Load Plan' tab

def get_api_key():
    # 1. Environment variable
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key

    # 2. Pi agent auth store
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
            "temperature": 0.1
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
                print(f"   ⚡ [{boat}] {note}")

    return rerig_count

def sync_schedule(api_key, root_dir):
    print("📥 Downloading Schedule CSV from Google Sheets (tab: v2)...")
    csv_data = fetch_sheet_csv(GID_SCHEDULE)

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
   - event_number: integer
   - event_class: string (e.g. 'W Mst C 2X (Final)')
   - boat: string
   - oars_assigned: string (e.g. 'BYWW (Pinks)', 'BGW (Yellow)')
   - cox: string or null (e.g. 'Isaac', 'Millzy', or null if uncoxed)
   - crew: string (e.g. 'Ellie, Jacinda' or 'COX: Isaac, JoY, Deb, Paula, Jolanda')
   - notes: string
   - rerig_required: boolean
   - rerig_note: string or null
4. COXSWAIN HANDLING:
   - The CSV column 'Cox' specifies the coxswain (e.g., Isaac, Millzy).
   - In 'crew', for any coxed race (like 4X+ or 8+ in events 19, 29, 53, 111), always prefix the crew string with 'COX: <Name>, ' (e.g. 'COX: Isaac, JoY, Deb, Paula, Jolanda').
   - Also set the 'cox' field to the coxswain's name (e.g. "Isaac" or "Millzy").
5. Preserve existing re-rig warnings and notes where applicable.

SPECIAL REGATTA HEATS & PROGRESSIONS HANDLING:
- Event 34 (Saturday W Mst D 2X):
  * Heat 1 (11:55): Ange, Vivienne in Moa (oars: BYWW (Pinks)).
  * Heat 2 (12:00): Liz, Claire in Matiu (oars: BYWW x 1; BWW x 1) (note: row in CSV has blank event number, but it is Event 34 Heat 2).
  * Final (12:30): In the sheet, boat/oar columns are left blank because either or both crews may qualify. You MUST include a distinct entry for the 12:30 Final:
    - day: "Saturday", block: 3, time: "12:30", event_number: 34, event_class: "W Mst D 2X (Final)"
    - boat: "Moa & Matiu"
    - oars_assigned: "Moa: BYWW (Pinks)\\nMatiu: BYWW x 1, BWW x 1"
    - crew: "Heat 1: Ange, Vivienne (Moa)\\nHeat 2: Liz, Claire (Matiu)"
    - notes: "Final: Either or both crews race subject to qualification from 11:55/12:00 heats"
    - rerig_required: false, rerig_note: null

- Event 125 (Sunday W Mst D 4X-):
  * Heat 1 (13:53): Mahanga, oars BWW x 4; BYWW x 4 (Ange, Jolanda, Jacinda, Paula).
  * Heat 2 (13:59): Hawkins, oars BWW x 4; BYWW x 4 (Liz, Deb, Deidre, Claire).
  * Final (14:29): Include the Final at 14:29 for qualifying crew(s).

- Event 86 (Sunday W MNw 2X):
  * Include Heat at 10:14 / 10:20 (Matiu) and Final at 11:14 (Matiu).

- Event 78 (Sunday W Mst C 4X-):
  * Include Heat at 8:30 (Hawkins) and Final at 9:30 (Hawkins).

CORRECTIONS FOR KNOWN SPREADSHEET RE-RIG ERRORS (Makaro & Hawkins):
- Makaro Re-rig Sequence (Sunday):
  * Event 73 (08:42/08:48, 2X Double Scull): rerig_required: true, rerig_note: "RE-RIG AS PAIR (2- SWEEP) FOR EVENT 90" (Spreadsheet says race 93 by mistake).
  * Event 90 (10:26, 2- Pair): rerig_required: true, rerig_note: "RE-RIG BACK TO DOUBLE (2X SCULL) FOR EVENT 101" (Spreadsheet incorrectly says after race 78 / for race 102).
  * Event 101 (11:43, 2X Double Scull): rerig_required: false, rerig_note: null, notes: "Double Scull (2X) - Must have been re-rigged back to double following Event 90".

- Hawkins Re-rig Sequence (Saturday to Sunday):
  * Event 38 (Saturday 12:15/12:20, 4X- Quad): rerig_required: true, rerig_note: "RE-RIG AS COXLESS 4 (SWEEP) FOR EVENT 65".
  * Event 65 (Saturday 15:10, 4- Four): rerig_required: true, rerig_note: "OVERNIGHT RE-RIG: Re-rig back to Quad (4X- scull) for Sunday Event 78 (08:30)" (Spreadsheet incorrectly says after race 51).
  * Event 78 (Sunday 08:30, 4X- Quad): rerig_required: false, rerig_note: null, notes: "Scull (4X-) - Re-rigged back to quad overnight following Event 65; Final at 09:30".

Input CSV Data:
{csv_data}
"""

    result = call_gemini(api_key, prompt)

    print("🧠 Running deterministic re-rig algorithm across boat timelines...")
    rerigs = compute_rerigs(result.get("races", []))
    if "metadata" in result:
        result["metadata"]["total_rerigs"] = rerigs

    with open(sched_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    race_count = len(result.get("races", []))
    rower_count = len(result.get("rowers", []))
    print(f"✅ Updated race_schedule.json ({race_count} races, {rower_count} rowers)")

def sync_load_plan(api_key, root_dir):
    print("📥 Downloading Load Plan CSV from Google Sheets (tab: Load Plan)...")
    csv_data = fetch_sheet_csv(GID_LOAD_PLAN)

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
4. fleet_specifications must be array of boat objects (boat_name, seats, riggers_required, notes, requires_re_rig).
5. oar_loading_plan must contain 'sweep_oars' and 'sculling_oars' with total_summary and allocations array (oar_set, quantity, assignments).
6. pre_regatta_maintenance_checklists must contain 'waimarino_shed' and 'town_shed' arrays of objects with id, item, tasks.
7. safety_and_spares must contain 'safety_mandates' and 'spares_box_checklist'.
8. Use Island Bay for the 2- (not Whanganui).

Input CSV Data:
{csv_data}
"""

    result = call_gemini(api_key, prompt)

    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    tier_count = len(result.get("trailer_load_configuration", []))
    boat_count = len(result.get("fleet_specifications", []))
    print(f"✅ Updated regatta_load_plan.json ({tier_count} trailer tiers, {boat_count} fleet specs)")

def sync_additional_gear(api_key, root_dir):
    gear_path = os.path.join(root_dir, "additional_gear.json")

    # 1. Check if an 'Additional Gear', 'Regatta Gear', or 'Gear' tab exists in the spreadsheet
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
            return

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
        if isinstance(result, list) and len(result) > 0:
            with open(gear_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            print(f"✅ Updated additional_gear.json ({len(result)} items from spreadsheet)")

    except Exception as e:
        print(f"⚠️ Note on Additional Gear sync: {e}")

def main():
    key = get_api_key()
    if not key:
        print("❌ Error: No Gemini API key found.")
        print("Please set GEMINI_API_KEY environment variable or ensure ~/.pi/agent/auth.json exists.")
        sys.exit(1)

    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    try:
        sync_schedule(key, root_dir)
        sync_load_plan(key, root_dir)
        sync_additional_gear(key, root_dir)
        print("\n🎉 Sync complete! All JSON files updated.")
    except Exception as e:
        print(f"\n❌ Error during sync: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
