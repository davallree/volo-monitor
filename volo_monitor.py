import os
import json
import hashlib
import requests
import sys
import re

# --- CONFIGURATION ---
NTFY_TOPIC = "davallree-sf-volleyball-alerts"
CACHE_FILE = "known_games.json"
BASE_URL = "https://www.volosports.com"
DISCOVER_URL = f"{BASE_URL}/discover?cityName=San%20Francisco&sportNames%5B0%5D=Volleyball"

def send_notification(game):
    try:
        message = f"🏐 {game['title']}\n📅 {game['details']}\n🔗 {game['link']}"
        requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", data=message.encode('utf-8'), 
                      headers={"Title": "New Volo Game Found!", "Priority": "high", "Tags": "volleyball,sf"})
        print(f"✅ Notification sent: {game['title']}")
    except Exception as e:
        print(f"❌ Notification error: {e}")

def get_game_id(game):
    fingerprint = f"{game['link']}-{game['details']}"
    return hashlib.md5(fingerprint.encode()).hexdigest()

def extract_games_recursively(obj, games_list):
    """Deep search for volleyball items in any JSON structure."""
    if isinstance(obj, dict):
        if all(k in obj for k in ('name', 'slug')) and 'sportName' in str(obj):
            if str(obj.get('sportName', '')).lower() == 'volleyball':
                games_list.append({
                    "title": obj.get('name'),
                    "details": f"{obj.get('locationName', 'TBD')} | {obj.get('startTime', 'Check site')}",
                    "link": f"{BASE_URL}/event/{obj.get('slug')}"
                })
        for v in obj.values():
            extract_games_recursively(v, games_list)
    elif isinstance(obj, list):
        for item in obj:
            extract_games_recursively(item, games_list)

def scrape_volo():
    headers_json = os.environ.get("VOLO_SESSION_HEADERS")
    if not headers_json:
        print("❌ Error: VOLO_SESSION_HEADERS secret is missing!")
        sys.exit(1)
    
    try:
        raw_headers = json.loads(headers_json)
        headers = {k: v for k, v in raw_headers.items() if not k.startswith(':')}
    except Exception as e:
        print(f"❌ Error parsing headers: {e}")
        sys.exit(1)

    s = requests.Session()
    games = []

    print("🚀 Step 1: Getting Build ID from main page...")
    try:
        res = s.get(DISCOVER_URL, headers=headers, timeout=15)
        if res.status_code != 200:
            print(f"🚫 Failed to load main page ({res.status_code})")
            return []

        # Find the buildId in the Next.js script tag
        match = re.search(r'"buildId":"(.*?)"', res.text)
        if not match:
            print("❌ Could not find Next.js Build ID.")
            return []
        
        build_id = match.group(1)
        print(f"🔓 Found Build ID: {build_id}")

        # Step 2: Hit the actual JSON data endpoint
        # The URL structure is: /_next/data/{buildId}/discover.json?...
        data_url = f"{BASE_URL}/_next/data/{build_id}/discover.json?cityName=San+Francisco&sportNames%5B0%5D=Volleyball"
        print(f"🚀 Step 2: Fetching clean data from {data_url}")
        
        data_res = s.get(data_url, headers=headers, timeout=15)
        if data_res.status_code == 200:
            extract_games_recursively(data_res.json(), games)
        else:
            print(f"⚠️ JSON fetch failed ({data_res.status_code}), falling back to HTML scan...")
            # If the JSON route fails, scan the HTML blob we already have
            if "__NEXT_DATA__" in res.text:
                json_blob = json.loads(re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', res.text).group(1))
                extract_games_recursively(json_blob, games)

    except Exception as e:
        print(f"❌ Scrape failed: {e}")

    return games

def main():
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'w') as f: json.dump([], f)
    with open(CACHE_FILE, 'r') as f:
        known_ids = json.load(f)
    
    all_found = scrape_volo()
    unique_games = {g['link']: g for g in all_found}.values()
    
    print(f"🔎 Final Count: {len(unique_games)} volleyball games.")
    
    new_count = 0
    for game in unique_games:
        gid = get_game_id(game)
        if gid not in known_ids:
            send_notification(game)
            known_ids.append(gid)
            new_count += 1
            
    if new_count > 0:
        with open(CACHE_FILE, 'w') as f: json.dump(known_ids, f)
        print(f"✅ Cache updated with {new_count} new games.")
    else:
        print("😴 No new updates.")

if __name__ == "__main__":
    main()
