# Pull Request: Add Native Windows Support for Toolchain and Controls Build

## Problem
While `README.md` states *"Windows and Linux (Proton) — same files"*, building from source or running `./install.py` / `./controls_mod.py` on native Windows failed because:
1. `common.py` hardcoded Linux binaries (`MBINCompiler-linux`, `hgpaktool`, `.steam/steam` paths).
2. `setup_tools.py` attempted to run bash `.sh` scripts (`dotnet-install.sh`) and download Linux tar/gz archives instead of Windows PE executables (`MBINCompiler.exe`, `libMBIN.dll`, `hgpaktool-x86_64-pc-windows.zip`).
3. Running on Windows without running the controls remap step left vanilla keybindings active (Roll bound to A/D, Pulse Jump bound to Space), conflicting directly with BetterFlight's 6DOF strafe and vertical thrust.

## Changes Made
1. **OS Detection & Binary Selection (`common.py`):**
   - Added `IS_WINDOWS = sys.platform == "win32"`
   - Automatically resolve `MBINC` to `MBINCompiler.exe` (with `libMBIN.dll`) on Windows vs `MBINCompiler-linux` on Linux.
   - Automatically resolve `HGPAK` to `hgpaktool.exe` on Windows vs `hgpaktool` on Linux.
   - Added Windows Steam library path resolution (reading Registry `SOFTWARE\Valve\Steam` and `libraryfolders.vdf`).
2. **Windows Toolchain Setup (`setup_tools.py`):**
   - Downloads `hgpaktool-x86_64-pc-windows.zip` on Windows.
   - Uses system `.NET` on Windows (available natively via `dotnet`) or downloads Windows assets.
   - Probes `MBINCompiler.exe` releases from GitHub assets.
3. **Automated Remap Generator (`build_controls_windows.py`):**
   - Provides a standalone / integrated pipeline to decompile `gcinputbindings_win_keyboard.mbin`, remap actions according to `controls.ini`, recompile, and place into `GAMEDATA/MODS/BetterFlightControls/`.
