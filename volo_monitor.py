import os
import json
import hashlib
import requests
import sys
import re

# --- CONFIGURATION ---
NTFY_TOPIC = "davallree-sf-volleyball-alerts"
CACHE_FILE = "known_games.json"
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

def find_games_in_text(text):
    """
    Finds volleyball games by searching for Next.js data patterns 
    or raw JSON blobs hidden in script tags.
    """
    games = []
    # Search for all script tags that might contain JSON
    scripts = re.findall(r'<script.*?> (.*?)</script>', text, re.DOTALL)
    
    for script_content in scripts:
        if '"sportName"' in script_content and 'volleyball' in script_content.lower():
            try:
                # Try to clean up and parse potential JSON
                data = json.loads(script_content.strip())
                
                def deep_search(obj):
                    if isinstance(obj, dict):
                        if obj.get('sportName', '').lower() == 'volleyball' and 'slug' in obj:
                            games.append({
                                "title": obj.get('name', 'Volleyball Game'),
                                "details": f"{obj.get('locationName', 'TBD')} | {obj.get('startTime', 'See site')}",
                                "link": f"https://www.volosports.com/event/{obj.get('slug')}"
                            })
                        for v in obj.values(): deep_search(v)
                    elif isinstance(obj, list):
                        for i in obj: deep_search(i)
                
                deep_search(data)
            except:
                continue
    return games

def scrape_volo():
    headers_json = os.environ.get("VOLO_SESSION_HEADERS")
    if not headers_json:
        print("❌ Error: VOLO_SESSION_HEADERS missing!")
        sys.exit(1)
    
    try:
        raw_headers = json.loads(headers_json)
        # Clean headers: No colons, no restricted browser-only keys
        headers = {k: v for k, v in raw_headers.items() if not k.startswith(':')}
    except Exception as e:
        print(f"❌ Header Error: {e}")
        sys.exit(1)

    print("🚀 Fetching Volo Discover page...")
    try:
        res = requests.get(TARGET_URL, headers=headers, timeout=20)
        if res.status_code != 200:
            print(f"🚫 Denied: {res.status_code}")
            return []
            
        games = find_games_in_text(res.text)
        
        # If regex fails, try a direct string search for the most likely data blob
        if not games and "__NEXT_DATA__" in res.text:
            print("🕵️ Found __NEXT_DATA__, performing surgical extraction...")
            start = res.text.find('{"props":')
            end = res.text.find('</script>', start)
            if start != -1 and end != -1:
                try:
                    blob = json.loads(res.text[start:end])
                    # Re-run deep search on the specific blob
                    def search(obj):
                        if isinstance(obj, dict):
                            if obj.get('sportName', '').lower() == 'volleyball' and 'slug' in obj:
                                games.append({
                                    "title": obj.get('name'),
                                    "details": f"{obj.get('locationName')} | {obj.get('startTime')}",
                                    "link": f"https://www.volosports.com/event/{obj.get('slug')}"
                                })
                            for v in obj.values(): search(v)
                        elif isinstance(obj, list):
                            for i in obj: search(i)
                    search(blob)
                except: pass

        return games
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return []

def main():
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'w') as f: json.dump([], f)
    with open(CACHE_FILE, 'r') as f:
        known_ids = json.load(f)
    
    found_games = scrape_volo()
    # Unique by link
    unique_games = {g['link']: g for g in found_games}.values()
    
    print(f"🔎 Results: Found {len(unique_games)} volleyball games.")
    
    new_found = 0
    for game in unique_games:
        gid = get_game_id(game)
        if gid not in known_ids:
            send_notification(game)
            known_ids.append(gid)
            new_found += 1
            
    if new_found > 0:
        with open(CACHE_FILE, 'w') as f: json.dump(known_ids, f)
        print(f"✅ Cache updated with {new_found} new entries.")
    else:
        print("😴 Nothing new to report.")

if __name__ == "__main__":
    main()
