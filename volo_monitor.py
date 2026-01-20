import os
import json
import hashlib
import requests

# --- CONFIGURATION ---
NTFY_TOPIC = "davallree-sf-volleyball-alerts"
CACHE_FILE = "known_games.json"
GRAPHQL_URL = "https://api.volosports.com/graphql"

def send_notification(game):
    """Sends a push notification via ntfy.sh"""
    try:
        message = (
            f"🏐 {game['title']}\n"
            f"📅 {game['details']}\n"
            f"🔗 https://www.volosports.com/event/{game['slug']}"
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
    """Creates a unique ID based on the event slug and date string."""
    fingerprint = f"{game['slug']}-{game['details']}"
    return hashlib.md5(fingerprint.encode()).hexdigest()

def scrape_volo():
    """Hits the Volo GraphQL API directly."""
    # This is the exact query payload Volo uses for its Discovery page
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
              __typename
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

    games = []
    try:
        print("🚀 Sending direct request to Volo API...")
        response = requests.post(GRAPHQL_URL, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 403:
            print("🚫 403 Forbidden: API is blocking the connection. Try reducing run frequency.")
            return []
            
        response.raise_for_status()
        data = response.json()
        
        items = data.get('data', {}).get('searchPrograms', {}).get('items', [])
        print(f"📡 API returned {len(items)} total items.")

        for item in items:
            # Filter for volleyball and meaningful registrations
            sport = item.get('sportName', '').lower()
            if "volleyball" in sport:
                games.append({
                    "title": item.get('name'),
                    "details": f"{item.get('locationName')} | {item.get('startTime')}",
                    "slug": item.get('slug')
                })
    except Exception as e:
        print(f"❌ API Request failed: {e}")

    return games

def main():
    # Initialize cache file
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'w') as f: json.dump([], f)
    
    with open(CACHE_FILE, 'r') as f:
        known_ids = json.load(f)
    
    current_games = scrape_volo()
    print(f"🔎 Found {len(current_games)} active volleyball games.")
    
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
        print("😴 No new games detected.")

if __name__ == "__main__":
    main()
