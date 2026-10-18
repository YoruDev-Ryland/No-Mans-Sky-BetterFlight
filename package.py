#!/usr/bin/env python3
"""
Build a Nexus-ready release zip against the currently installed game build.

    ./package.py      -> dist/BetterFlight-<version>-steambuild<id>.zip

Everything is rebuilt from source and verified first: data mods round-trip
checked against the real game files, DLL self-tested against the real NMS.exe.
The shipped BetterFlight.ini has debug logging turned off.

The zip mirrors the game folder, so players extract it straight into
"No Man's Sky/". Docs go in BetterFlight-docs/.
"""
import hashlib, re, shutil, subprocess, sys, zipfile
from pathlib import Path
import common as C

VERSION = "1.2.1"
DIST    = C.ROOT / "dist"
REL     = C.ROOT / "release"


def sh(cmd):
    if str(cmd[0]).endswith(".py"):          # Windows can't execute .py files directly
        cmd = [sys.executable, *cmd]
    r = subprocess.run([str(c) for c in cmd], cwd=C.ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"\n  step failed: {' '.join(map(str, cmd))}\n{r.stdout}\n{r.stderr}")
    return r.stdout


def dll_version():
    src = (C.ROOT / "native" / "src" / "betterflight.c").read_text(encoding="utf-8")
    return re.search(r'#define BF_VERSION "([^"]+)"', src).group(1)


def release_ini():
    s = (C.ROOT / "controls.ini").read_text(encoding="utf-8")
    s = re.sub(r"^(Debug\s*=\s*)\d+", r"\g<1>0", s, flags=re.M)
    if not re.search(r"^Debug\s*=\s*0\s*$", s, re.M):
        sys.exit("could not force Debug = 0 in the release ini")
    return s


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    st = C.require_current_toolchain()
    bid, _ = C.game_build()
    if dll_version() != VERSION:
        sys.exit(f"version mismatch: package.py says {VERSION}, DLL says {dll_version()}")

    print(f"Better Flight {VERSION}  |  Steam build {bid}  |  toolchain {st['mbincompiler']}\n")
    print("  building control remap ...");      sh([C.ROOT / "controls_mod.py", "--build"])
    print("  flight simulator tests ...")
    out = sh([C.ROOT / "native" / "build.py", "simtest"])
    if "SIMTEST PASS" not in out:
        sys.exit("flight simulator tests failed:\n" + out)
    print("  building + self-testing DLL ...")
    out = sh([C.ROOT / "native" / "build.py", "selftest"])
    if "SELFTEST PASS" not in out:
        sys.exit("DLL self-test failed:\n" + out)

    name  = f"BetterFlight-{VERSION}"
    stage = DIST / name
    shutil.rmtree(stage, ignore_errors=True)

    payload = {
        "GAMEDATA/MODS/BetterFlightControls/METADATA/INPUT/BINDINGS/GCINPUTBINDINGS_WIN_KEYBOARD.MBIN":
            C.WORK / "controls" / "gcinputbindings_win_keyboard.MBIN",
        "Binaries/winmm.dll":                          C.ROOT / "native" / "build" / "winmm.dll",
        "BetterFlight-docs/README.txt":                REL / "README.txt",
        "BetterFlight-docs/LICENSE.txt":               C.ROOT / "LICENSE",
        "BetterFlight-docs/THIRD-PARTY-LICENSES.txt":  C.ROOT / "THIRD-PARTY-LICENSES.txt",
        "BetterFlight-docs/linux_wine_override.py":    REL / "linux_wine_override.py",
    }
    for rel, src in payload.items():
        if not src.exists():
            sys.exit(f"missing build output or doc: {src}")
        dst = stage / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    # LF and UTF-8 on every OS: the release must not depend on where it was built
    (stage / "Binaries" / "BetterFlight.ini").write_bytes(release_ini().encode("utf-8"))
    readme = stage / "BetterFlight-docs" / "README.txt"
    text = readme.read_text(encoding="utf-8").replace("{VERSION}", VERSION).replace("{BUILD}", bid)
    readme.write_bytes(text.encode("utf-8"))

    DIST.mkdir(exist_ok=True)
    zpath = DIST / f"{name}-steambuild{bid}.zip"
    zpath.unlink(missing_ok=True)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(stage.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(stage).as_posix())

    print(f"\n  {zpath.relative_to(C.ROOT)}  ({zpath.stat().st_size:,} bytes)\n")
    with zipfile.ZipFile(zpath) as z:
        for i in z.infolist():
            print(f"    {i.file_size:>9,}  {i.filename}")
    print(f"\n  sha256 zip       {sha256(zpath)}")
    print(f"  sha256 winmm.dll {sha256(stage / 'Binaries' / 'winmm.dll')}")
    nexus = REL / "nexus_description.bbcode"
    if nexus.exists():
        shutil.copy2(nexus, DIST / "nexus_description.bbcode")
        print(f"  Nexus page text  -> {(DIST / 'nexus_description.bbcode').relative_to(C.ROOT)}")


if __name__ == "__main__":
    main()
