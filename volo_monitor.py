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
        # Launch with 'stealth' settings to bypass bot detection
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 1200},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # This script prevents 'navigator.webdriver' from being true
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = context.new_page()
        print(f"🚀 Visiting Volo SF...")
        
        # Navigate and wait for the page to actually settle
        page.goto(VOLO_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(15000)

        # Check if we were blocked by reCAPTCHA
        if page.query_selector('iframe[title*="reCAPTCHA"]') or "captcha" in page.content().lower():
            print("🚫 BLOCKED: The site is showing a bot-check (reCAPTCHA).")
            return []

        # Volo uses a specific structure for their "Cards"
        # We look for divs that have an ARIA label containing sport info
        cards = page.query_selector_all('div[aria-label*="Volleyball"]')
        
        # If no ARIA cards, try finding links that look like events
        if not cards:
            cards = page.query_selector_all('a[href*="/event/"]')

        print(f"📊 Found {len(cards)} potential card elements.")

        for card in cards:
            try:
                # Find the link inside or on the card
                href = card.get_attribute('href') or card.query_selector('a').get_attribute('href')
                
                # Get all text from the card
                text = card.inner_text().strip()
                if not text or len(text) < 10:
                    continue
                
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                # Skip if it's just a generic header
                if len(lines) < 2: continue

                title = lines[0] if lines[0].upper() != "VOLLEYBALL" else lines[1]
                details = " | ".join(lines[1:5])

                if href and "/event/" in href:
                    if not any(g['link'] == href for g in games):
                        games.append({"title": title, "details": details, "link": href})
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
    print(f"🔎 Final Count: {len(current_games)} games.")
    
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
        print("😴 Nothing new.")

if __name__ == "__main__":
    main()
