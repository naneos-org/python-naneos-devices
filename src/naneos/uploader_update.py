"""Automatic update of a Raspberry Pi installation to the newest release.

``naneos-uploader-update`` runs from the ``naneos_uploader_update.timer`` that
the installer writes (once a day, randomized). It is cheap when there is nothing
to do: one request to the PyPI JSON of the package, whose ``info.version`` is
the newest release without pre-releases, compared with the installed version.
The service is not touched in that case.

When PyPI has a newer release, the installer of exactly that release (git tag
``vX.Y.Z``) is downloaded and run with ``--version X.Y.Z``. The installer is
the updater because it also carries the unit files and config drop-ins, which
a plain ``pip install --upgrade`` would miss. It restarts the service once.

Never touched: an installation from a git ref (``--ref``, hardware testing) and
pre-releases. The timer is switched with ``--auto-update`` / ``--no-auto-update``
on the installer line, with ``AUTO_UPDATE=on|off`` in the change file on the SD
card, or with ``systemctl enable|disable --now naneos_uploader_update.timer``.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from naneos import __version__
from naneos.cli import installed_from

PACKAGE = "naneos-devices"
PYPI_URL = f"https://pypi.org/pypi/{PACKAGE}/json"
REPO = "naneos-org/python-naneos-devices"
INSTALLER_URL = f"https://raw.githubusercontent.com/{REPO}/{{ref}}/installers/install.sh"
UPDATE_SERVICE = "naneos_uploader_update.service"
UPDATE_TIMER = "naneos_uploader_update.timer"

_VERSION = re.compile(r"^v?(?P<release>\d+(?:\.\d+)*)(?:(?P<stage>a|b|rc|\.dev)(?P<num>\d*))?$")
_STAGES = {".dev": 0, "a": 1, "b": 2, "rc": 3, None: 4}


def version_key(version: str) -> tuple[tuple[int, ...], int, int]:
    """A sortable key for the version formats this project publishes (2.0.6, 2.0.6rc2)."""
    match = _VERSION.match(version.strip())
    if match is None:
        raise ValueError(f"cannot compare version {version!r}")
    release = [int(part) for part in match.group("release").split(".")]
    while len(release) > 1 and release[-1] == 0:
        release.pop()
    return tuple(release), _STAGES[match.group("stage")], int(match.group("num") or 0)


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": f"{PACKAGE}/{__version__}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": f"{PACKAGE}/{__version__}"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


@dataclass
class Plan:
    installed: str
    source: str
    latest: str | None = None
    reason: str = ""

    @property
    def update(self) -> bool:
        return self.latest is not None and not self.reason

    def describe(self) -> str:
        if self.update:
            return f"update {self.installed} -> {self.latest}"
        return f"{self.installed} ({self.source}): {self.reason}"


def make_plan(
    installed: str = __version__,
    source: str | None = None,
    fetch: Callable[[str], dict] = fetch_json,
) -> Plan:
    """Decide without changing anything."""
    plan = Plan(installed=installed, source=source or installed_from())
    if plan.source != "PyPI":
        plan.reason = "installed from a git ref, not updated automatically"
        return plan
    try:
        plan.latest = str(fetch(PYPI_URL)["info"]["version"])
    except Exception as e:  # network, JSON shape: try again tomorrow
        plan.reason = f"could not read the newest version from PyPI ({e})"
        return plan
    try:
        newer = version_key(plan.latest) > version_key(installed)
    except ValueError as e:
        plan.reason = str(e)
        return plan
    if not newer:
        plan.reason = f"up to date, newest release is {plan.latest}"
    return plan


def run_installer(script: Path, args: list[str]) -> int:
    """Run the installer with its output going to our stdout (the journal)."""
    sys.stdout.flush()
    return subprocess.run(["bash", str(script), *args], check=False).returncode


def update(
    user: str,
    plan: Plan,
    fetch_text_: Callable[[str], str] = fetch_text,
    run: Callable[[Path, list[str]], int] = run_installer,
) -> int:
    """Download the installer of the newest release and run it. Returns its exit code."""
    assert plan.latest is not None
    ref = f"v{plan.latest}"
    try:
        script_text = fetch_text_(INSTALLER_URL.format(ref=ref))
    except Exception as e:
        # The release workflow creates the tag after the release is on PyPI, so for a
        # short while there is a release without its installer. The installer of
        # master is no substitute: it may already belong to the next release and
        # write unit files the installed version does not understand.
        print(f"could not download the installer of {ref} ({e}), trying again tomorrow")
        return 1
    print(f"installer from {ref}")
    with tempfile.TemporaryDirectory(prefix="naneos-update-") as tmp:
        script = Path(tmp) / "install.sh"
        script.write_text(script_text, encoding="utf-8")
        return run(script, ["--version", plan.latest, "--user", user])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="naneos-uploader-update",
        description=f"Update {PACKAGE} to the newest release on PyPI, if there is one.",
    )
    parser.add_argument("--version", action="version", version=f"{PACKAGE} {__version__}")
    parser.add_argument("--user", default="pi", help="user that runs the service (default: pi)")
    parser.add_argument("--check", action="store_true", help="only report, never install")
    args = parser.parse_args(argv)

    plan = make_plan()
    print(f"{PACKAGE}: {plan.describe()}")
    if not plan.update or args.check:
        return 0
    return update(args.user, plan)


if __name__ == "__main__":
    sys.exit(main())
