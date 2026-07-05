# youtube_client_manager.py
# Manages multiple YouTube API keys with automatic rotation on quota exhaustion.

import os
import threading
import itertools
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()

# Load a list of keys from the env (comma-separated)
RAW = os.getenv("YOUTUBE_API_KEYS", "")
API_KEYS = [k.strip() for k in RAW.split(",") if k.strip()]

if not API_KEYS:
    raise RuntimeError("YOUTUBE_API_KEYS env var missing – add at least one key")

print(f"🔑 Loaded {len(API_KEYS)} YouTube API key(s)")

# Thread-safe round-robin iterator
_key_cycle = itertools.cycle(API_KEYS)
_lock = threading.Lock()


def _next_key():
    """Get the next key in rotation (thread-safe)."""
    with _lock:
        return next(_key_cycle)


def get_youtube_client():
    """
    Return a (youtube_service, api_key) tuple.
    Tries each key once — if a key hits quotaExceeded, rotates to the next.
    Raises RuntimeError if ALL keys are exhausted.
    """
    for _ in range(len(API_KEYS)):
        key = _next_key()
        youtube = build("youtube", "v3", developerKey=key)
        # Test a cheap call (1 unit) to verify the key still has quota
        try:
            youtube.channels().list(
                part="id", forUsername="GoogleDevelopers", maxResults=1
            ).execute()
            return youtube, key  # success
        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                print(f"⚠️  Key {key[:8]}… exhausted – switching to next key")
                continue  # try the next key
            raise  # other errors bubble up

    raise RuntimeError("All YouTube API keys exhausted for today")