"""Your commits, across every repository under the configured roots."""

import subprocess
from collections.abc import Iterator
from pathlib import Path

from history.collectors.base import Collector, full_scan
from history.models import Event

SEPARATOR = "\x1f"
FORMAT = SEPARATOR.join(["%H", "%at", "%ae", "%s"])


def _repositories(roots: list[Path]) -> Iterator[Path]:
    for root in roots:
        if (root / ".git").exists():
            yield root
        for git_dir in sorted(root.glob("*/.git")):
            yield git_dir.parent


def _events(roots: list[Path], emails: list[str]) -> Iterator[Event]:
    wanted = {email.lower() for email in emails}
    for repo in _repositories(roots):
        result = subprocess.run(
            ["git", "-C", str(repo), "log", "--all", "--no-merges", f"--format={FORMAT}"],
            capture_output=True,
            text=True,
            errors="replace",
        )
        if result.returncode != 0:  # e.g. a repository with no commits yet
            continue
        for line in result.stdout.splitlines():
            sha, timestamp, email, subject = line.split(SEPARATOR, 3)
            if email.lower() in wanted:
                yield Event(
                    source="git",
                    source_id=f"{repo.name}:{sha}",
                    ts=float(timestamp),
                    title=subject,
                    data={"repo": repo.name, "sha": sha},
                )


def git_collector(roots: list[Path], emails: list[str]) -> Collector:
    return Collector(
        name="git", source="git", collect=lambda cursor: full_scan("git", _events(roots, emails))
    )
