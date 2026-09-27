# Copyright © 2026 Roger B. Leuthner. All rights reserved.  This software is provided for informational and educational purposes. Use of this software does not imply endorsement by the author of any particular use or application. The author assumes no responsibility or liability for any damages or consequences arising from its use.

# banner.py

import os


def print_banner(APP_VERSION, APP_NAME):
    u = os.uname()

    print()
    print("=" * 50)
    print(" ESP32 MicroPython")
    print("=" * 50)
    print(f" Firmware : {u.release}")
    print(f" Build    : {u.version}")
    print(f" Machine  : {u.machine}")
    print(f" System   : {u.sysname}")
    print(f" App : {APP_NAME}")
    print(f" App Version : {APP_VERSION}")
    print("=" * 50)
    print()
