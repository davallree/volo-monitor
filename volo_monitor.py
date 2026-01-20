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

def get_free_proxies():
    """Scrapes a list of free HTTP proxies to bypass IP-based firewall blocks."""
    print("🌐 Fetching fresh proxy list...")
    try:
        response = requests.get("https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all")
        if response.status_code == 200:
            return response.text.strip().split("\r\n")
    except:
        return []
    return []

def scrape_volo():
    games = []
    proxies = get_free_proxies()
    random.shuffle(proxies)
    
    # We will try up to 5 different proxies if the first ones fail
    for proxy in proxies[:5]:
        print(f"🕵️ Attempting scrape with proxy: {proxy}")
        
        # UC Mode (Undetected) is key here to bypass Cloudflare
        driver = Driver(uc=True, headless=True, proxy=proxy)
        
        try:
            driver.get(TARGET_URL)
            # Human-like delay to wait for content and bypass timed challenges
            time.sleep(10) 
            
            # Use SeleniumBase's smart selectors to find the cards
            # Looking for any div that contains 'ProgramCard' in the class name
            elements = driver.find_elements("css selector", 'div[class*="ProgramCard"]')
            
            if not elements:
                print("⚠️ No listings found with this proxy. Rotating...")
                driver.quit()
                continue

            print(f"📡 Found {len(elements)} items!")
            for el in elements:
                try:
                    text = el.text
                    lines = text.split('\n')
                    title = lines[0]
                    # The second line usually contains the location/date info
                    details = lines[1] if len(lines) > 1 else "No details"
                    
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
            
            # If we found games, we are done
            driver.quit()
            break 
            
        except Exception as e:
            print(f"❌ Attempt failed: {e}")
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
        with open(CACHE_FILE, 'w') as f: json.dump(known_ids, f)
    else:
        print("😴 No new updates.")

if __name__ == "__main__":
    main()
