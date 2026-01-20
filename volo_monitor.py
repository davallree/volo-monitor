import os
import json
import hashlib
import requests
import sys

# --- CONFIGURATION ---
NTFY_TOPIC = "davallree-sf-volleyball-alerts"
CACHE_FILE = "known_games.json"
TARGET_URL = "https://www.volosports.com/discover?cityName=San%20Francisco&sportNames%5B0%5D=Volleyball"

def send_notification(game):
    try:
        message = (
            f"🏐 {game['title']}\n"
            f"📅 {game['details']}\n"
            f"🔗 {game['link']}"
        )
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode('utf-8'),
            headers={"Title": "New Volo Game Found!", "Priority": "high", "Tags": "volleyball,sf"}
        )
        print(f"✅ Notification sent: {game['title']}")
    except Exception as e:
        print(f"❌ Notification error: {e}")

def get_game_id(game):
    fingerprint = f"{game['link']}-{game['details']}"
    return hashlib.md5(fingerprint.encode()).hexdigest()

def find_all_games_brute_force(obj, found_games=None):
    """
    Recursively scans the entire JSON tree for objects that look like Volo events.
    Volo events typically have a 'name', 'slug', and 'sportName'.
    """
    if found_games is None:
        found_games = []

    if isinstance(obj, dict):
        # Check if this object has the signature of a Volo Program/Event
        if all(k in obj for k in ('name', 'slug')) and 'sportName' in str(obj):
            sport = str(obj.get('sportName', '')).lower()
            if sport == 'volleyball':
                game = {
                    "title": obj.get('name'),
                    "details": f"{obj.get('locationName', 'TBD')} | {obj.get('startTime', 'See site')}",
                    "link": f"https://www.volosports.com/event/{obj.get('slug')}"
                }
                # Avoid adding the exact same game multiple times if it appears twice in the JSON
                if game not in found_games:
                    found_games.append(game)
        
        # Keep searching deeper into the dictionary
        for v in obj.values():
            find_all_games_brute_force(v, found_games)
            
    elif isinstance(obj, list):
        # Search through lists
        for item in obj:
            find_all_games_brute_force(item, found_games)
            
    return found_games

def scrape_with_session():
    headers_json = os.environ.get("VOLO_SESSION_HEADERS")
    if not headers_json:
        print("❌ Error: VOLO_SESSION_HEADERS secret is missing!")
        sys.exit(1)
    
    try:
        raw_headers = json.loads(headers_json)
        # Strip HTTP/2 pseudo-headers (keys starting with ':')
        headers = {k: v for k, v in raw_headers.items() if not k.startswith(':')}
    except Exception as e:
        print(f"❌ Error parsing headers: {e}")
        sys.exit(1)

    print("🚀 Replaying session to Volo Sports...")
    
    try:
        s = requests.Session()
        response = s.get(TARGET_URL, headers=headers, timeout=20)
        
        if response.status_code != 200:
            print(f"🚫 Access Denied (Status: {response.status_code})")
            return []
            
        if "__NEXT_DATA__" in response.text:
            print("🔓 Extracting Next.js Data...")
            start_marker = '<script id="__NEXT_DATA__" type="application/json">'
            start = response.text.find(start_marker) + len(start_marker)
            end = response.text.find('</script>', start)
            json_data = json.loads(response.text[start:end])
            
            # Use brute force to find those 2 games you see on the site
            games = find_all_games_brute_force(json_data)
            return games
            
    except Exception as e:
        print(f"❌ Scrape failed: {e}")

    return []

def main():
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'w') as f: json.dump([], f)
    with open(CACHE_FILE, 'r') as f:
        known_ids = json.load(f)
    
    current_games = scrape_with_session()
    print(f"🔎 Found {len(current_games)} volleyball games.")
    
    new_found = False
    for game in current_games:
        gid = get_game_id(game)
        if gid not in known_ids:
            send_notification(game)
            known_ids.append(gid)
            new_found = True
            
    if new_found:
        with open(CACHE_FILE, 'w') as f: json.dump(known_ids, f)
        print("✅ Cache updated.")
    else:
        print("😴 No new updates.")

if __name__ == "__main__":
    main()
