"""The naneos tray app (`naneos-gui`), installed with `naneos-devices[gui]`.

Only the modules that draw something import Qt, and they do it lazily, so the
rest of this package (and the whole of `naneos`) works without PySide6. Nothing
in the package imports this subpackage: the Raspberry Pi uploader never loads it.
"""
