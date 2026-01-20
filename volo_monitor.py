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
    """Creates a unique ID so we don't notify twice."""
    fingerprint = f"{game['link']}-{game['details']}"
    return hashlib.md5(fingerprint.encode()).hexdigest()

def scrape_volo():
    found_games = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Use a real browser size
        context = browser.new_context(viewport={'width': 1280, 'height': 1000})
        page = context.new_page()
        
        print("🚀 Opening Volo Discover...")
        page.goto(VOLO_URL, wait_until="networkidle")
        
        # Give React 15 seconds to fully load the cards and icons
        print("⏳ Waiting for cards to appear...")
        page.wait_for_timeout(15000)

        # FIND THE CARDS: In your HTML, every card has an <a> link containing "/event/"
        # We find those links and then look at the text around them.
        event_links = page.query_selector_all('a[href*="/event/"]')
        
        for link_el in event_links:
            try:
                href = link_el.get_attribute('href')
                
                # Move up the HTML tree to find the box containing the text and icons
                # Based on your HTML, 5 levels up gets the whole card
                container = link_el.evaluate_handle("el => el.closest('div[style*=\"flex-direction: column\"]')").as_element()
                
                if container:
                    # Check for the icons (SVGs) you mentioned
                    icons = container.query_selector_all('svg')
                    # A real game card must have icons (time, person, location)
                    if len(icons) < 1: continue
                    
                    raw_text = container.inner_text().strip()
                    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]

                    if len(lines) >= 2:
                        # Skip the generic "VOLLEYBALL" header if it's the first line
                        title = lines[1] if lines[0].upper() == "VOLLEYBALL" else lines[0]
                        # Capture the date, time, and location lines
                        details = " | ".join(lines[1:5])

                        # Verify this specific link hasn't been added in this run
                        if not any(g['link'] == href for g in found_games):
                            found_games.append({
                                "title": title,
                                "details": details,
                                "link": href
                            })
            except:
                continue
                
        browser.close()
    
    print(f"✨ Found {len(found_games)} volleyball listings.")
    return found_games

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
        print("✅ Success
