"""Settings, read from ~/.config/history/config.toml. Every key is optional."""

import os
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path.home() / ".local/share/history"
CONFIG_DIR = Path.home() / ".config/history"
CONFIG_PATH = CONFIG_DIR / "config.toml"

# Sources that are rescanned in full run less often than the default interval.
DEFAULT_INTERVALS = {"calendar": 300, "notes": 300, "git": 600, "photos": 900, "transactions": 900}


def _git_email() -> list[str]:
    result = subprocess.run(
        ["git", "config", "--global", "user.email"], capture_output=True, text=True
    )
    return [result.stdout.strip()] if result.stdout.strip() else []


@dataclass(frozen=True)
class Config:
    db_path: Path = DATA_DIR / "history.db"
    host: str = "127.0.0.1"
    port: int = 8765
    interval_seconds: int = 60
    intervals: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_INTERVALS))
    disabled: list[str] = field(default_factory=list)
    git_roots: list[Path] = field(default_factory=lambda: [Path.home() / "Desktop/projects"])
    git_emails: list[str] = field(default_factory=_git_email)
    ics_feeds: list[str] = field(default_factory=list)
    transactions_dir: Path = DATA_DIR / "transactions"
    location_log: Path = DATA_DIR / "location.jsonl"
    plugins_dir: Path = CONFIG_DIR / "collectors"
    api_token: str | None = None  # required by the server when set

    @property
    def server_url(self) -> str:
        host = "127.0.0.1" if self.host == "0.0.0.0" else self.host
        return f"http://{host}:{self.port}"

    @property
    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}

    def interval_for(self, source: str) -> int:
        return self.intervals.get(source, self.interval_seconds)


def load_config(path: Path | None = None) -> Config:
    path = path or Path(os.environ.get("HISTORY_CONFIG", CONFIG_PATH))
    if not path.exists():
        return Config()
    raw = tomllib.loads(path.read_text())
    for key in ("db_path", "transactions_dir", "location_log", "plugins_dir"):
        if key in raw:
            raw[key] = Path(raw[key]).expanduser()
    if "git_roots" in raw:
        raw["git_roots"] = [Path(p).expanduser() for p in raw["git_roots"]]
    raw["intervals"] = DEFAULT_INTERVALS | raw.get("intervals", {})
    return Config(**raw)
