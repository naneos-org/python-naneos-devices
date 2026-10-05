"""Hardware-free tests for how PartectorBleManager waits for a Bluetooth adapter.

On macOS the adapter check does not return until the user has answered the Bluetooth
permission dialog, so stop() must be able to end the wait, and so must it end the pause
between two checks.
"""

import asyncio
import logging
import time

import pytest

from naneos.ble.partector.manager import PartectorBleManager


async def _never_returns() -> bool:
    await asyncio.Event().wait()
    return True  # pragma: no cover


def _run_in_thread_then_stop(manager: PartectorBleManager, after: float = 0.5) -> float:
    """Start the manager thread, stop it after a moment. Seconds stop() took to take effect."""
    manager.start()
    time.sleep(after)
    stopped_at = time.monotonic()
    manager.stop()
    manager.join(timeout=10)
    return time.monotonic() - stopped_at


@pytest.mark.timeout(30)
def test_stop_ends_the_wait_for_an_adapter_check_that_never_returns(monkeypatch) -> None:
    monkeypatch.setattr(PartectorBleManager, "_adapter_available", staticmethod(_never_returns))
    manager = PartectorBleManager()

    took = _run_in_thread_then_stop(manager)

    assert not manager.is_alive()
    assert took < 2


@pytest.mark.timeout(30)
def test_stop_ends_the_pause_between_two_adapter_checks(monkeypatch) -> None:
    async def not_yet() -> bool:
        return False

    monkeypatch.setattr(PartectorBleManager, "_adapter_available", staticmethod(not_yet))
    monkeypatch.setattr(PartectorBleManager, "ADAPTER_CHECK_INTERVAL_SECONDS", 20.0)
    manager = PartectorBleManager()

    took = _run_in_thread_then_stop(manager)

    assert not manager.is_alive()
    assert took < 2  # not the 20 s of the pause


@pytest.mark.timeout(30)
def test_an_adapter_that_is_ready_does_not_wait(monkeypatch) -> None:
    async def ready() -> bool:
        return True

    monkeypatch.setattr(PartectorBleManager, "_adapter_available", staticmethod(ready))
    manager = PartectorBleManager()

    started = time.monotonic()
    asyncio.run(manager._wait_for_bluetooth_adapter())

    assert time.monotonic() - started < 0.15  # well below one poll of the stop event


@pytest.mark.timeout(30)
def test_an_adapter_that_is_not_ready_is_checked_again(monkeypatch) -> None:
    answers = [False, False, True]

    async def sometimes() -> bool:
        return answers.pop(0)

    monkeypatch.setattr(PartectorBleManager, "_adapter_available", staticmethod(sometimes))
    monkeypatch.setattr(PartectorBleManager, "ADAPTER_CHECK_INTERVAL_SECONDS", 0.05)
    manager = PartectorBleManager()

    asyncio.run(manager._wait_for_bluetooth_adapter())

    assert answers == []


@pytest.mark.timeout(30)
def test_a_stopped_manager_does_not_start_a_check(monkeypatch) -> None:
    calls: list[int] = []

    async def counted() -> bool:
        calls.append(1)
        return True

    monkeypatch.setattr(PartectorBleManager, "_adapter_available", staticmethod(counted))
    manager = PartectorBleManager()
    manager.stop()

    asyncio.run(manager._wait_for_bluetooth_adapter())

    assert calls == []


@pytest.mark.timeout(30)
def test_a_slow_adapter_check_is_reported_once(monkeypatch, caplog) -> None:
    async def slow() -> bool:
        await asyncio.sleep(0.6)
        return True

    monkeypatch.setattr(PartectorBleManager, "_adapter_available", staticmethod(slow))
    monkeypatch.setattr(PartectorBleManager, "ADAPTER_CHECK_SLOW_SECONDS", 0.2)
    manager = PartectorBleManager()

    with caplog.at_level(logging.INFO, logger="naneos"):
        asyncio.run(manager._wait_for_bluetooth_adapter())

    slow_lines = [
        r for r in caplog.records if "Still waiting for the Bluetooth adapter" in r.message
    ]
    assert len(slow_lines) == 1
    assert any("adapter is available and ready" in r.message for r in caplog.records)


@pytest.mark.timeout(30)
def test_an_error_of_the_adapter_check_is_not_swallowed(monkeypatch) -> None:
    async def broken() -> bool:
        raise RuntimeError("boom")

    monkeypatch.setattr(PartectorBleManager, "_adapter_available", staticmethod(broken))
    manager = PartectorBleManager()

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(manager._wait_for_bluetooth_adapter())
