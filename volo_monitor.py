import os
import json
import hashlib
import requests
import re
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
    fingerprint = f"{game['link']}-{game['details']}"
    return hashlib.md5(fingerprint.encode()).hexdigest()

def scrape_volo():
    games = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Force a standard desktop view
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        
        print("🚀 Accessing Volo Discover...")
        page.goto(VOLO_URL, wait_until="networkidle")
        
        # Volo needs a long time to "hydrate" the React components
        print("⏳ Waiting for cards to render...")
        page.wait_for_timeout(15000) 

        # 1. Find the "Event Links" first
        # Every card has a link that goes to /event/
        event_links = page.query_selector_all('a[href*="/event/"]')
        
        for link_el in event_links:
            try:
                href = link_el.get_attribute('href')
                
                # 2. Walk up to the main container for this card
                # We look for the div that contains the icons (SVGs)
                # Usually 3-5 levels up from the link
                container = link_el.evaluate_handle("el => el.closest('div[style*=\"flex-direction: column\"]')").as_element()
                if not container:
                    continue

                # 3. Verify it has the "Card DNA" (The icons you saw)
                icons = container.query_selector_all('svg')
                if len(icons) < 1:
                    continue

                # 4. Extract Text
                raw_text = container.inner_text().strip()
                lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
                
                if len(lines) >= 2:
                    # Filter out the generic "Volleyball" label often at the top
                    title = lines[1] if lines[0].lower() == "volleyball" else lines[0]
                    # Everything else is the time, place, and spots
                    details = " | ".join(lines[1:5])

                    # Only add if we haven't seen this link in this specific run
                    if not any(g['link'] == href for g in games):
                        # Final check: Is it actually volleyball?
                        if "volleyball" in raw_text.lower():
                            games.append({
                                "title": title,
                                "details": details,
                                "link": href
                            })
            except:
                continue
                
        browser.close()
    
    print(f"✨ Successfully detected {len(games)} volleyball listings.")
    return games

def main():
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'w') as f: json.dump([], f)
    
    with open(CACHE_FILE, 'r') as f:
        known_ids = json.load(f)
    
    current_games = scrape_volo()
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
        print("😴 No new games detected.")

if __name__ == "__main__":
    main()
