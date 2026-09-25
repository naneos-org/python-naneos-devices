"""Tests of the macOS workaround for the Qt tray icon crash (macOS only, needs pyobjc's AppKit).

The guard changes -[NSEvent clickCount] for the whole process, so it is tried in a fresh
interpreter and not in the pytest process.
"""

import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="AppKit events exist on macOS only"
)

EVENTS = """
import AppKit
from AppKit import NSEvent, NSPoint
from naneos.gui.macos import guard_event_click_count

def mouse(kind, clicks):
    return NSEvent.mouseEventWithType_location_modifierFlags_timestamp_windowNumber_context_eventNumber_clickCount_pressure_(
        kind, NSPoint(0, 0), 0, 0.0, 0, None, 0, clicks, 1.0)

def enter_exit(kind):
    return NSEvent.enterExitEventWithType_location_modifierFlags_timestamp_windowNumber_context_eventNumber_trackingNumber_userData_(
        kind, NSPoint(0, 0), 0, 0.0, 0, None, 0, 0, None)
"""  # noqa: E501  (the Objective-C selectors are that long)


def _run(code: str) -> subprocess.CompletedProcess[str]:
    pytest.importorskip("AppKit")
    return subprocess.run(
        [sys.executable, "-c", EVENTS + code], capture_output=True, text=True, timeout=60
    )


def test_click_count_of_a_mouse_exited_event_is_answered_instead_of_raised() -> None:
    result = _run(
        "assert guard_event_click_count()\n"
        "assert enter_exit(AppKit.NSEventTypeMouseExited).clickCount() == 0\n"
        "assert enter_exit(AppKit.NSEventTypeMouseEntered).clickCount() == 0\n"
        "print('ok')\n"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_click_count_of_real_mouse_events_is_left_alone() -> None:
    result = _run(
        "assert guard_event_click_count()\n"
        "assert mouse(AppKit.NSEventTypeLeftMouseDown, 1).clickCount() == 1\n"
        "assert mouse(AppKit.NSEventTypeLeftMouseDown, 2).clickCount() == 2\n"
        "assert mouse(AppKit.NSEventTypeRightMouseUp, 3).clickCount() == 3\n"
        "assert mouse(AppKit.NSEventTypeLeftMouseDragged, 1).clickCount() == 1\n"
        "print('ok')\n"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_installing_the_guard_twice_is_harmless() -> None:
    result = _run(
        "assert guard_event_click_count() and guard_event_click_count()\n"
        "assert mouse(AppKit.NSEventTypeLeftMouseDown, 2).clickCount() == 2\n"
        "assert enter_exit(AppKit.NSEventTypeMouseExited).clickCount() == 0\n"
        "print('ok')\n"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
