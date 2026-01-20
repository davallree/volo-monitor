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
    """Sends a push notification via ntfy.sh"""
    try:
        message = (
            f"🏐 {game['title']}\n"
            f"📅 {game['details']}\n"
            f"🔗 {game['link']}"
        )
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode('utf-8'),
            headers={
                "Title": "New Volo Game Found!",
                "Priority": "high", 
                "Tags": "volleyball,sf"
            }
        )
        print(f"✅ Notification sent: {game['title']}")
    except Exception as e:
        print(f"❌ Notification error: {e}")

def get_game_id(game):
    """Creates a unique hash for a game to prevent duplicate alerts."""
    fingerprint = f"{game['link']}-{game['details']}"
    return hashlib.md5(fingerprint.encode()).hexdigest()

def scrape_with_session():
    """Uses session headers from GitHub secrets to bypass Cloudflare."""
    headers_json = os.environ.get("VOLO_SESSION_HEADERS")
    if not headers_json:
        print("❌ Error: VOLO_SESSION_HEADERS secret is missing!")
        sys.exit(1)
    
    try:
        headers = json.loads(headers_json)
    except Exception as e:
        print(f"❌ Error: Could not parse header JSON from secret. {e}")
        sys.exit(1)

    games = []
    print("🚀 Replaying session to Volo Sports...")
    
    try:
        s = requests.Session()
        # Request the page using the 'borrowed' browser headers
        response = s.get(TARGET_URL, headers=headers, timeout=20)
        
        if response.status_code == 403:
            print("🚫 403 Forbidden. Your session headers/cookies may have expired.")
            return []
            
        print(f"✅ Access Granted! (Status: {response.status_code})")
        
        # Next.js apps embed their initial state in a JSON blob inside a script tag
        if "__NEXT_DATA__" in response.text:
            print("🔓 Found Next.js Data Blob! Extracting precise data...")
            start_str = '<script id="__NEXT_DATA__" type="application/json">'
            start = response.text.find(start_str) + len(start_str)
            end = response.text.find('</script>', start)
            json_data = json.loads(response.text[start:end])
            
            try:
                # Drilling down into the Next.js page properties for listing items
                programs = json_data['props']['pageProps']['initialPrograms']['items']
                for p in programs:
                    # Double-check it's a Volleyball game
                    if "volleyball" in p.get('sportName', '').lower():
                        games.append({
                            "title": p.get('name'),
                            "details": f"{p.get('locationName')} | {p.get('startTime')}",
                            "link": f"https://www.volosports.com/event/{p.get('slug')}"
                        })
            except KeyError:
                print("⚠️ Warning: Site structure changed. Could not find 'initialPrograms'.")

    except Exception as e:
        print(f"❌ Network request failed: {e}")

    return games

def main():
    # Initialize cache file if it doesn't exist
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'w') as f: json.dump([], f)
    
    with open(CACHE_FILE, 'r') as f:
        known_ids = json.load(f)
    
    current_games = scrape_with_session()
    print(f"🔎 Found {len(current_games)} active games.")
    
    new_found = False
    for game in current_games:
        gid = get_game_id(game)
        if gid not in known_ids:
            send_notification(game)
            known_ids.append(gid)
            new_found = True
            
    if new_found:
        with open(CACHE_FILE, 'w') as f:
            json.dump(known_ids, f)
        print("✅ Cache updated with new games.")
    else:
        print("😴 No new updates found.")

if __name__ == "__main__":
    main()
