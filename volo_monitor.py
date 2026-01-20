import os
import json
import hashlib
import requests
import sys

# --- CONFIGURATION ---
NTFY_TOPIC = "davallree-sf-volleyball-alerts"
CACHE_FILE = "known_games.json"
# The GraphQL endpoint Volo uses
API_URL = "https://api.volosports.com/v1/graphql"
TARGET_URL = "https://www.volosports.com/discover?cityName=San%20Francisco&sportNames%5B0%5D=Volleyball"

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

    games = []
    s = requests.Session()

    # --- STRATEGY 1: TALK TO THE API DIRECTLY ---
    print("🚀 Attempting GraphQL API Fetch...")
    # This is the exact query Volo uses to find games
    query = {
        "operationName": "DiscoverPrograms",
        "variables": {
            "cityName": "San Francisco",
            "sportNames": ["Volleyball"],
            "limit": 50
        },
        "query": """
        query DiscoverPrograms($cityName: String, $sportNames: [String], $limit: Int) {
          discoverPrograms(cityName: $cityName, sportNames: $sportNames, limit: $limit) {
            items {
              name
              slug
              startTime
              locationName
              sportName
            }
          }
        }
        """
    }
    
    try:
        api_res = s.post(API_URL, headers=headers, json=query, timeout=15)
        if api_res.status_code == 200:
            data = api_res.json()
            items = data.get('data', {}).get('discoverPrograms', {}).get('items', [])
            if items:
                for p in items:
                    games.append({
                        "title": p.get('name'),
                        "details": f"{p.get('locationName')} | {p.get('startTime')}",
                        "link": f"https://www.volosports.com/event/{p.get('slug')}"
                    })
                print(f"✅ API Success! Found {len(games)} games.")
                return games
    except Exception as e:
        print(f"⚠️ API Route failed: {e}")

    # --- STRATEGY 2: FALLBACK TO DEEP PAGE SCAN ---
    print("🚀 Falling back to Deep Page Scan...")
    try:
        res = s.get(TARGET_URL, headers=headers, timeout=15)
        if "__NEXT_DATA__" in res.text:
            start_marker = '<script id="__NEXT_DATA__" type="application/json">'
            start = res.text.find(start_marker) + len(start_marker)
            end = res.text.find('</script>', start)
            json_data = json.loads(res.text[start:end])
            
            def find_volleyball(obj):
                if isinstance(obj, dict):
                    if str(obj.get('sportName', '')).lower() == 'volleyball' and 'slug' in obj:
                        games.append({
                            "title": obj.get('name'),
                            "details": f"{obj.get('locationName')} | {obj.get('startTime')}",
                            "link": f"https://www.volosports.com/event/{obj.get('slug')}"
                        })
                    for v in obj.values(): find_volleyball(v)
                elif isinstance(obj, list):
                    for i in obj: find_volleyball(i)
            
            find_volleyball(json_data)
    except Exception as e:
        print(f"❌ Page Scrape failed: {e}")

    return games

def main():
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'w') as f: json.dump([], f)
    with open(CACHE_FILE, 'r') as f:
        known_ids = json.load(f)
    
    all_found = scrape_volo()
    
    # Deduplicate by link
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
