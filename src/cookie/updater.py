"""Checking GitHub for a newer release and installing it.

Updating never touches the save. The save lives in the XDG data directory and an install only
replaces the code, so there is no migration step here and no backup to take. That is the whole
reason this is safe to offer as a one-liner.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from typing import Final

DEFAULT_REPO: Final[str] = "Justcakenl/cookie-clicker-linux"
RELEASE_API: Final[str] = "https://api.github.com/repos/{repo}/releases/latest"
REQUEST_TIMEOUT: Final[float] = 10.0

Fetch = Callable[[str], bytes]
Runner = Callable[[Sequence[str]], int]


class UpdateError(Exception):
    """The update could not be checked or applied."""


@dataclasses.dataclass(frozen=True, slots=True)
class Release:
    tag: str
    url: str


@dataclasses.dataclass(frozen=True, slots=True)
class Plan:
    current: str
    release: Release
    command: tuple[str, ...]
    installer: str

    @property
    def is_newer(self) -> bool:
        return version_key(self.release.tag) > version_key(self.current)


def repo() -> str:
    """The repository to update from. Overridable so a fork can point at itself."""
    return os.environ.get("COOKIE_REPO", DEFAULT_REPO)


def version_key(raw: str) -> tuple[int, ...]:
    """A comparable key for a version string.

    Leading "v" and any trailing pre-release suffix are ignored, so "v1.2.0" and "1.2.0-rc1" both
    compare as (1, 2, 0). Comparing releases is all this needs to do; it is not a PEP 440 parser.
    """
    numbers = re.findall(r"\d+", raw.strip().lstrip("vV"))
    return tuple(int(part) for part in numbers[:3]) or (0,)


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json", "User-Agent": "cookie-updater"}
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        body = response.read()
        assert isinstance(body, bytes)
        return body


def latest_release(*, fetch: Fetch = _fetch, source: str | None = None) -> Release:
    """The newest published release of the repository."""
    name = source or repo()
    try:
        raw = fetch(RELEASE_API.format(repo=name))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise UpdateError(f"{name} has no published releases yet") from error
        raise UpdateError(f"GitHub said {error.code} for {name}") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise UpdateError(f"could not reach GitHub: {error}") from error

    try:
        payload = json.loads(raw)
    except ValueError as error:
        raise UpdateError("GitHub returned something that is not JSON") from error
    if not isinstance(payload, dict):
        raise UpdateError("GitHub returned an unexpected shape")

    tag = payload.get("tag_name")
    if not isinstance(tag, str) or not tag:
        raise UpdateError("the latest release has no tag")
    url = payload.get("html_url")
    return Release(tag=tag, url=url if isinstance(url, str) else f"https://github.com/{name}")


def installer_name(prefix: str | None = None) -> str:
    """How this copy was installed, guessed from where it is running."""
    location = (prefix or sys.prefix).replace(os.sep, "/")
    if "/pipx/" in location:
        return "pipx"
    if "/uv/tools/" in location:
        return "uv"
    return "pip"


def install_command(
    tag: str, *, installer: str | None = None, source: str | None = None
) -> tuple[str, ...]:
    """The argv that installs a given tag over this copy."""
    name = installer or installer_name()
    target = f"git+https://github.com/{source or repo()}@{tag}"
    match name:
        case "pipx":
            return ("pipx", "install", "--force", target)
        case "uv":
            return ("uv", "tool", "install", "--force", target)
        case _:
            return (sys.executable, "-m", "pip", "install", "--upgrade", target)


def plan(
    current: str, *, fetch: Fetch = _fetch, source: str | None = None, installer: str | None = None
) -> Plan:
    """What updating would do, without doing it."""
    release = latest_release(fetch=fetch, source=source)
    name = installer or installer_name()
    return Plan(
        current=current,
        release=release,
        command=install_command(release.tag, installer=name, source=source),
        installer=name,
    )


def _run(command: Sequence[str]) -> int:
    return subprocess.call(list(command))


def apply(update: Plan, *, runner: Runner = _run) -> int:
    """Run the install. The caller is responsible for having asked the player first."""
    code = runner(update.command)
    if code != 0:
        raise UpdateError(f"{update.installer} exited with {code}")
    return code
