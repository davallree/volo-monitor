import os
import json
import hashlib
import requests
import time
import random
from seleniumbase import Driver

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
    
    # UC (Undetected-Chromedriver) mode is the non-legit way to bypass Cloudflare
    print("🚀 Launching Undetected Driver...")
    driver = Driver(uc=True, headless=True)
    
    try:
        driver.get(TARGET_URL)
        
        # Human-like interaction: Scroll down slowly to trigger lazy loading
        print("🖱️ Simulating human scroll...")
        for _ in range(3):
            driver.execute_script("window.scrollBy(0, 400);")
            time.sleep(2)
        
        # Wait for the specific card element to appear
        driver.wait_for_element('div[class*="ProgramCard"]', timeout=20)
        
        elements = driver.find_elements("css selector", 'div[class*="ProgramCard"]')
        print(f"📡 Found {len(elements)} items!")

        for el in elements:
            try:
                # Use JS to get text to avoid 'element not visible' issues
                text = driver.execute_script("return arguments[0].innerText;", el)
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                
                title = lines[0]
                details = lines[1] if len(lines) > 1 else "Various Dates"
                
                link_el = el.find_element("css selector", "a")
                href = link_el.get_attribute("href")
                slug = href.split('/')[-1]

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
        driver.quit()

    return games

def main():
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'w') as f: json.dump([], f)
    
    with open(CACHE_FILE, 'r') as f:
        known_ids = json.load(f)
    
    current_games = scrape_volo()
    print(f"🔎 Final Count: {len(current_games)} items.")
    
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
        print("✅ Cache updated.")
    else:
        print("😴 No new updates.")

if __name__ == "__main__":
    main()
