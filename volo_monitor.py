import os
import json
import hashlib
import requests
import time

# --- CONFIGURATION ---
NTFY_TOPIC = "davallree-sf-volleyball-alerts"
CACHE_FILE = "known_games.json"

# We use the Next.js internal data URL which is often less protected than the API
DATA_URL = "https://www.volosports.com/_next/data/latest/discover.json"

def send_notification(game):
    try:
        message = (
            f"🏐 {game['title']}\n"
            f"📅 {game['details']}\n"
            f"🔗 https://www.volosports.com/event/{game['slug']}"
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
    fingerprint = f"{game['slug']}-{game['details']}"
    return hashlib.md5(fingerprint.encode()).hexdigest()

def scrape_volo():
    # Constructing the exact query params used by the frontend
    params = {
        "cityName": "San Francisco",
        "subView": "DAILY",
        "view": "SPORTS",
        "sportNames[0]": "Volleyball"
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "x-nextjs-data": "1"  # Tells the server to return JSON, not HTML
    }

    for attempt in range(3):
        try:
            print(f"🚀 Fetching Next.js data (Attempt {attempt + 1})...")
            response = requests.get(DATA_URL, params=params, headers=headers, timeout=20)
            
            if response.status_code == 200:
                data = response.json()
                # Next.js structure usually puts data in 'pageProps'
                items = data.get('pageProps', {}).get('initialPrograms', {}).get('items', [])
                
                # Fallback check for different JSON structure
                if not items:
                    items = data.get('data', {}).get('searchPrograms', {}).get('items', [])

                return [
                    {
                        "title": item.get('name'),
                        "details": f"{item.get('locationName')} | {item.get('startTime')}",
                        "slug": item.get('slug')
                    }
                    for item in items if item.get('slug')
                ]
            else:
                print(f"⚠️ Status {response.status_code}. The site might be blocking the request.")
        except Exception as e:
            print(f"⚠️ Request failed: {e}")
        
        time.sleep(5)

    return []

def main():
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'w') as f: json.dump([], f)
    
    with open(CACHE_FILE, 'r') as f:
        known_ids = json.load(f)
    
    current_games = scrape_volo()
    print(f"🔎 Found {len(current_games)} volleyball listings.")
    
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
