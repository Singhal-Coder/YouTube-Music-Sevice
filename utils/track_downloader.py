import requests
import time
import re
import json

from urllib.parse import urlparse, parse_qs
import os
from dotenv import load_dotenv
load_dotenv()

# ====== Endpoints ======
CHANNEL_ID = os.getenv("CHANNEL_ID")
GET_TRACKS_URL = "https://studio.youtube.com/youtubei/v1/creator_music/get_tracks?alt=json"
REQUEST_TIMEOUT = 30
CLIENT_SCREEN_NONCE = str(int(time.time()))


def get_studio_headers(cfg: dict):
    return {
        # Standard headers
        "accept": "*/*",
        "accept-language": "en-GB,en-US;q=0.9,en;q=0.8,hi;q=0.7",

        # auth + cookies (variables above)
        "authorization": cfg['authorization'],
        "cookie": cfg['cookie'],

        "cache-control": "no-cache",
        # do NOT set content-length manually when using requests; requests will calculate it.
        "content-type": "application/json",

        "origin": "https://studio.youtube.com",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "referer": f"https://studio.youtube.com/channel/{CHANNEL_ID}/music",

        # client hints / UA information (as captured)
        "sec-ch-ua": cfg['sec-ch-ua'],
        "sec-ch-ua-arch": cfg['sec-ch-ua-arch'],
        "sec-ch-ua-bitness": cfg['sec-ch-ua-bitness'],
        "sec-ch-ua-form-factors": cfg['sec-ch-ua-form-factors'],
        "sec-ch-ua-full-version": cfg['sec-ch-ua-full-version'],
        "sec-ch-ua-full-version-list": cfg['sec-ch-ua-full-version-list'],
        "sec-ch-ua-mobile": cfg['sec-ch-ua-mobile'],
        "sec-ch-ua-model": cfg['sec-ch-ua-model'],
        "sec-ch-ua-platform": cfg['sec-ch-ua-platform'],
        "sec-ch-ua-platform-version": cfg['sec-ch-ua-platform-version'],
        "sec-ch-ua-wow64": cfg['sec-ch-ua-wow64'],

        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",

        "user-agent": cfg['user-agent'],

        # other x- headers (use the variables above where applicable)
        "x-browser-channel": "stable",
        "x-browser-copyright": "Copyright 2025 Google LLC. All rights reserved.",
        "x-browser-year": "2025",
        "x-goog-authuser": cfg['x-goog-authuser'],
        "x-goog-visitor-id": cfg['x-goog-visitor-id'],
        "x-origin": "https://studio.youtube.com",

        # YouTube specific signals & client info
        "x-youtube-ad-signals": cfg['x-youtube-ad-signals'],
        "x-youtube-client-name": cfg['x-youtube-client-name'],
        "x-youtube-client-version": cfg['x-youtube-client-version'],
        "x-youtube-delegation-context": cfg['x-youtube-delegation-context'],
        "x-youtube-page-cl": cfg['x-youtube-page-cl'],
        "x-youtube-page-label": cfg['x-youtube-page-label'],
        "x-youtube-time-zone": cfg['x-youtube-time-zone'],
        "x-youtube-utc-offset": cfg['x-youtube-utc-offset'],
    }

def get_studio_payload(cfg: dict, track_ids: list[str]):
    return {
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
                "screenHeightPoints": 643,
                "screenPixelDensity": 2,
                "screenDensityFloat": 2
            },
            "request": {
                "returnLogEntry": True,
                "internalExperimentFlags": [],
                "eats": cfg['EATS'],
                "sessionInfo": {"token": cfg['SESSION_TOKEN']},
                "consistencyTokenJars": cfg['CONSISTENCY_TOKEN_JARS']
            },
            "user": {
                "delegationContext": {
                    "externalChannelId": CHANNEL_ID,
                    "roleType": {"channelRoleType": "CREATOR_CHANNEL_ROLE_TYPE_OWNER"}
                },
                "serializedDelegationContext": cfg['x-youtube-delegation-context']
            },
            "clickTracking": {"visualElement": {"veType": 97615}},
            "clientScreenNonce": CLIENT_SCREEN_NONCE
        },
        "trackIds": track_ids,
        "channelId": CHANNEL_ID,
        "mask": {"includeDownloadUrl": True}
    }
    
def get_dl_headers(cfg: dict):
    return {
        "user-agent": cfg['user-agent'],
        "cookie": cfg['cookie'],
        "referer": f"https://studio.youtube.com/channel/{CHANNEL_ID}/music",
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

# ====== Helper: sanitize filename ======
def sanitize_filename(name: str):
    name = re.sub(r'[\\/:"*?<>|]+', "_", name) 
    name = re.sub(r'\s+', " ", name).strip()
    return name[:200] 

# ====== Function: ask Studio for download URL for a trackId ======
def get_download_url_for_track(track_ids: list[str], max_retries: int = 2):
    for _ in range(max_retries):
        cfg = load_cfg()
        studio_headers = get_studio_headers(cfg)
        payload = get_studio_payload(cfg, track_ids)
        resp = requests.post(GET_TRACKS_URL, headers=studio_headers, json=payload, timeout=REQUEST_TIMEOUT)
        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            if resp.status_code == 401 or resp.status_code == 403:
                print(f"{resp.status_code} Unauthorized — refreshing tokens...")
                import subprocess, sys
                subprocess.run([sys.executable, "utils/token_fetcher.py"], check=True)
                continue
            else:
                print("Error:", str(e))
                raise
        data = resp.json()
        tracks = data.get("tracks", [])
        if not tracks:
            raise RuntimeError("No track object returned in get_tracks response.")
        track_urls = {}
        for track_obj in tracks:
            dl_url = track_obj.get("downloadAudioUrl")
            dl_title = track_obj.get("title")
            if not dl_url:
                raise RuntimeError("downloadAudioUrl not present in response. Check permissions/tokens.")
            track_urls[track_obj.get("trackId")] = (dl_title, dl_url)
        return track_urls

def download_track_from_url(url: str, filename: str, chunk_size=8192, max_retries: int = 2):
    for _ in range(max_retries):
        cfg = load_cfg()
        dl_headers = get_dl_headers(cfg)
        with requests.get(url, headers=dl_headers, stream=True, timeout=REQUEST_TIMEOUT) as r:
            try:
                r.raise_for_status()
            except requests.HTTPError as e:
                if r.status_code == 401 or r.status_code == 403:
                    print(f"{r.status_code} Unauthorized — refreshing tokens...")
                    import subprocess, sys
                    subprocess.run([sys.executable, "utils/token_fetcher.py"], check=True)
                    continue
                else:
                    print("Error:", str(e))
                    raise
            ext = None
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            if "ext" in qs:
                ext = qs["ext"][0]
            else:
                # fallback to Content-Type header
                ctype = r.headers.get("Content-Type", "")
                if "mpeg" in ctype or "mp3" in ctype:
                    ext = "mp3"
                elif "wav" in ctype:
                    ext = "wav"
            if not ext:
                ext = "bin"
            out_path = f"{filename}.{ext}"

            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
        return out_path

def stream_track_from_url(url: str, chunk_size=8192, max_retries: int = 2):
    for _ in range(max_retries):
        cfg = load_cfg()
        dl_headers = get_dl_headers(cfg)
        with requests.get(url, headers=dl_headers, stream=True, timeout=REQUEST_TIMEOUT) as r:
            try:
                r.raise_for_status()
            except requests.HTTPError as e:
                if r.status_code == 401 or r.status_code == 403:
                    print(f"{r.status_code} Unauthorized — refreshing tokens...")
                    import subprocess, sys
                    subprocess.run([sys.executable, "utils/token_fetcher.py"], check=True)
                    continue
                else:
                    print("Error:", str(e))
                    raise
            
            for chunk in r.iter_content(chunk_size=chunk_size):
                if chunk:
                    yield chunk
        break
# ====== Example usage: download a single track by id ======
if __name__ == "__main__":
    json_data = json.load(open("youtube_studio_tracks.json", "r", encoding="utf-8"))
    json_data = json_data['tracks']
    track_ids_to_download = [track['trackId'] for track in json_data]
    import random
    track_ids_to_download = random.sample(track_ids_to_download, 1)
    try:
        track_urls = get_download_url_for_track(track_ids_to_download)
        for title, dl_url in track_urls.values():
            print("Got download URL (length):", len(dl_url))
            fname = sanitize_filename(title)
            saved = download_track_from_url(dl_url, fname)
            print("Saved file:", saved)
        
    except Exception as e:
        print("Error:", str(e))