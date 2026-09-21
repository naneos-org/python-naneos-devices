"""Hardware-free tests for the automatic update (naneos-uploader-update)."""

from importlib.metadata import entry_points
from pathlib import Path

import pytest

from naneos.uploader_update import (
    INSTALLER_URL,
    PYPI_URL,
    Plan,
    make_plan,
    update,
    version_key,
)


def test_console_script_is_registered() -> None:
    scripts = {ep.name: ep.value for ep in entry_points(group="console_scripts")}
    assert scripts.get("naneos-uploader-update") == "naneos.uploader_update:main"


@pytest.mark.parametrize(
    "older, newer",
    [
        ("2.0.5", "2.0.6"),
        ("2.0.6rc2", "2.0.6"),
        ("2.0.5", "2.0.6rc1"),
        ("2.0.6rc1", "2.0.6rc2"),
        ("2.0.6a1", "2.0.6b1"),
        ("2.0.6.dev3", "2.0.6a1"),
        ("2.0.9", "2.0.10"),
        ("2.0", "2.0.1"),
        ("v2.0.5", "2.1"),
    ],
)
def test_version_order(older: str, newer: str) -> None:
    assert version_key(older) < version_key(newer)


def test_version_equal_forms_and_garbage() -> None:
    assert version_key("2.0") == version_key("2.0.0")
    with pytest.raises(ValueError):
        version_key("latest")


def pypi(version: str):
    def fetch(url: str) -> dict:
        assert url == PYPI_URL
        return {"info": {"version": version}}

    return fetch


def test_plan_updates_to_a_newer_release() -> None:
    plan = make_plan(installed="2.0.5", source="PyPI", fetch=pypi("2.0.6"))
    assert plan.update and plan.latest == "2.0.6"
    assert plan.describe() == "update 2.0.5 -> 2.0.6"


def test_plan_up_to_date_does_nothing() -> None:
    plan = make_plan(installed="2.0.6", source="PyPI", fetch=pypi("2.0.6"))
    assert not plan.update and "up to date" in plan.describe()
    plan = make_plan(installed="2.0.7rc1", source="PyPI", fetch=pypi("2.0.6"))
    assert not plan.update


def test_plan_skips_git_installations() -> None:
    def fetch(url: str) -> dict:
        raise AssertionError("must not touch the network")

    plan = make_plan(
        installed="2.0.5",
        source="https://github.com/naneos-org/python-naneos-devices/archive/release_test.tar.gz",
        fetch=fetch,
    )
    assert not plan.update and "git ref" in plan.reason


def test_plan_survives_network_errors() -> None:
    def fetch(url: str) -> dict:
        raise OSError("no route to host")

    plan = make_plan(installed="2.0.5", source="PyPI", fetch=fetch)
    assert not plan.update and "no route to host" in plan.reason


def test_update_runs_the_installer_of_the_release_tag(capsys: pytest.CaptureFixture) -> None:
    fetched: list[str] = []
    runs: list[tuple[str, list[str]]] = []

    def fetch_text(url: str) -> str:
        fetched.append(url)
        return "#!/usr/bin/env bash\necho installer\n"

    def run(script: Path, args: list[str]) -> int:
        runs.append((script.read_text(), args))
        return 0

    code = update("pi", Plan("2.0.5", "PyPI", latest="2.0.6"), fetch_text_=fetch_text, run=run)

    assert code == 0
    assert fetched == [INSTALLER_URL.format(ref="v2.0.6")]
    assert runs == [
        ("#!/usr/bin/env bash\necho installer\n", ["--version", "2.0.6", "--user", "pi"])
    ]
    assert "installer from v2.0.6" in capsys.readouterr().out


def test_update_falls_back_to_master_when_the_tag_is_missing() -> None:
    def fetch_text(url: str) -> str:
        if "/v2.0.6/" in url:
            raise OSError("404")
        return "echo master\n"

    args_seen: list[list[str]] = []

    def run(script: Path, args: list[str]) -> int:
        args_seen.append(args)
        return 0

    assert update("pi", Plan("2.0.5", "PyPI", latest="2.0.6"), fetch_text_=fetch_text, run=run) == 0
    assert args_seen == [["--version", "2.0.6", "--user", "pi"]]


def test_update_reports_a_download_failure() -> None:
    def fetch_text(url: str) -> str:
        raise OSError("offline")

    def run(script: Path, args: list[str]) -> int:
        raise AssertionError("must not run")

    assert update("pi", Plan("2.0.5", "PyPI", latest="2.0.6"), fetch_text_=fetch_text, run=run) == 1
