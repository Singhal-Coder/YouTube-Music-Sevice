import requests
import json
import time
import os
from dotenv import load_dotenv



load_dotenv()
# ===== Sensitive data in variables =====
CHANNEL_ID = os.getenv("CHANNEL_ID")
# ===== Request URL =====
CLIENT_SCREEN_NONCE = str(int(time.time()))
URL = "https://studio.youtube.com/youtubei/v1/creator_music/list_tracks?alt=json"

# ===== Headers =====
def get_headers(cfg: dict):
    return {
        "authority": "studio.youtube.com",
        "accept": "*/*",
        "accept-language": "en-GB,en-US;q=0.9,en;q=0.8,hi;q=0.7",
        "authorization": cfg['authorization'],
        "cache-control": "no-cache",
        "content-type": "application/json",
        "cookie": cfg['cookie'],
        "origin": "https://studio.youtube.com",
        "pragma": "no-cache",
        "referer": f"https://studio.youtube.com/channel/{CHANNEL_ID}/music",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": cfg['user-agent'],
        "x-goog-authuser": cfg['x-goog-authuser'],
        "x-goog-visitor-id": cfg['x-goog-visitor-id'],
        "x-origin": "https://studio.youtube.com",
        "x-youtube-ad-signals": cfg['x-youtube-ad-signals'],
        "x-youtube-client-name": cfg['x-youtube-client-name'],
        "x-youtube-client-version": cfg['x-youtube-client-version'],
        "x-youtube-delegation-context": cfg['x-youtube-delegation-context'],
        "x-youtube-page-cl": cfg['x-youtube-page-cl'],
        "x-youtube-page-label": cfg['x-youtube-page-label'],
        "x-youtube-time-zone": cfg['x-youtube-time-zone'],
        "x-youtube-utc-offset": cfg['x-youtube-utc-offset']
    }
    # ===== Payload =====
def get_payload(cfg: dict):
    return {
        "channelId": CHANNEL_ID,
        "filter": {},
        "trackOrder": {
            "orderField": "CREATOR_MUSIC_TRACK_SORT_FIELD_RELEASE_DATE",
            "orderDirection": "ORDER_DIRECTION_DESC"
        },
        "pageInfo": {
            "pageSize": 100
        },
        "context": {
            "client": {
                "clientName": cfg['x-youtube-client-name'],
                "clientVersion": cfg['x-youtube-client-version'],
                "hl": "en-GB",
                "gl": "IN",
                "experimentsToken": "",
                "utcOffsetMinutes": cfg['x-youtube-utc-offset'],
                "rolloutToken": cfg['ROLLOUT_TOKEN'],
                "userInterfaceTheme": "USER_INTERFACE_THEME_DARK",
                "screenWidthPoints": 980,
                "screenHeightPoints": 810,
                "screenPixelDensity": 2,
                "screenDensityFloat": 2
            },
            "request": {
                "returnLogEntry": True,
                "internalExperimentFlags": [],
                "eats": cfg['EATS'],
                "sessionInfo": {
                    "token": cfg['SESSION_TOKEN']
                },
                "consistencyTokenJars": cfg['CONSISTENCY_TOKEN_JARS']
            },
            "user": {
                "delegationContext": {
                    "externalChannelId": CHANNEL_ID,
                    "roleType": {
                        "channelRoleType": "CREATOR_CHANNEL_ROLE_TYPE_OWNER"
                    }
                },
                "serializedDelegationContext": cfg['x-youtube-delegation-context']
            },
            "clickTracking": {
                "visualElement": {"veType": 97615}
            },
            "clientScreenNonce": CLIENT_SCREEN_NONCE
        }
    }

def load_cfg():
    if os.path.exists("config.json"):
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        print("config.json not found, running youtube_token_fetcher.py...")
        import subprocess, sys
        subprocess.run([sys.executable, "utils/token_fetcher.py"], check=True)
        return load_cfg()

def get_all_tracks():
    cfg = load_cfg()
    headers = get_headers(cfg)
    payload = get_payload(cfg)
    all_genres = set()
    all_moods = set()
    all_instruments = set()
    all_tracks = {}
    page = 1
    while True:
        print(f"Fetching page {page} ...")
        resp = requests.post(URL, headers=headers, json=payload, timeout=30)
        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            if resp.status_code == 401 or resp.status_code == 403:
                print(f"{resp.status_code} Unauthorized — refreshing tokens...")
                import subprocess, sys
                subprocess.run([sys.executable, "utils/token_fetcher.py"], check=True)
                cfg = load_cfg()
                headers = get_headers(cfg)
                payload = get_payload(cfg)
                continue
            else:
                print("HTTP error:", e, resp.status_code, resp.text[:400])
                break

        data = resp.json()
        tracks = data.get("tracks", [])
        if not tracks and "pageInfo" in data and data["pageInfo"].get("totalSizeInfo"):
            tracks = data.get("tracks", [])

        for t in tracks:
            all_genres.update(t.get("attributes", {}).get("genres", []))
            all_moods.update(t.get("attributes", {}).get("moods", []))
            all_instruments.update(t.get("attributes", {}).get("instruments", []))
            tid = t.get("trackId") or t.get("id")
            if tid:
                all_tracks[tid] = t

        # get next page token (matches your response: pageInfo.nextPageToken)
        next_token = data.get("pageInfo", {}).get("nextPageToken")
        if not next_token:
            print("No nextPageToken — done.")
            break

        # set token for next request inside pageInfo
        payload.setdefault("pageInfo", {})["pageToken"] = next_token
        page += 1
        time.sleep(0.8)  # polite delay

    print(f"Collected tracks: {len(all_tracks)}")

    output_file ="youtube_studio_tracks.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({"collected": len(all_tracks), "tracks": list(all_tracks.values())}, f, ensure_ascii=False, indent=2)

    print(f"Saved to {output_file}")
    return {
        "success": True, 
        "count": len(all_tracks),
        "available_attributes": {
            "genres": list(all_genres),
            "moods": list(all_moods),
            "instruments": list(all_instruments)
        }
    }


if __name__ == "__main__":
    print(get_all_tracks())