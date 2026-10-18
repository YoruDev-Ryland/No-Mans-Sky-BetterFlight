#!/usr/bin/env python3
"""
Run this after every No Man's Sky update (with the game closed). Linux and Windows.

1. Revalidates MBINCompiler against the new game build (fails closed).
2. Rebuilds and reinstalls everything via install.py.

The native DLL finds its hooks by signature at runtime, so it usually survives
updates unchanged. If it doesn't, Binaries/BetterFlight.log says which
signature failed, and the game still runs normally with strafe disabled.

    python3 update.py [--force]      (arguments go to setup_tools.py)
"""
import subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for script, args in (("setup_tools.py", sys.argv[1:]), ("install.py", [])):
    r = subprocess.run([sys.executable, str(HERE / script), *args])
    if r.returncode != 0:
        sys.exit(r.returncode)
