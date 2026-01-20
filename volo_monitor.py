import os
import json
import hashlib
import requests
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

# --- CONFIGURATION ---
# Prefer env var in Actions; fall back to your current topic.
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "davallree-sf-volleyball-alerts")
CACHE_FILE = os.getenv("CACHE_FILE", "known_games.json")

# IMPORTANT: the HAR shows the working endpoint is on volosports.com (no www)
API_URL = "https://volosports.com/hapi/v1/graphql"

DISCOVER_URL = (
    "https://www.volosports.com/discover?cityName=San%20Francisco&sportNames%5B0%5D=Volleyball"
)

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
    # GraphQL payloads from DiscoverDaily use game_id / league_id / _id
    uid = item.get('game_id') or item.get('league_id') or item.get('_id')
    if not uid:
        fingerprint = f"{item.get('event_start_date')}-{item.get('event_start_time_str')}"
        return hashlib.md5(fingerprint.encode()).hexdigest()
    return str(uid)

def fetch_graphql_data():
    # Minimal but realistic headers; do not replay HTTP/2 pseudo-headers.
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://www.volosports.com",
        "Referer": "https://www.volosports.com/",
        "User-Agent": os.getenv(
            "VOLO_USER_AGENT",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ),
        "Accept": "*/*",
    }

    # Optional: merge in headers exported from HAR (VOLO_SESSION_HEADERS)
    # This can help on some networks, but is not required per the captured HAR.
    raw = os.getenv("VOLO_SESSION_HEADERS")
    if raw:
        try:
            extra = json.loads(raw)
            # Strip invalid keys (requests rejects some / they cause weird behavior)
            for k, v in list(extra.items()):
                if k.startswith(":"):
                    extra.pop(k, None)
            # Avoid clobbering our known-good basics
            for k in ("content-length", "host"):
                extra.pop(k, None)
            headers.update(extra)
        except Exception:
            pass

    # Compute time windows like the browser does.
    # League filter starts from "yesterday at local midnight" (SF midnight = 08:00Z in winter).
    sf = ZoneInfo("America/Los_Angeles")
    now_utc = datetime.now(timezone.utc)
    sf_today_midnight = datetime.now(sf).replace(hour=0, minute=0, second=0, microsecond=0)
    sf_yesterday_midnight_utc = (sf_today_midnight - timedelta(days=1)).astimezone(timezone.utc)

    def iso_z(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    where = {
        "_or": [
            {
                "league_id": {"_is_null": False},
                "league": {
                    "organizationByOrganization": {"name": {"_eq": "San Francisco"}},
                    "sportBySport": {"name": {"_in": ["Volleyball"]}},
                    "start_date": {"_gte": iso_z(sf_yesterday_midnight_utc)},
                    "program_type": {"_in": ["PICKUP", "PRACTICE", "CLINIC"]},
                    "status": {"_eq": "registration_open"},
                    "registrationByRegistration": {
                        "available_spots": {"_gte": 1},
                        "registration_close_date": {"_gte": "now()"},
                    },
                },
            },
            {
                "game_id": {"_is_null": False},
                "game": {
                    "start_time": {"_gte": iso_z(now_utc)},
                    "drop_in_capacity": {},
                    "leagueByLeague": {
                        "organizationByOrganization": {"name": {"_eq": "San Francisco"}},
                        "sportBySport": {"name": {"_in": ["Volleyball"]}},
                    },
                },
            },
        ]
    }

    query_body = {
        "operationName": "DiscoverDaily",
        "variables": {"limit": 15, "offset": 0, "where": where},
        "query": """
query DiscoverDaily($where: discover_daily_bool_exp!, $limit: Int = 15, $offset: Int = 0) {
  discover_daily(
    where: $where
    order_by: [{event_start_date: asc}, {event_start_time_str: asc}, {event_end_time_str: asc}, {_id: asc}]
    limit: $limit
    offset: $offset
  ) {
    _id
    game_id
    game {
      start_time
      end_time
      venueByVenue { shorthand_name formatted_address }
      drop_in_capacity { total_available_spots }
      leagueByLeague { program_type sportBySport { name } }
    }
    league_id
    league {
      name
      display_name
      program_type
      start_date
      venueByVenue { shorthand_name formatted_address }
      sportBySport { name }
    }
    event_start_date
    event_start_time_str
    event_end_time_str
  }
  discover_daily_aggregate(where: $where) { aggregate { count } }
}
        """,
    }
    try:
        response = requests.post(API_URL, headers=headers, json=query_body, timeout=20)
        if response.status_code == 200:
            payload = response.json()
            items = payload.get("data", {}).get("discover_daily", [])
            return "SUCCESS", items
        return ("BLOCKED" if response.status_code in [403, 429] else "ERROR"), response.status_code
    except Exception as e:
        return "ERROR", str(e)

def main():
    if not os.path.exists(CACHE_FILE):
        known_ids = []
    else:
        with open(CACHE_FILE, 'r') as f:
            try:
                known_ids = json.load(f)
            except:
                known_ids = []

    status, result = fetch_graphql_data()

    if status == "BLOCKED":
        send_ntfy(f"Monitor blocked (Status {result})", title="⚠️ Volo Blocked", priority="high", tags="warning")
        return

    if status == "SUCCESS":
        new_games = []
        for item in result:
            gid = get_game_id(item)
            if gid not in known_ids:
                # Normalize into human-friendly fields.
                if item.get("game"):
                    g = item["game"] or {}
                    venue = (g.get("venueByVenue") or {})
                    sport = (((g.get("leagueByLeague") or {}).get("sportBySport") or {}).get("name")) or "Volleyball"
                    spots = ((g.get("drop_in_capacity") or {}).get("total_available_spots"))
                    start = g.get("start_time")
                    title = f"{sport} (Drop-in)"
                else:
                    l = item.get("league") or {}
                    venue = (l.get("venueByVenue") or {})
                    sport = ((l.get("sportBySport") or {}).get("name")) or "Volleyball"
                    spots = None
                    start = l.get("start_date")
                    title = l.get("display_name") or l.get("name") or f"{sport} League"

                link = DISCOVER_URL
                location = venue.get("shorthand_name") or "(location unknown)"
                address = venue.get("formatted_address")
                when = start or f"{item.get('event_start_date')} {item.get('event_start_time_str')}"

                msg = f"🏐 {title}\n🕒 {when}\n📍 {location}\n👥 Spots: {spots if spots is not None else 'see listing'}"
                if address:
                    msg += f"\n🗺️ {address}"
                msg += f"\n🔗 {link}\nID: {gid}"
                send_ntfy(msg, title="New Volo Volleyball!")
                known_ids.append(gid)
                new_games.append(gid)
        
        if new_games:
            with open(CACHE_FILE, 'w') as f:
                json.dump(known_ids, f)
            print(f"✅ Notified for {len(new_games)} new games.")
        else:
            print("🔎 0 new games found (checking against cache).")

if __name__ == "__main__":
    main()
