"""macOS details of the tray app. Needs pyobjc-core, which bleak already brings on a Mac."""

import ctypes
import ctypes.util
from typing import Any

from naneos.logger import get_naneos_logger

logger = get_naneos_logger("naneos.gui.macos")

# NSApplicationActivationPolicyAccessory: no Dock icon and no menu bar of its own.
_ACCESSORY = 1


def hide_dock_icon() -> None:
    """Keep the tray app out of the Dock.

    LSUIElement in the app bundle only covers the launcher process. The python
    process that Qt runs in is a separate application to macOS, so it needs the
    same treatment (it is also the only one when run from a terminal).
    """
    try:
        import objc

        objc.lookUpClass("NSApplication").sharedApplication().setActivationPolicy_(_ACCESSORY)
    except Exception as e:  # a Dock icon is ugly, not fatal
        logger.warning(f"Could not hide the Dock icon: {e}")


# NSEventType values for which -[NSEvent clickCount] is valid: left, right and other mouse
# button down, up and dragged.
_MOUSE_EVENT_TYPES = frozenset({1, 2, 3, 4, 6, 7, 25, 26, 27})

_click_count_guard: Any = None  # the ctypes callback must stay alive as long as it is installed


def guard_event_click_count() -> bool:
    """Stop Qt's tray icon from crashing the app on macOS 27. Returns whether it is installed.

    Qt 6.11.2 (and 6.12.0) reads `[NSApp currentEvent].clickCount` when the status item menu
    opens. On macOS 27 that event can be a MouseExited or a gesture event, and AppKit raises
    NSInternalInconsistencyException ("Invalid message sent to event"), which ends the process
    after a few clicks on the icon. Fixed in Qt (qtbase 65020b4, "Don't assume the current event
    is a mouse event in the tray icon"), but not yet in a PySide6 release on PyPI.

    This replaces clickCount, in this process only, by a version that answers 0 for an event
    that is not a mouse button event and asks the original for the others. Qt then sees a plain
    click, which is what the fix does. Remove it once naneos-devices requires a PySide6 with the
    Qt fix.
    """
    global _click_count_guard
    if _click_count_guard is not None:
        return True
    try:
        libobjc = ctypes.CDLL(ctypes.util.find_library("objc") or "/usr/lib/libobjc.A.dylib")
        pointer = ctypes.c_void_p
        libobjc.objc_getClass.restype = pointer
        libobjc.objc_getClass.argtypes = [ctypes.c_char_p]
        libobjc.sel_registerName.restype = pointer
        libobjc.sel_registerName.argtypes = [ctypes.c_char_p]
        libobjc.class_getInstanceMethod.restype = pointer
        libobjc.class_getInstanceMethod.argtypes = [pointer, pointer]
        libobjc.method_getImplementation.restype = pointer
        libobjc.method_getImplementation.argtypes = [pointer]
        libobjc.method_setImplementation.restype = pointer
        libobjc.method_setImplementation.argtypes = [pointer, pointer]

        method = libobjc.class_getInstanceMethod(
            libobjc.objc_getClass(b"NSEvent"), libobjc.sel_registerName(b"clickCount")
        )
        if not method:
            raise RuntimeError("NSEvent has no clickCount")
        type_selector = libobjc.sel_registerName(b"type")

        click_count_type = ctypes.CFUNCTYPE(ctypes.c_long, pointer, pointer)  # NSInteger
        event_type_type = ctypes.CFUNCTYPE(ctypes.c_ulong, pointer, pointer)  # NSUInteger
        original = click_count_type(libobjc.method_getImplementation(method))
        event_type = event_type_type(("objc_msgSend", libobjc))  # [event type]

        def click_count(event: int, selector: int) -> int:
            if event_type(event, type_selector) in _MOUSE_EVENT_TYPES:
                return int(original(event, selector))
            return 0

        callback = click_count_type(click_count)
        libobjc.method_setImplementation(method, ctypes.cast(callback, pointer))
        _click_count_guard = callback
        return True
    except Exception as e:  # without it the tray can crash on macOS 27, but only there
        logger.warning(f"Could not install the clickCount guard: {e}")
        return False
