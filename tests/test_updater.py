"""Release checking and the install command. No test here touches the network."""

from __future__ import annotations

import json
import sys
import urllib.error
from collections.abc import Sequence

import pytest

from cookie import updater


def _release(tag: str) -> bytes:
    return json.dumps(
        {"tag_name": tag, "html_url": f"https://github.com/owner/repo/releases/tag/{tag}"}
    ).encode()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.0.0", (1, 0, 0)),
        ("v1.0.0", (1, 0, 0)),
        ("V2.11.3", (2, 11, 3)),
        ("1.2.0-rc1", (1, 2, 0)),
        ("2.0", (2, 0)),
        ("nightly", (0,)),
        ("", (0,)),
    ],
)
def test_version_keys_compare_the_way_releases_are_numbered(
    raw: str, expected: tuple[int, ...]
) -> None:
    assert updater.version_key(raw) == expected


def test_a_higher_release_sorts_above_a_lower_one() -> None:
    assert updater.version_key("v1.10.0") > updater.version_key("v1.9.0")
    assert updater.version_key("2.0.0") > updater.version_key("1.99.99")
    assert updater.version_key("1.0.0") == updater.version_key("v1.0.0")


def test_the_plan_reports_a_newer_release() -> None:
    plan = updater.plan(
        "1.0.0", fetch=lambda _url: _release("v1.1.0"), source="owner/repo", installer="pipx"
    )
    assert plan.release.tag == "v1.1.0"
    assert plan.is_newer
    assert plan.command == (
        "pipx",
        "install",
        "--force",
        "git+https://github.com/owner/repo@v1.1.0",
    )


def test_the_plan_reports_being_up_to_date() -> None:
    plan = updater.plan(
        "1.0.0", fetch=lambda _url: _release("v1.0.0"), source="owner/repo", installer="pipx"
    )
    assert not plan.is_newer


def test_a_release_older_than_the_installed_one_is_not_newer() -> None:
    plan = updater.plan(
        "2.0.0", fetch=lambda _url: _release("v1.9.9"), source="owner/repo", installer="pip"
    )
    assert not plan.is_newer


def test_the_request_goes_to_the_releases_endpoint() -> None:
    seen: list[str] = []

    def fetch(url: str) -> bytes:
        seen.append(url)
        return _release("v1.0.0")

    updater.latest_release(fetch=fetch, source="owner/repo")
    assert seen == ["https://api.github.com/repos/owner/repo/releases/latest"]


def test_a_repository_without_releases_says_so() -> None:
    def fetch(url: str) -> bytes:
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)  # type: ignore[arg-type]

    with pytest.raises(updater.UpdateError, match="no published releases"):
        updater.latest_release(fetch=fetch, source="owner/repo")


def test_another_http_error_is_reported_with_its_code() -> None:
    def fetch(url: str) -> bytes:
        raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, None)  # type: ignore[arg-type]

    with pytest.raises(updater.UpdateError, match="503"):
        updater.latest_release(fetch=fetch, source="owner/repo")


def test_an_unreachable_github_is_reported_rather_than_raised_raw() -> None:
    def fetch(_url: str) -> bytes:
        raise urllib.error.URLError("no route to host")

    with pytest.raises(updater.UpdateError, match="could not reach GitHub"):
        updater.latest_release(fetch=fetch, source="owner/repo")


@pytest.mark.parametrize("body", [b"not json at all", b"[]", json.dumps({"tag_name": ""}).encode()])
def test_a_malformed_response_is_rejected(body: bytes) -> None:
    with pytest.raises(updater.UpdateError):
        updater.latest_release(fetch=lambda _url: body, source="owner/repo")


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [
        ("/home/x/.local/pipx/venvs/cookie", "pipx"),
        ("/home/x/.local/share/uv/tools/cookie", "uv"),
        ("/usr", "pip"),
        ("/home/x/project/.venv", "pip"),
    ],
)
def test_the_installer_is_guessed_from_where_the_code_lives(prefix: str, expected: str) -> None:
    assert updater.installer_name(prefix) == expected


@pytest.mark.parametrize(
    ("installer", "head"),
    [("pipx", ("pipx", "install", "--force")), ("uv", ("uv", "tool", "install", "--force"))],
)
def test_the_install_command_pins_the_tag(installer: str, head: tuple[str, ...]) -> None:
    command = updater.install_command("v2.3.4", installer=installer, source="owner/repo")
    assert command[: len(head)] == head
    assert command[-1] == "git+https://github.com/owner/repo@v2.3.4"


def test_the_pip_command_uses_this_interpreter() -> None:
    command = updater.install_command("v1.0.0", installer="pip", source="owner/repo")
    assert command[0] == sys.executable
    assert command[1:4] == ("-m", "pip", "install")


def test_applying_runs_the_command_and_reports_a_failure() -> None:
    calls: list[Sequence[str]] = []
    plan = updater.plan(
        "1.0.0", fetch=lambda _url: _release("v1.1.0"), source="owner/repo", installer="pipx"
    )

    def ok(command: Sequence[str]) -> int:
        calls.append(command)
        return 0

    assert updater.apply(plan, runner=ok) == 0
    assert calls == [list(plan.command)] or calls == [plan.command]

    with pytest.raises(updater.UpdateError, match="exited with 1"):
        updater.apply(plan, runner=lambda _command: 1)


def test_the_repository_can_be_pointed_at_a_fork(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COOKIE_REPO", "someone/their-fork")
    assert updater.repo() == "someone/their-fork"
    assert "someone/their-fork" in updater.install_command("v1.0.0", installer="pipx")[-1]


def test_the_default_repository_is_used_when_nothing_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COOKIE_REPO", raising=False)
    assert updater.repo() == updater.DEFAULT_REPO
