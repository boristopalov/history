"""Spotify listening on any device, from the Web API.

`recently-played` only reaches back 50 tracks, so this captures listening from now on as long
as the daemon runs often enough. Setup is in the README: it needs a free app registration,
and Spotify requires the owner of a development-mode app to have Premium.
"""

import base64
import hashlib
import http.server
import secrets
import urllib.parse
import webbrowser
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import httpx

from history import credentials
from history.collectors.base import Collector
from history.models import Batch, Event

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
RECENTLY_PLAYED_URL = "https://api.spotify.com/v1/me/player/recently-played"
SCOPE = "user-read-recently-played"
# Spotify rejects `localhost`; it must be this exact loopback address.
REDIRECT_URI = "http://127.0.0.1:8888/callback"
CREDENTIALS = "spotify"


def _played_at(item: dict) -> float:
    return datetime.fromisoformat(item["played_at"]).timestamp()


def _to_event(item: dict) -> Event:
    track = item["track"]
    artists = ", ".join(artist["name"] for artist in track["artists"])
    context = item.get("context") or {}
    return Event(
        source="music",
        source_id=f"spotify:{item['played_at']}",
        ts=_played_at(item),
        title=f"{track['name']} — {artists}",
        url=track.get("external_urls", {}).get("spotify"),
        data={
            "player": "Spotify",
            "album": track.get("album", {}).get("name"),
            "track_id": track.get("id"),
            "duration_ms": track.get("duration_ms"),
            "context": context.get("uri"),
        },
    )


def _access_token(http: httpx.Client, client_id: str, directory: Path) -> str | None:
    stored = credentials.load(directory, CREDENTIALS)
    if stored is None:
        return None
    response = http.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": stored["refresh_token"],
            "client_id": client_id,
        },
    )
    tokens = response.raise_for_status().json()
    if "refresh_token" in tokens:  # only sometimes rotated
        credentials.save(directory, CREDENTIALS, {"refresh_token": tokens["refresh_token"]})
    return tokens["access_token"]


def _batches(
    http: httpx.Client, client_id: str, directory: Path, cursor: str | None
) -> Iterator[Batch]:
    token = _access_token(http, client_id, directory)
    if token is None:
        return
    params = {"limit": 50} | ({"after": cursor} if cursor else {})
    response = http.get(
        RECENTLY_PLAYED_URL, params=params, headers={"Authorization": f"Bearer {token}"}
    )
    items = response.raise_for_status().json()["items"]
    if items:
        newest_ms = max(int(_played_at(item) * 1000) for item in items)
        yield Batch(
            collector="spotify",
            cursor=str(newest_ms),
            events=[_to_event(item) for item in items],
        )


def spotify_collector(
    client_id: str | None, directory: Path, http: httpx.Client | None = None
) -> Collector:
    def collect(cursor: str | None) -> Iterator[Batch]:
        if client_id is None:
            return
        if http is not None:
            yield from _batches(http, client_id, directory, cursor)
            return
        with httpx.Client(timeout=30) as client:
            yield from _batches(client, client_id, directory, cursor)

    return Collector(name="spotify", source="music", collect=collect)


def _wait_for_redirect() -> dict[str, str]:
    received: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            query = urllib.parse.urlparse(self.path).query
            received.update(dict(urllib.parse.parse_qsl(query)))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Done. You can close this tab.")

        def log_message(self, *args) -> None:
            pass

    port = urllib.parse.urlparse(REDIRECT_URI).port
    with http.server.HTTPServer(("127.0.0.1", port), Handler) as server:
        while "code" not in received and "error" not in received:
            server.handle_request()
    return received


def login(client_id: str, directory: Path) -> None:
    """Runs the one-time PKCE browser flow and stores the refresh token."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    state = secrets.token_urlsafe(16)
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPE,
            "state": state,
            "code_challenge_method": "S256",
            "code_challenge": base64.urlsafe_b64encode(digest).rstrip(b"=").decode(),
        }
    )
    url = f"{AUTHORIZE_URL}?{query}"
    print(f"Opening {url}")
    webbrowser.open(url)
    reply = _wait_for_redirect()
    if "error" in reply or reply.get("state") != state:
        raise SystemExit(f"Spotify login failed: {reply.get('error', 'state mismatch')}")
    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": reply["code"],
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "code_verifier": verifier,
        },
    )
    refresh_token = response.raise_for_status().json()["refresh_token"]
    credentials.save(directory, CREDENTIALS, {"refresh_token": refresh_token})
    print("Spotify connected.")
