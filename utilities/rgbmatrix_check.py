""" Helper module that detects if the rgbmatrix library is present on the system.
Use the exit codes to determine if this is true.
0 = Installed and accessible globally
1 = Not installed
3 = Present but needs to be installed in a virtual environment """
import sys
import os
from pathlib import Path
if __name__ != '__main__':
    print("This module cannot be imported. Run it directly.")
    sys.exit(126)

CURRENT_DIR = Path(__file__).resolve().parent
# get the user's home directory
if os.name != 'nt':
    try:
        PATH_OWNER = CURRENT_DIR.owner()
        OWNER_HOME = os.path.expanduser(f"~{PATH_OWNER}")
    except:
        PATH_OWNER = None
        OWNER_HOME = Path.home()
else:
    PATH_OWNER = None
    OWNER_HOME = Path.home()
try:
    import rgbmatrix
    sys.exit(0)
except (ModuleNotFoundError, ImportError):
    if (RGBMATRIX_DIR := Path(OWNER_HOME, "rpi-rgb-led-matrix")).exists():
        sys.path.append(Path(RGBMATRIX_DIR, 'bindings', 'python'))
        try:
            import rgbmatrix
            sys.exit(3) # rgbmatrix isn't available globally
        except (ModuleNotFoundError, ImportError):
            sys.exit(1)
    else:
        sys.exit(1)