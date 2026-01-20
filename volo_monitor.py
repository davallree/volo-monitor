import os
import json
import hashlib
import requests
import time
from seleniumbase import SB

# --- CONFIGURATION ---
NTFY_TOPIC = "davallree-sf-volleyball-alerts"
CACHE_FILE = "known_games.json"
TARGET_URL = "https://www.volosports.com/discover?cityName=San%20Francisco&sportNames%5B0%5D=Volleyball"

def send_notification(game):
    """Sends a push notification via ntfy.sh"""
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
    """Creates a unique ID based on the slug and details."""
    fingerprint = f"{game['slug']}-{game['details']}"
    return hashlib.md5(fingerprint.encode()).hexdigest()

def scrape_volo():
    """Scrapes Volo using SeleniumBase CDP Mode for maximum stealth."""
    games = []
    
    # uc=True enables Undetected-Chromedriver
    # test=True helps with internal bypasses
    with SB(uc=True, incognito=True, test=True) as sb:
        try:
            print(f"🚀 Opening {TARGET_URL} in CDP Mode...")
            sb.activate_cdp_mode(TARGET_URL)
            
            # Handle potential Cloudflare Turnstile/Captcha challenges
            print("🛡️ Checking for bot challenges...")
            sb.sleep(5)
            sb.uc_gui_click_captcha() 
            
            # Allow time for React content to populate
            print("⌛ Waiting for page content...")
            sb.sleep(12)
            
            # Scroll slightly to trigger any lazy-loaded cards
            sb.execute_script("window.scrollBy(0, 800);")
            sb.sleep(2)

            # Broad selector: Look for cards or anything with 'program' in data/class
            elements = sb.find_elements('div[class*="ProgramCard"], [data-testid*="program"]')
            
            if not elements:
                print("⚠️ No listings found. Saving source for debugging...")
                with open("error_debug.html", "w", encoding="utf-8") as f:
                    f.write(sb.get_page_source())
                return []

            print(f"📡 Found {len(elements)} items!")

            for el in elements:
                try:
                    text = el.text
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    
                    if not lines: continue
                    
                    # Usually: [0] = Sport, [1] = Title, [2] = Location/Date
                    # Or: [0] = Title if 'Volleyball' is filtered out
                    title = lines[1] if lines[0].upper() == "VOLLEYBALL" and len(lines) > 1 else lines[0]
                    details = lines[2] if len(lines) > 2 else (lines[1] if len(lines) > 1 else "Details on site")
                    
                    link_el = el.find_element("css selector", "a")
                    href = link_el.get_attribute("href")
                    slug = href.split('/')[-1] if href else "unknown"

                    games.append({
                        "title": title,
                        "details": details,
                        "slug": slug
                    })
                except:
                    continue
                    
        except Exception as e:
            print(f"❌ Scrape failed: {e}")
            
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
