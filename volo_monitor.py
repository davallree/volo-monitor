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
    """ID based on link and details to catch updates to existing sessions."""
    fingerprint = f"{game['link']}-{game['details']}"
    return hashlib.md5(fingerprint.encode()).hexdigest()

def scrape_volo():
    games = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Use a desktop viewport to ensure cards aren't hidden in a mobile slider
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()
        
        print("🚀 Accessing Volo Discover...")
        page.goto(VOLO_URL, wait_until="networkidle")
        
        # Wait for the JavaScript to render the icons and images
        page.wait_for_timeout(10000)

        # 1. VISUAL PATTERN MATCHING
        # We look for containers that have a sport image AND at least one icon (SVG)
        # This is the most consistent way to find the actual game listings.
        
        # We find all links that point to an event, then look at their parent containers
        event_links = page.query_selector_all('a[href*="/event/"]')
        
        for link_el in event_links:
            try:
                href = link_el.get_attribute('href')
                
                # Move up to the container that holds the title and the icons
                # Based on the HTML, moving up 3-4 levels gets us the whole card
                card = link_el.evaluate_handle("el => el.closest('div[style*=\"flex-direction: column\"]') or el.parentElement.parentElement").as_element()
                
                if not card: continue
                
                # Check for the icons you mentioned (Clock, Person, Pin)
                # These are always SVGs in the Volo source code
                icons = card.query_selector_all('svg')
                if len(icons) == 0: continue
                
                raw_text = card.inner_text().strip()
                lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
                
                if len(lines) >= 2:
                    # The first line is usually the Title (e.g., 'Indoor Volleyball at...')
                    title = lines[0]
                    # The lines near the icons contain the date, time, and spots left
                    details = " | ".join(lines[1:])

                    # Ensure we aren't picking up the sidebar sport list
                    if "volleyball" in title.lower() or "volleyball" in details.lower():
                        if not any(g['link'] == href for g in games):
                            games.append({
                                "title": title,
                                "details": details,
                                "link": href
                            })
            except:
                continue
                
        browser.close()
    
    print(f"✨ Found {len(games)} volleyball event cards.")
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
        print("Memory updated.")
    else:
        print("No new games detected.")

if __name__ == "__main__":
    main()
