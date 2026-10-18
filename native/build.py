#!/usr/bin/env python3
"""
Build BetterFlight as a winmm.dll proxy with llvm-mingw (no MSVC). Linux and Windows.

    python build.py             -> build/winmm.dll
    python build.py simtest     -> also build/simtest.exe and run it
                                   (offline flight-logic simulator)
    python build.py selftest    -> also build/selftest.exe and run it against the
                                   installed NMS.exe (maps it, never executes the game)

On Linux the test programs run under Wine; on Windows they run natively.
The compiler is tools/llvm-mingw, installed by setup_tools.py.

The export surface (every winmm function) is generated from native/reference/
by gen_winmm_exports.py. Builds are reproducible: the linker's embedded
timestamps are zeroed, so the same source always gives the same file hash.

Environment: OUT (output path, default build/winmm.dll), EXTRA_CFLAGS.
"""
import os, shlex, struct, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WINDOWS = sys.platform == "win32"
EXE = ".exe" if WINDOWS else ""
CC = HERE.parent / "tools" / "llvm-mingw" / "bin" / f"x86_64-w64-mingw32-clang{EXE}"

MH = "third_party/minhook"
SRCS = [f"{MH}/src/buffer.c", f"{MH}/src/hook.c", f"{MH}/src/trampoline.c", f"{MH}/src/hde/hde64.c"]
FLAGS = ["-O2", "-Wall", "-Wextra", "-Wno-unused-parameter", "-std=gnu11", "-D_WIN32_WINNT=0x0601",
         "-I", f"{MH}/include", "-I", "src", "-static", "-s"]
# GUID and data-format definitions only (DirectInput itself is loaded at runtime).
LIBS = ["-ldxguid", "-ldinput8"]


def step(cmd, **kw):
    """Run in native/, relative paths exactly as build.sh used them (reproducible output)."""
    r = subprocess.run([str(c) for c in cmd], cwd=HERE, **kw)
    if r.returncode != 0:
        sys.exit(r.returncode)
    return r


def zero_timestamps(path):
    """COFF and export-directory TimeDateStamp -> 0, so rebuilds are byte-identical."""
    d = bytearray(path.read_bytes())
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    struct.pack_into("<I", d, pe + 8, 0)                                   # COFF TimeDateStamp
    opt = pe + 24
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    optsz = struct.unpack_from("<H", d, pe + 20)[0]
    exp_rva = struct.unpack_from("<I", d, opt + 112)[0]
    if exp_rva:
        for i in range(nsec):
            o = pe + 24 + optsz + i * 40
            vsz, va, rsz, ptr = struct.unpack_from("<IIII", d, o + 8)
            if va <= exp_rva < va + max(vsz, rsz):
                struct.pack_into("<I", d, ptr + (exp_rva - va) + 4, 0)     # export dir TimeDateStamp
    path.write_bytes(bytes(d))


def run_test(exe, *args):
    """Run a test program: natively on Windows, under Wine elsewhere. Returns its exit code.
    Absolute path: Windows resolves a relative program path against the caller's
    directory, not cwd=."""
    exe = HERE / exe
    if WINDOWS:
        return subprocess.run([str(exe), *map(str, args)], cwd=HERE).returncode
    env = dict(os.environ, WINEPREFIX=str(HERE / "build" / "wineprefix"), WINEDEBUG="-all")
    return subprocess.run(["wine", str(exe), *map(str, args)], cwd=HERE, env=env).returncode


def wine_path(p):
    """Host path -> the path a Windows program sees."""
    if WINDOWS:
        return str(p)
    env = dict(os.environ, WINEPREFIX=str(HERE / "build" / "wineprefix"), WINEDEBUG="-all")
    return subprocess.run(["winepath", "-w", str(p)], env=env, capture_output=True, text=True).stdout.strip()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("", "simtest", "selftest"):
        sys.exit(f"usage: build.py [simtest|selftest]   (got {mode!r})")
    if not CC.exists():
        sys.exit(f"compiler not found: {CC}\n  Run setup_tools.py first - it installs llvm-mingw into tools/.")

    (HERE / "build").mkdir(exist_ok=True)
    step([sys.executable, "gen_winmm_exports.py"])
    step([sys.executable, "gen_tuning.py"])

    # No version resource on purpose: Wine >= 11.6 then prefers it without an override.
    out = os.environ.get("OUT", "build/winmm.dll")
    extra = shlex.split(os.environ.get("EXTRA_CFLAGS", ""))
    step([CC, *FLAGS, "-shared", "src/betterflight.c", "src/winmm.def", *SRCS, *extra, *LIBS, "-o", out])
    zero_timestamps(HERE / out)
    print(f"built {(HERE / out).stat().st_size} bytes -> {out}", flush=True)

    if mode == "simtest":
        step([CC, *FLAGS, "-DBF_SIMTEST", "src/betterflight.c", *SRCS, *LIBS, "-o", "build/simtest.exe"])
        sys.exit(run_test("build/simtest.exe"))

    if mode == "selftest":
        step([CC, *FLAGS, "-municode", "-DBF_SELFTEST", "src/betterflight.c", *SRCS, *LIBS, "-o", "build/selftest.exe"])
        sys.path.insert(0, str(HERE.parent))
        import common as C
        sys.exit(run_test("build/selftest.exe", wine_path(C.GAME / "Binaries" / "NMS.exe")))


if __name__ == "__main__":
    main()
