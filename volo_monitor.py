import os
import json
import hashlib
import requests
import sys
from datetime import datetime

# --- CONFIGURATION ---
NTFY_TOPIC = "davallree-sf-volleyball-alerts"
CACHE_FILE = "known_games.json"
API_URL = "https://www.volosports.com/hapi/v1/graphql"

def send_ntfy(message, title="Volo Monitor", priority="default", tags="volleyball"):
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode('utf-8'),
            headers={"Title": title, "Priority": priority, "Tags": tags},
            timeout=10
        )
    except Exception as e:
        print(f"❌ Failed to send ntfy: {e}")

def get_game_id(item):
    uid = item.get('id') or item.get('league_id') or item.get('_id')
    if not uid:
        fingerprint = f"{item.get('name')}-{item.get('start_time')}"
        return hashlib.md5(fingerprint.encode()).hexdigest()
    return str(uid)

def fetch_graphql_data():
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://www.volosports.com",
        "Referer": "https://www.volosports.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    query_body = {
        "operationName": "DiscoverDaily",
        "variables": {
            "where": {
                "organization": {"_eq": "San Francisco"},
                "sport": {"_eq": "Volleyball"},
                "status": {"_eq": "registration_open"},
                "available_spots": {"_gt": 0},
                "start_time": {"_gte": datetime.utcnow().isoformat()}
            }
        },
        "query": """
        query DiscoverDaily($where: discover_daily_bool_exp) {
          discover_daily(where: $where, order_by: {start_time: asc}) {
            id
            league_id
            name
            start_time
            location_name
            available_spots
            slug
          }
        }
        """
    }
    try:
        response = requests.post(API_URL, headers=headers, json=query_body, timeout=20)
        if response.status_code == 200:
            return "SUCCESS", response.json().get('data', {}).get('discover_daily', [])
        return ("BLOCKED" if response.status_code in [403, 429] else "ERROR"), response.status_code
    except Exception as e:
        return "ERROR", str(e)

def main():
    if not os.path.exists(CACHE_FILE):
        known_ids = []
    else:
        with open(CACHE_FILE, 'r') as f:
            known_ids = json.load(f)

    status, result = fetch_graphql_data()

    if status == "BLOCKED":
        send_ntfy(f"Monitor blocked (Status {result})", title="⚠️ Volo Blocked", priority="high", tags="warning")
        return

    if status == "SUCCESS":
        new_games = []
        for item in result:
            gid = get_game_id(item)
            if gid not in known_ids:
                link = f"https://www.volosports.com/event/{item['slug']}" if item.get('slug') else "https://www.volosports.com/discover"
                msg = f"🏐 {item['name']}\n📍 {item['location_name']}\n👥 Spots: {item['available_spots']}\n🔗 {link}"
                send_ntfy(msg, title="New Volo Volleyball!")
                known_ids.append(gid)
                new_games.append(gid)
        
        if new_games:
            with open(CACHE_FILE, 'w') as f:
                json.dump(known_ids, f)

if __name__ == "__main__":
    main()
