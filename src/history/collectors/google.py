"""Access to Gmail and Google Calendar through the `gws` CLI, which owns the login."""

import json
import subprocess
from typing import Any

from history.collectors.base import CollectorNotReady

LOGIN_COMMAND = "gws auth login --readonly --services gmail,calendar"


def gws(*command: str, **params: Any) -> dict[str, Any]:
    """Runs e.g. `gws("gmail", "users", "getProfile", userId="me")` and returns its JSON."""
    try:
        result = subprocess.run(
            ["gws", *command, "--params", json.dumps(params)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        raise CollectorNotReady("the gws CLI isn't installed") from None
    output = result.stdout
    reply = json.loads(output[output.index("{") :]) if "{" in output else {}
    error = reply.get("error")
    if error:
        if error.get("code") in (401, 403):
            raise CollectorNotReady(f"Google access failed; run `{LOGIN_COMMAND}`")
        raise RuntimeError(f"gws {' '.join(command)}: {error.get('message')}")
    if result.returncode != 0:
        raise RuntimeError(f"gws {' '.join(command)} failed: {result.stderr[:200]}")
    return reply
