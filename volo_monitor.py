import os
import json
import hashlib
import requests
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

# ---------------- CONFIG ----------------

NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")
CACHE_FILE = "known_games.json"

API_URL = "https://volosports.com/hapi/v1/graphql"

DISCOVER_URL = (
    "https://www.volosports.com/discover"
    "?cityName=San%20Francisco&sportNames%5B0%5D=Volleyball"
)

# ---------------- NTfy ----------------

def send_ntfy(message, title="Volo Monitor", priority="default", tags="volleyball"):
    try:
        r = requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": priority, "Tags": tags},
            timeout=10,
        )
        print(f" ntfy status: {r.status_code}")
        if r.status_code >= 400:
            print(f" ntfy error body: {r.text[:200]}")
    except Exception as e:
        print(f"ntfy exception: {e}")

# ---------------- HELPERS ----------------

def get_game_id(item):
    uid = item.get("game_id") or item.get("league_id") or item.get("_id")
    if uid:
        return str(uid)
    fingerprint = f"{item.get('event_start_date')}-{item.get('event_start_time_str')}"
    return hashlib.md5(fingerprint.encode()).hexdigest()

def iso_z(dt: datetime) -> str:
    return (
        dt.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )

# ---------------- GRAPHQL ----------------

def fetch_graphql_data():
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://www.volosports.com",
        "Referer": "https://www.volosports.com/",
        "User-Agent": os.getenv(
            "VOLO_USER_AGENT",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36",
        ),
        "Accept": "*/*",
    }

    raw = os.getenv("VOLO_SESSION_HEADERS")
    if raw:
        try:
            extra = json.loads(raw)
            for k in list(extra.keys()):
                if k.startswith(":") or k.lower() in ("content-length", "host"):
                    extra.pop(k, None)
            headers.update(extra)
        except Exception as e:
            print(f" Failed to parse VOLO_SESSION_HEADERS: {e}")

    sf = ZoneInfo("America/Los_Angeles")
    now_utc = datetime.now(timezone.utc)

    sf_today_midnight = datetime.now(sf).replace(hour=0, minute=0, second=0, microsecond=0)
    sf_yesterday_midnight_utc = (sf_today_midnight - timedelta(days=1)).astimezone(timezone.utc)

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
                    "leagueByLeague": {
                        "organizationByOrganization": {"name": {"_eq": "San Francisco"}},
                        "sportBySport": {"name": {"_in": ["Volleyball"]}},
                    },
                },
            },
        ]
    }

    payload = {
        "operationName": "DiscoverDaily",
        "variables": {"limit": 15, "offset": 0, "where": where},
        "query": """
query DiscoverDaily($where: discover_daily_bool_exp!, $limit: Int, $offset: Int) {
  discover_daily(
    where: $where
    order_by: [{event_start_date: asc}, {event_start_time_str: asc}, {_id: asc}]
    limit: $limit
    offset: $offset
  ) {
    _id
    game_id
    league_id
    event_start_date
    event_start_time_str
    event_end_time_str
    game {
      start_time
      end_time
      venueByVenue { shorthand_name formatted_address }
      drop_in_capacity { total_available_spots }
      leagueByLeague { sportBySport { name } }
    }
    league {
      name
      display_name
      start_date
      venueByVenue { shorthand_name formatted_address }
      sportBySport { name }
    }
  }
}
""",
    }

    try:
        r = requests.post(API_URL, headers=headers, json=payload, timeout=25)
        if r.status_code == 200:
            data = r.json().get("data", {}).get("discover_daily", [])
            return "SUCCESS", data
        if r.status_code in (403, 429):
            return "BLOCKED", r.status_code
        return "ERROR", f"{r.status_code}: {r.text[:200]}"
    except Exception as e:
        return "ERROR", str(e)

# ---------------- MAIN ----------------

def main():
    if not NTFY_TOPIC:
        print("NTFY_TOPIC not set")
        raise SystemExit(2)

    # Load cache
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                known_ids = set(json.load(f) or [])
        except Exception:
            known_ids = set()
    else:
        known_ids = set()

    seen_before = len(known_ids)

    status, result = fetch_graphql_data()

    if status == "BLOCKED":
        send_ntfy(
            f"Volo blocked this run ({result})\n{DISCOVER_URL}",
            title="Volo Blocked",
            priority="high",
            tags="warning",
        )
        return

    if status != "SUCCESS":
        send_ntfy(
            f"Volo error:\n{result}",
            title="Volo Error",
            priority="high",
            tags="warning",
        )
        print(f"Error: {result}")
        raise SystemExit(1)

    new_count = 0

    for item in result:
        gid = get_game_id(item)
        if gid in known_ids:
            continue

        if item.get("game"):
            g = item["game"] or {}
            venue = g.get("venueByVenue") or {}
            title = "Volleyball (Drop-in)"
            when = g.get("start_time")
            spots = (g.get("drop_in_capacity") or {}).get("total_available_spots")
        else:
            l = item.get("league") or {}
            venue = l.get("venueByVenue") or {}
            title = l.get("display_name") or l.get("name") or "Volleyball League"
            when = l.get("start_date")
            spots = None

        msg = (
            f"{title}\n"
            f"{when}\n"
            f"{venue.get('shorthand_name', 'Unknown location')}\n"
            f"Spots: {spots if spots is not None else 'See listing'}\n"
            f"{DISCOVER_URL}\n"
            f"ID: {gid}"
        )

        send_ntfy(msg, title="New Volo Volleyball!")
        known_ids.add(gid)
        new_count += 1

    # Always write cache
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(known_ids), f)

    print(f"Fetched {len(result)} items")
    print(f"Cache had {seen_before}, now {len(known_ids)} (added {new_count})")

if __name__ == "__main__":
    main()
