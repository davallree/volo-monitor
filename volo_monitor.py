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
        message = (
            f"🏐 {game['title']}\n"
            f"📅 {game['details']}\n"
            f"🔗 https://www.volosports.com{game['link']}"
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
    fingerprint = f"{game['link']}-{game['details']}"
    return hashlib.md5(fingerprint.encode()).hexdigest()

def scrape_volo():
    games = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 1200},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        # DEBUG: Print browser console logs to GitHub logs
        page.on("console", lambda msg: print(f"BROWSER LOG: {msg.text}"))

        print(f"🚀 Navigating to: {VOLO_URL}")
        page.goto(VOLO_URL, wait_until="networkidle", timeout=60000)
        
        # Wait longer for the dynamic React content
        print("⏳ Waiting 15s for dynamic content...")
        page.wait_for_timeout(15000)

        # BROAD SEARCH: Find every link on the page to see what's there
        all_links = page.query_selector_all('a')
        print(f"📊 Total links found on page: {len(all_links)}")

        # Look for event links specifically
        event_links = [l for l in all_links if "/event/" in (l.get_attribute('href') or "")]
        print(f"🎯 Event-style links found: {len(event_links)}")

        if len(event_links) == 0:
            print("📸 NO EVENTS FOUND. Taking debug screenshot...")
            page.screenshot(path="debug_view.png", full_page=True)
            with open("debug_page.html", "w", encoding="utf-8") as f:
                f.write(page.content())
            print("💾 Debug files saved (debug_view.png and debug_page.html)")

        for link_el in event_links:
            try:
                href = link_el.get_attribute('href')
                # Walk up to find the card container
                container = link_el.evaluate_handle("el => el.closest('div[style*=\"flex-direction: column\"]') || el.parentElement.parentElement").as_element()
                
                if container:
                    text = container.inner_text()
                    if "volleyball" in text.lower():
                        lines = [l.strip() for l in text.split('\n') if l.strip()]
                        title = lines[1] if (len(lines) > 1 and lines[0].upper() == "VOLLEYBALL") else lines[0]
                        details = " | ".join(lines[1:5])
                        
                        if not any(g['link'] == href for g in games):
                            games.append({"title": title, "details": details, "link": href})
            except Exception as e:
                continue
                
        browser.close()
    return games

def main():
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'w') as f: json.dump([], f)
    
    with open(CACHE_FILE, 'r') as f:
        known_ids = json.load(f)
    
    current_games = scrape_volo()
    print(f"🔎 Final Count: {len(current_games)} volleyball listings.")
    
    new_found = False
    for game in current_games:
        gid = get_game_id(game)
        if gid not in known_ids:
            send_notification(game)
            known_ids.append(gid)
            new_found = True
            
    if new_found:
        with open(CACHE_FILE, 'w') as f: json.dump(known_ids, f)
        print("✅ Success: Updated memory.")
    else:
        print("😴 No new items to report.")

if __name__ == "__main__":
    main()
