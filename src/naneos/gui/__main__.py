"""`python -m naneos.gui`: the same as the `naneos-gui` command.

The installers use it with the console python of the tool environment, because
a Windows PowerShell does not wait for the windowless naneos-gui.exe.
"""

import sys

from naneos.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
