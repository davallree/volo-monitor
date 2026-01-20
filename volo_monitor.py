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
    """Sends a push notification to your phone via ntfy.sh"""
    try:
        message = (
            f"🏐 {game['title']}\n"
            f"📅 {game['info']}\n"
            f"🔗 https://www.volosports.com{game['link']}"
        )
        response = requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode('utf-8'),
            headers={
                "Title": "New Volo Volleyball Game!",
                "Priority": "high",
                "Tags": "volleyball,sf"
            }
        )
        if response.status_code == 200:
            print(f"✅ Notification sent for: {game['title']}")
    except Exception as e:
        print(f"❌ Failed to send notification: {e}")

def get_game_id(game):
    """Creates a unique fingerprint so we don't notify twice for the same game."""
    fingerprint = f"{game['title']}-{game['info']}-{game['link']}"
    return hashlib.md5(fingerprint.encode()).hexdigest()

def scrape_volo():
    games = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        print("🔍 Scanning Volo Discover page...")
        page.goto(VOLO_URL, wait_until="networkidle")
        
        # Wait 10 seconds to ensure the React grid/list is fully loaded
        page.wait_for_timeout(10000)

        # TARGETED SEARCH: We only look inside 'Program Cards'. 
        # This ignores 'Volleyball' text in sidebars, filters, or headers.
        cards = page.query_selector_all('div[class*="ProgramCard"]')
        
        for card in cards:
            try:
                title_el = card.query_selector('h3, h4, [class*="title"]')
                if not title_el: continue
                title = title_el.inner_text().strip()

                link_el = card.query_selector('a')
                link = link_el.get_attribute('href') if link_el else ""

                # Combine paragraph text to get the full schedule/location info
                p_elements = card.query_selector_all('p')
                info_text = " | ".join([p.inner_text().strip() for p in p_elements if p.inner_text().strip()])

                # Ensure it's a real volleyball event with a valid link
                if "volleyball" in title.lower() and "/event/" in link:
                    games.append({
                        "title": title,
                        "info": info_text,
                        "link": link
                    })
            except Exception:
                continue
                
        browser.close()
    
    unique_games = {get_game_id(g): g for g in games}.values()
    print(f"✨ Found {len(unique_games)} unique volleyball listings.")
    return list(unique_games)

def main():
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'w') as f:
            json.dump([], f)
    
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
        with open(CACHE_FILE, 'w') as f:
            json.dump(known_ids, f)
        print("Updated cache with new games.")
    else:
        print("Checked: No new games found.")

if __name__ == "__main__":
    main()
