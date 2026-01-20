import os
import json
import hashlib
import requests
import time
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
NTFY_TOPIC = "davallree-sf-volleyball-alerts"
CACHE_FILE = "known_games.json"
TARGET_URL = "https://www.volosports.com/discover?cityName=San%20Francisco&sportNames%5B0%5D=Volleyball"

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
    games = []
    with sync_playwright() as p:
        print("🚀 Launching stealth browser...")
        browser = p.chromium.launch(headless=True)
        
        # Create context with a realistic user agent and window size
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        
        page = context.new_page()
        
        try:
            # Navigate and wait for the page to actually load content
            page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
            
            # Additional wait for React hydration
            page.wait_for_timeout(5000)
            
            # Scrape program cards based on the structure in your debug file
            # We target elements containing "ProgramCard" or similar listing structures
            cards = page.query_selector_all('div[class*="ProgramCard"], div[class*="listing"]')
            print(f"📡 Found {len(cards)} potential listings.")

            for card in cards:
                try:
                    title_el = card.query_selector('h3') or card.query_selector('div[class*="title"]')
                    link_el = card.query_selector('a')
                    
                    if title_el and link_el:
                        title = title_el.inner_text().strip()
                        href = link_el.get_attribute('href') or ""
                        slug = href.split('/')[-1]
                        
                        # Grab descriptive text (location/date)
                        full_text = card.inner_text()
                        details = full_text.replace(title, "").strip().split('\n')[0]
                        
                        games.append({
                            "title": title,
                            "details": details,
                            "slug": slug
                        })
                except:
                    continue

        except Exception as e:
            print(f"❌ Scrape failed: {e}")
        finally:
            browser.close()
            
    return games

def main():
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'w') as f: json.dump([], f)
    
    with open(CACHE_FILE, 'r') as f:
        known_ids = json.load(f)
    
    current_games = scrape_volo()
    print(f"🔎 Extracted {len(current_games)} items.")
    
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
        print("😴 No new updates.")

if __name__ == "__main__":
    main()
