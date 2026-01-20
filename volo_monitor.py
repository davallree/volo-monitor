import os
import json
import hashlib
import requests
import time

# --- CONFIGURATION ---
NTFY_TOPIC = "davallree-sf-volleyball-alerts"
CACHE_FILE = "known_games.json"
# Using the main domain's GraphQL gateway to avoid DNS resolution issues
GRAPHQL_URL = "https://www.volosports.com/api/graphql"

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
    payload = {
        "operationName": "searchPrograms",
        "variables": {
            "input": {
                "cityName": "San Francisco",
                "sportNames": ["Volleyball"],
                "view": "SPORTS",
                "subView": "DAILY",
                "limit": 50,
                "offset": 0
            }
        },
        "query": """query searchPrograms($input: SearchProgramsInput!) {
          searchPrograms(input: $input) {
            items {
              id
              name
              slug
              sportName
              locationName
              startTime
              registrationStatus
            }
          }
        }"""
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.volosports.com/discover",
        "Origin": "https://www.volosports.com"
    }

    # Retry logic: Try 3 times with increasing wait times
    for attempt in range(3):
        try:
            print(f"🚀 Requesting data (Attempt {attempt + 1})...")
            response = requests.post(GRAPHQL_URL, json=payload, headers=headers, timeout=20)
            
            if response.status_code == 200:
                data = response.json()
                items = data.get('data', {}).get('searchPrograms', {}).get('items', [])
                return [
                    {
                        "title": item.get('name'),
                        "details": f"{item.get('locationName')} | {item.get('startTime')}",
                        "slug": item.get('slug')
                    }
                    for item in items if "volleyball" in item.get('sportName', '').lower()
                ]
            else:
                print(f"⚠️ Server returned {response.status_code}. Retrying...")
        except Exception as e:
            print(f"⚠️ Attempt {attempt + 1} failed: {e}")
        
        time.sleep(5 * (attempt + 1)) # Wait 5s, then 10s

    return []

def main():
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'w') as f: json.dump([], f)
    
    with open(CACHE_FILE, 'r') as f:
        known_ids = json.load(f)
    
    current_games = scrape_volo()
    print(f"🔎 Found {len(current_games)} active volleyball listings.")
    
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
        print("😴 No new items found.")

if __name__ == "__main__":
    main()
