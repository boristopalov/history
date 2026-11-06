"""What's playing right now in Spotify or Apple Music, sampled on each run.

macOS keeps no usable play history: knowledgeC's now-playing stream has no track titles.
So history starts when the daemon starts, and tracks shorter than the interval can be
missed. The first run asks for Automation permission for each player.
"""

import subprocess
import time
from collections.abc import Callable, Iterator

from history.collectors.base import Collector, full_scan
from history.models import Event

SEPARATOR = "\x1f"

# `is running` is checked first because addressing a closed app would launch it.
SCRIPT = """
set AppleScript's text item delimiters to (ASCII character 31)
if application "{app}" is running then
    tell application "{app}"
        if player state is playing then
            set fields to {{{id_expr}, name of current track, artist of current track}}
            set fields to fields & {{album of current track, player position as text}}
            return fields as text
        end if
    end tell
end if
return ""
"""

PLAYERS = {"Spotify": "id of current track", "Music": "persistent ID of current track"}


def _ask_player(app: str) -> str:
    script = SCRIPT.format(app=app, id_expr=PLAYERS[app])
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
    return result.stdout.rstrip("\n") if result.returncode == 0 else ""


def _events(ask: Callable[[str], str], now: Callable[[], float]) -> Iterator[Event]:
    for app in PLAYERS:
        output = ask(app)
        if not output:
            continue
        track_id, title, artist, album, position = output.split(SEPARATOR)
        started = now() - float(position.replace(",", "."))
        # Sampling jitter moves `started` by a second or two between runs of the same play,
        # so the id is rounded to keep one play as one event.
        play = round(started / 60)
        yield Event(
            source="music",
            source_id=f"{app}:{track_id}:{play}",
            ts=started,
            title=f"{title} — {artist}",
            data={"player": app, "album": album, "track_id": track_id},
        )


def music_collector(
    ask: Callable[[str], str] = _ask_player, now: Callable[[], float] = time.time
) -> Collector:
    return Collector(
        name="music", source="music", collect=lambda cursor: full_scan("music", _events(ask, now))
    )
