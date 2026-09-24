"""Tests for the backoff and the RSSI gate of a BLE connection: no bleak, no adapter."""

from naneos.ble.partector.reconnect import (
    MAX_BACKOFF_SECONDS,
    MIN_RSSI_CONNECT_DBM,
    RSSI_GATE_MAX_SILENCE_SECONDS,
    ReconnectPolicy,
)


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_backoff_doubles_up_to_the_cap_and_counts_down_with_the_loop() -> None:
    policy = ReconnectPolicy(8617)
    assert not policy.waiting

    seen = []
    for _ in range(6):
        policy.start_backoff()
        seen.append(policy.backoff_remaining)
    assert seen == [5, 10, 20, MAX_BACKOFF_SECONDS, MAX_BACKOFF_SECONDS, MAX_BACKOFF_SECONDS]
    assert policy.attempt == 6

    policy.backoff_remaining = 2
    assert policy.waiting
    policy.tick()
    policy.tick()
    assert not policy.waiting
    policy.tick()
    assert policy.backoff_remaining == 0  # never negative


def test_a_working_link_resets_the_counters_but_not_a_running_backoff() -> None:
    policy = ReconnectPolicy(8617)
    policy.start_backoff()
    policy.gatt_errors = 3

    policy.link_established()
    assert (policy.attempt, policy.gatt_errors) == (0, 0)

    policy.start_backoff()
    assert policy.backoff_remaining == 5  # counting starts again from the first step

    policy.clear_backoff()
    assert not policy.waiting


def test_without_a_provider_every_attempt_is_allowed() -> None:
    assert ReconnectPolicy(8617).signal_allows_connect()


def test_the_gate_lets_a_strong_signal_through_and_holds_back_a_weak_or_missing_one() -> None:
    rssi: list[int | None] = [MIN_RSSI_CONNECT_DBM]
    policy = ReconnectPolicy(8617, rssi_provider=lambda: rssi[0], clock=_Clock())

    assert policy.signal_allows_connect()  # exactly at the limit is enough
    rssi[0] = MIN_RSSI_CONNECT_DBM - 1
    assert not policy.signal_allows_connect()
    rssi[0] = None  # not advertising recently
    assert not policy.signal_allows_connect()
    rssi[0] = -40
    assert policy.signal_allows_connect()


def test_a_device_that_stopped_advertising_gets_one_attempt_after_a_long_silence() -> None:
    clock = _Clock()
    policy = ReconnectPolicy(8617, rssi_provider=lambda: None, clock=clock)

    clock.now += RSSI_GATE_MAX_SILENCE_SECONDS - 1
    assert not policy.signal_allows_connect()

    clock.now += 1
    assert policy.signal_allows_connect()  # the gate opens once ...
    assert not policy.signal_allows_connect()  # ... and closes again

    clock.now += RSSI_GATE_MAX_SILENCE_SECONDS
    assert policy.signal_allows_connect()


def test_a_good_signal_restarts_the_silence_timer() -> None:
    clock = _Clock()
    rssi: list[int | None] = [-50]
    policy = ReconnectPolicy(8617, rssi_provider=lambda: rssi[0], clock=clock)

    clock.now += RSSI_GATE_MAX_SILENCE_SECONDS - 1
    assert policy.signal_allows_connect()  # the timer is reset here

    rssi[0] = None
    clock.now += RSSI_GATE_MAX_SILENCE_SECONDS - 1
    assert not policy.signal_allows_connect()
