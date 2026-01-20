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
            f"📅 {game['info']}\n"
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
        print(f"✅ Alert sent: {game['title']}")
    except Exception as e:
        print(f"❌ Notification error: {e}")

def get_game_id(game):
    """Unique ID based on title, time, and link."""
    fingerprint = f"{game['title']}-{game['info']}-{game['link']}"
    return hashlib.md5(fingerprint.encode()).hexdigest()

def scrape_volo():
    found_games = []
    with sync_playwright() as p:
        # 1. Use a large window size to force the Desktop layout
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        print("🚀 Opening Volo...")
        page.goto(VOLO_URL, wait_until="networkidle")
        
        # 2. Aggressive Loading: Scroll down and wait 12 seconds
        # This triggers any 'lazy loading' of cards
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        print("⏳ Waiting for list to populate...")
        page.wait_for_timeout(12000) 

        # 3. Super-Broad Search: Find every single link that points to an event
        # This ignores card structure entirely and just finds the 'Register' links
        potential_links = page.query_selector_all('a[href*="/event/"]')
        
        for link_el in potential_links:
            try:
                href = link_el.get_attribute('href')
                
                # Move 'up' the HTML tree from the link to find the containing block
                # This grabs the text associated with that specific registration link
                card_container = link_el.evaluate_handle("el => el.closest('div')").as_element()
                raw_text = card_container.inner_text() if card_container else ""
                
                # We split the text by lines to find the Title and Date
                lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
                
                if len(lines) >= 2 and "volleyball" in raw_text.lower():
                    # Usually the first line is the title, second/third is date/time
                    title = lines[0]
                    # We grab everything else as 'info'
                    info = " | ".join(lines[1:4])
                    
                    found_games.append({
                        "title": title,
                        "info": info,
                        "link": href
                    })
            except:
                continue
                
        browser.close()
    
    # De-duplicate the list (in case one card had two links)
    unique_dict = {get_game_id(g): g for g in found_games}
    print(f"✨ Found {len(unique_dict)} volleyball listings.")
    return list(unique_dict.values())

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
        print("✅ Cache updated with new games.")
    else:
        print("😴 No new games found.")

if __name__ == "__main__":
    main()
