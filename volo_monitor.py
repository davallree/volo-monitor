import os
import json
import hashlib
import requests  # We use requests instead of smtplib now
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
VOLO_URL = "https://www.volosports.com/discover?cityName=San%20Francisco&subView=DAILY&view=SPORTS&sportNames%5B0%5D=Volleyball"
CACHE_FILE = "known_games.json"

# --- NTFY CONFIGURATION ---
# 1. Download the 'ntfy' app on your phone.
# 2. Click '+' and subscribe to the topic below.
# 3. Change 'my-secret-vball-topic' to something unique to you.
NTFY_TOPIC = "davallree-sf-volleyball-alerts" 

def send_notification(game):
    """Sends a push notification to your phone via ntfy.sh"""
    try:
        response = requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=f"New Game: {game['title']}\n{game['info']}\nLink: https://www.volosports.com{game['link']}".encode('utf-8'),
            headers={
                "Title": "🏐 New Volo Volleyball Found!",
                "Priority": "high",
                "Tags": "volleyball,sf"
            }
        )
        if response.status_code == 200:
            print(f"✅ Push notification sent for: {game['title']}")
        else:
            print(f"❌ ntfy error: {response.status_code}")
    except Exception as e:
        print(f"❌ Failed to send push: {e}")

def get_game_id(game):
    """Creates a unique fingerprint for a game so we don't double-notify."""
    fingerprint = f"{game['title']}-{game['info']}-{game['link']}"
    return hashlib.md5(fingerprint.encode()).hexdigest()

def scrape_volo():
    games = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("Accessing Volo Discover Page...")
        page.goto(VOLO_URL, wait_until="networkidle")
        page.wait_for_timeout(5000) 

        # Target the program cards
        cards = page.query_selector_all('div[class*="ProgramCard"], a[href*="/event/"]')
        
        for card in cards:
            try:
                title_el = card.query_selector('h3, [class*="title"]')
                if not title_el: continue
                
                title = title_el.inner_text().strip()
                link = card.get_attribute('href') or card.query_selector('a').get_attribute('href')
                
                details = card.query_selector_all('p, span')
                info_text = " | ".join([d.inner_text().strip() for d in details if d.inner_text().strip()])

                if "volleyball" in title.lower():
                    games.append({
                        "title": title,
                        "info": info_text,
                        "link": link
                    })
            except:
                continue
                
        browser.close()
    return games

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
        print("No new volleyball games found.")

if __name__ == "__main__":
    main()
