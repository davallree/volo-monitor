import os
import json
import hashlib
import requests
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
VOLO_URL = "https://www.volosports.com/discover?cityName=San%20Francisco&subView=DAILY&view=SPORTS&sportNames%5B0%5D=Volleyball"
CACHE_FILE = "known_games.json"
NTFY_TOPIC = "davallree-sf-volleyball-alerts" 

def send_notification(game):
    try:
        message = f"🏐 {game['title']}\n📅 {game['details']}\n🔗 https://www.volosports.com{game['link']}"
        requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", data=message.encode('utf-8'),
                      headers={"Title": "New Volo Game Found!", "Priority": "high", "Tags": "volleyball,sf"})
        print(f"✅ Notification sent: {game['title']}")
    except Exception as e:
        print(f"❌ Notification error: {e}")

def get_game_id(game):
    return hashlib.md5(f"{game['link']}-{game['details']}".encode()).hexdigest()

def scrape_volo():
    games = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Use a very generic, high-trust User Agent
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # INTERNAL DATA CAPTURE
        # We listen for the specific background request Volo makes to load the list
        def handle_response(response):
            if "graphql" in response.url or "discover" in response.url:
                try:
                    data = response.json()
                    # Navigating Volo's JSON structure for 'program' listings
                    items = data.get('data', {}).get('searchPrograms', {}).get('items', [])
                    for item in items:
                        if "volleyball" in item.get('sportName', '').lower():
                            games.append({
                                "title": item.get('name', 'Volleyball Game'),
                                "details": f"{item.get('locationName', 'SF')} | {item.get('startTime', '')}",
                                "link": f"/event/{item.get('slug', '')}"
                            })
                except:
                    pass

        page.on("response", handle_response)

        print("🚀 Requesting data from Volo API...")
        # Navigate to the page to trigger the background API calls
        page.goto(VOLO_URL, wait_until="networkidle", timeout=60000)
        
        # Give it a bit extra time to finish background API calls
        page.wait_for_timeout(5000)
        browser.close()

    return games

def main():
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'w') as f: json.dump([], f)
    with open(CACHE_FILE, 'r') as f:
        known_ids = json.load(f)
    
    current_games = scrape_volo()
    
    # FALLBACK: If API interception failed, try a final forced-wait scan
    if not current_games:
        print("⚠️ API capture empty, likely blocked. No games found.")
        return

    print(f"🔎 Found {len(current_games)} games via API.")
    
    new_found = False
    for game in current_games:
        gid = get_game_id(game)
        if gid not in known_ids:
            send_notification(game)
            known_ids.append(gid)
            new_found = True
            
    if new_found:
        with open(CACHE_FILE, 'w') as f: json.dump(known_ids, f)
        print("✅ Memory updated.")
    else:
        print("😴 No new updates.")

if __name__ == "__main__":
    main()
