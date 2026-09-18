"""Hardware-free tests for restarting a PartectorBleScanner that went silent."""

import asyncio
from typing import Any

import pytest

from naneos.ble.partector import scanner as scanner_module
from naneos.ble.partector.scanner import PartectorBleScanner


class _FakeBleakScanner:
    sessions: list[dict[str, Any]] = []

    def __init__(self, detection_callback: Any, **kwargs: Any) -> None:
        self._kwargs = kwargs

    async def __aenter__(self) -> "_FakeBleakScanner":
        self.sessions.append(self._kwargs)
        return self

    async def __aexit__(self, *exc: object) -> None:
        pass


async def _restart_twice(passive_supported: bool) -> list[bool]:
    scanner = PartectorBleScanner(
        loop=asyncio.get_running_loop(), queue=PartectorBleScanner.create_scanner_queue()
    )
    scanner._passive_supported = scanner._passive = passive_supported

    scanner.start()
    await asyncio.sleep(0.01)
    await scanner.restart()
    await asyncio.sleep(0.01)
    assert scanner.silent_for < 1.0  # a new scan listens from zero
    await scanner.restart(switch_mode=True)
    await asyncio.sleep(0.01)
    await scanner.stop()

    return ["scanning_mode" in kwargs for kwargs in _FakeBleakScanner.sessions]


@pytest.fixture(autouse=True)
def fake_bleak(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeBleakScanner.sessions = []
    monkeypatch.setattr(scanner_module, "BleakScanner", _FakeBleakScanner)


def test_restart_opens_a_new_scan_and_can_switch_the_mode() -> None:
    assert asyncio.run(_restart_twice(passive_supported=True)) == [True, True, False]


def test_restart_never_switches_to_a_passive_scan_bluez_refused() -> None:
    assert asyncio.run(_restart_twice(passive_supported=False)) == [False, False, False]
