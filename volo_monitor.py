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
    """Sends a push notification via ntfy.sh"""
    try:
        message = (
            f"🏐 {game['title']}\n"
            f"📅 {game['details']}\n"
            f"🔗 https://www.volosports.com{game['link']}"
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
    """Creates a unique ID based on the link and date/time details."""
    fingerprint = f"{game['link']}-{game['details']}"
    return hashlib.md5(fingerprint.encode()).hexdigest()

def scrape_volo():
    games = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 1000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        print("🚀 Opening Volo Discover...")
        page.goto(VOLO_URL, wait_until="networkidle")
        
        # Wait for React to render the actual content cards
        print("⏳ Waiting for cards to hydrate...")
        page.wait_for_timeout(10000)

        # Find all event links
        event_links = page.query_selector_all('a[href*="/event/"]')
        
        for link_el in event_links:
            try:
                href = link_el.get_attribute('href')
                # Find the container that holds the text and icons
                container = link_el.evaluate_handle("el => el.closest('div[style*=\"flex-direction: column\"]')").as_element()
                
                if container:
                    raw_text = container.inner_text().strip()
                    if "volleyball" in raw_text.lower():
                        lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
                        
                        # Title is usually the first line that isn't just "VOLLEYBALL"
                        title = lines[1] if lines[0].upper() == "VOLLEYBALL" else lines[0]
                        details = " | ".join(lines[1:6])

                        if not any(g['link'] == href for g in games):
                            games.append({
                                "title": title,
                                "details": details,
                                "link": href
                            })
            except:
                continue
                
        browser.close()
    return games

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
        print("✅ Success: New games detected and memory updated.")
    else:
        print("😴 No new games found in this run.")

if __name__ == "__main__":
    main()
