import os
import json
from typing import Optional, get_args

from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security import APIKeyHeader
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, model_validator
from dotenv import load_dotenv

from schemas.youtube_attributes import genreSchema, moodSchema, instrumentSchema, licenseTypeSchema
from utils.track_downloader import get_download_url_for_track, stream_track_from_url
from utils.playlist_scraper import get_all_tracks as get_all_tracks_from_youtube

load_dotenv()


API_KEY = os.getenv("API_KEY")
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(api_key: str = Security(api_key_header)):
    """Dependency function to validate the API key."""
    if api_key == API_KEY:
        return api_key
    else:
        raise HTTPException(
            status_code=403, detail="Could not validate credentials"
        )

attributes = {
    "genres": get_args(genreSchema),
    "moods": get_args(moodSchema),
    "instruments": get_args(instrumentSchema)
}

app = FastAPI(
    title="YouTube Creator Music API",
    description="A custom microservice to filter and download royalty-free music."
)

class Attribute(BaseModel):
    genre: Optional[str] = None
    mood: Optional[str] = None
    instrument: Optional[str] = None
    @model_validator(mode="after")
    def validate_attributes(self):
        if self.genre is not None and self.genre not in attributes["genres"]:
            raise ValueError(f"Invalid genre: {self.genre}")
        if self.mood is not None and self.mood not in attributes["moods"]:
            raise ValueError(f"Invalid mood: {self.mood}")
        if self.instrument is not None and self.instrument not in attributes["instruments"]:
            raise ValueError(f"Invalid instrument: {self.instrument}")
        return self

class TrackSearchRequest(BaseModel):
    attributes: Attribute
    license_type: Optional[licenseTypeSchema] = 'CREATOR_MUSIC_LICENSE_TYPE_CCBY_4'
    use_or_logic: Optional[bool] = False

def load_tracks_from_db():
    """Helper function to load our track data."""
    global attributes
    try:
        if not os.path.exists("youtube_studio_tracks.json"):
            result = get_all_tracks_from_youtube()
            attributes = result.get("available_attributes", {})
        with open("youtube_studio_tracks.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("tracks", [])
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Track database file not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading track database: {e}")



# 2. Define a "route" or "endpoint" for the main URL ("/")
@app.get("/")
def read_root():
    """
    This function runs when someone visits the main page.
    """
    return {"message": "Hello from your YouTube Music Service API!"}

@app.get("/attributes")
def get_available_attributes():
    """
    Returns a list of all unique, available values for genres,
    moods, and instruments to be used in search filters.
    """
    return attributes

@app.post("/tracks/refresh", dependencies=[Depends(get_api_key)])
def refresh_track_database():
    """
    Triggers a full re-scrape of all tracks from YouTube Studio
    and overwrites the local JSON database file.
    This can take a few minutes to complete.
    """
    global attributes
    print("Force refresh of track database initiated...")
    try:
        result = get_all_tracks_from_youtube()
        attributes = result.get("available_attributes", {})
        
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        print("Track database refresh completed successfully.")
        return {"status": "success", "message": f"Successfully scraped and saved {result.get('count', 0)} tracks."}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during refresh: {e}")


@app.get("/tracks/all", dependencies=[Depends(get_api_key)])
def get_all_tracks():
    """
    Returns the entire list of tracks without any filtering.
    """
    return load_tracks_from_db()


@app.post("/tracks/search", dependencies=[Depends(get_api_key)])
def search_tracks(request: TrackSearchRequest):
    """
    Searches for tracks based on license, genres, moods, and instruments.
    """
    all_tracks = load_tracks_from_db()
    filtered_tracks = []

    if request.license_type:
        tracks_to_search = [
            track for track in all_tracks 
            if track.get("licenseType", "") == request.license_type
        ]
    else:
        tracks_to_search = all_tracks
    if not request.attributes:
        return tracks_to_search

    filtered_tracks = []
    for track in tracks_to_search:
        # Get the track's attributes, with empty lists as a fallback
        track_genres = track.get("attributes", {}).get("genres", [])
        track_moods = track.get("attributes", {}).get("moods", [])
        track_instruments = track.get("attributes", {}).get("instruments", [])

        # Build a list of conditions that must be met
        conditions = []
        if request.attributes.genre is not None:
            conditions.append(request.attributes.genre in track_genres)
        if request.attributes.mood is not None:
            conditions.append(request.attributes.mood in track_moods)
        if request.attributes.instrument is not None:
            conditions.append(request.attributes.instrument in track_instruments)

        if not conditions:
            continue

        if request.use_or_logic:
            if any(conditions):
                filtered_tracks.append(track)
        else:
            if all(conditions):
                filtered_tracks.append(track)
                
    return filtered_tracks


@app.get("/tracks/{track_id}/download", dependencies=[Depends(get_api_key)])
def download_track(track_id: str):
    """
    Takes a track_id, gets the temporary download URL, and streams
    the audio file back to the client.
    """
    print(f"Received download request for track_id: {track_id}")

    track_info = get_download_url_for_track([track_id])

    # 2. Handle any errors from the utility function
    if "error" in track_info:
        status_code = track_info.get("status_code", 500)
        raise HTTPException(status_code=status_code, detail=track_info["error"])

    if track_id not in track_info:
        raise HTTPException(status_code=404, detail=f"Track ID {track_id} not found or no URL returned.")

    filename, download_url = track_info[track_id]

    file_extension = "mp3" # Default to mp3
    if ".wav" in download_url:
        file_extension = "wav"

    return StreamingResponse(
        stream_track_from_url(download_url),
        media_type="audio/mpeg",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}.{file_extension}\""}
    )
    
