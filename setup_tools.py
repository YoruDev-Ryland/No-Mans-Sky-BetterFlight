#!/usr/bin/env python3
"""
Validate the toolchain against the *installed* game build.

MBINCompiler versions are tied to game versions. Using the wrong one does not
fail loudly - it emits silently misaligned data. So we don't guess: we probe
released versions against a real game file and keep the first one whose
decompile+recompile round-trip reproduces the data bytes exactly.

Run this after every No Man's Sky update. It also installs, user-local, every
tool the build needs: .NET 8 runtime, HGPAKtool, MBINCompiler and llvm-mingw.
Linux and Windows.

    python3 setup_tools.py            # probe and install the correct version
    python3 setup_tools.py --force    # re-probe even if state looks current
    python3 setup_tools.py --check    # report only, change nothing
"""
import argparse, hashlib, io, json, shutil, sys, tarfile, zipfile
from pathlib import Path
import common as C

PROBE_FILE = "gcspaceshipglobals.global.mbin"   # the file we actually care about

HGPAK_URL = "https://github.com/monkeyman192/HGPAKtool/releases/download/1.1.3/"
# The compiler is pinned: the same version on every machine keeps builds reproducible.
LLVM_MINGW = "20260908"
LLVM_MINGW_URL = f"https://github.com/mstorsjo/llvm-mingw/releases/download/{LLVM_MINGW}/"
LLVM_DIR = C.TOOLS/"llvm-mingw"
CLANG = LLVM_DIR/"bin"/("x86_64-w64-mingw32-clang.exe" if C.WINDOWS else "x86_64-w64-mingw32-clang")
DOTNET_INDEX = "https://builds.dotnet.microsoft.com/dotnet/release-metadata/8.0/releases.json"


def ensure_hgpaktool():
    if C.HGPAK.exists():
        return
    print("  fetching HGPAKtool ...")
    C.TOOLS.mkdir(parents=True, exist_ok=True)
    if C.WINDOWS:
        with zipfile.ZipFile(io.BytesIO(C._get(HGPAK_URL + "hgpaktool-x86_64-pc-windows.zip"))) as z:
            member = next(n for n in z.namelist() if n.lower().endswith("hgpaktool.exe"))
            C.HGPAK.write_bytes(z.read(member))
        return
    import gzip
    C.HGPAK.write_bytes(gzip.decompress(C._get(HGPAK_URL + "hgpaktool-x86_64-unknown-linux.gz")))
    C.HGPAK.chmod(0o755)


def ensure_llvm_mingw():
    """The C compiler for the DLL. Unpacked into tools/llvm-mingw."""
    if CLANG.exists():
        return
    asset = (f"llvm-mingw-{LLVM_MINGW}-ucrt-x86_64.zip" if C.WINDOWS
             else f"llvm-mingw-{LLVM_MINGW}-ucrt-ubuntu-22.04-x86_64.tar.xz")
    print(f"  fetching llvm-mingw {LLVM_MINGW} (C compiler, ~150 MB) ...")
    data = C._get(LLVM_MINGW_URL + asset)
    tmp = C.TOOLS/"_llvm-mingw-unpack"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    if C.WINDOWS:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extractall(tmp)
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as t:
            if hasattr(tarfile, "data_filter"):
                t.extractall(tmp, filter="data")
            else:
                t.extractall(tmp)
    top = [p for p in tmp.iterdir() if p.is_dir()]
    if len(top) != 1:
        sys.exit(f"unexpected llvm-mingw archive layout: {[p.name for p in tmp.iterdir()]}")
    shutil.rmtree(LLVM_DIR, ignore_errors=True)
    top[0].rename(LLVM_DIR)
    shutil.rmtree(tmp, ignore_errors=True)
    if not CLANG.exists():
        sys.exit(f"llvm-mingw unpacked but {CLANG.name} is missing")


def ensure_dotnet():
    if C.DOTNET_EXE.exists():
        return
    print("  installing .NET 8 runtime (user-local, no admin) ...")
    if C.WINDOWS:
        # Microsoft's official runtime zip, checked against the SHA-512 in their release index.
        rel = json.loads(C._get(DOTNET_INDEX))["releases"][0]["runtime"]
        f = next(f for f in rel["files"] if f.get("rid") == "win-x64" and f["name"].endswith(".zip"))
        data = C._get(f["url"])
        if hashlib.sha512(data).hexdigest().lower() != f["hash"].lower():
            sys.exit(f"downloaded .NET runtime failed its SHA-512 check: {f['url']}")
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extractall(C.DOTNET)
        if not C.DOTNET_EXE.exists():
            sys.exit("dotnet install failed: dotnet.exe missing after unpacking")
        print(f"    .NET runtime {rel['version']} -> {C.DOTNET}")
        return
    import urllib.request
    sh = C.WORK/"dotnet-install.sh"
    C.WORK.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve("https://dot.net/v1/dotnet-install.sh", sh)
    sh.chmod(0o755)
    r = C.run([sh, "--runtime", "dotnet", "--channel", "8.0",
               "--install-dir", C.DOTNET, "--no-path"])
    if not C.DOTNET_EXE.exists():
        sys.exit(f"dotnet install failed:\n{r.stdout}\n{r.stderr}")


def get_probe_mbin():
    out = C.WORK/"probe"
    shutil.rmtree(out, ignore_errors=True)
    C.extract(C.PCBANKS/"NMSARC.globals.pak", "*spaceshipglobals*", out)
    src = next(out.rglob(PROBE_FILE), None)
    if not src:
        sys.exit("could not extract the probe file from NMSARC.globals.pak")
    keep = C.WORK/"probe_vanilla.mbin"
    shutil.copy(src, keep)
    shutil.rmtree(out, ignore_errors=True)
    return keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    bid, nms = C.game_build()
    print(f"\n  game     : {C.GAME}")
    print(f"  build    : steam {bid} / NMS {nms}")

    flags = C.update_in_progress()
    if flags:
        print(f"\n  ⚠  Steam reports an update in progress (StateFlags={flags}).")
        print("     Game files are not final. Re-run this once the update completes.")

    st = C.load_state()
    if a.check:
        ok = st.get("steam_buildid") == bid and C.MBINC.exists()
        print(f"  compiler : {'llvm-mingw installed' if CLANG.exists() else 'MISSING - run setup_tools.py'}")
        print(f"  toolchain: {st.get('mbincompiler','(none)')} "
              f"validated for {st.get('steam_buildid','?')}")
        print(f"  status   : {'CURRENT' if ok else 'STALE - run setup_tools.py'}")
        return

    ensure_llvm_mingw()               # needed for the DLL whatever the game build

    if flags and not a.force:
        return

    if st.get("steam_buildid") == bid and C.MBINC.exists() and not a.force:
        print(f"  toolchain: {st['mbincompiler']} already validated for this build")
        return

    ensure_dotnet()
    ensure_hgpaktool()
    probe = get_probe_mbin()
    print(f"  probe    : {probe.name} ({probe.stat().st_size:,} bytes)")

    tags = C.releases()
    print(f"\n  probing {len(tags)} MBINCompiler releases (newest first)\n")

    scratch = C.WORK/"probe_scratch"
    cache   = C.TOOLS/"candidates"
    winner  = None
    for tag in tags:
        d = cache/tag
        if not (d/C.MBINC.name).exists():
            if not C.fetch_version(tag, d):
                print(f"    {tag:22s} no {'Windows' if C.WINDOWS else 'Linux'} build in this release")
                continue
        ok, why = C.roundtrip_clean(d/C.MBINC.name, probe, scratch)
        print(f"    {tag:22s} {'OK   ' if ok else 'no   '} {why}")
        if ok:
            winner = (tag, d)
            break

    if not winner:
        sys.exit("\n  No MBINCompiler release round-trips cleanly against this build.\n"
                 "  The game is likely newer than any release; wait for an update to\n"
                 "  monkeyman192/MBINCompiler.\n")

    tag, d = winner
    shutil.rmtree(C.MBIN_DIR, ignore_errors=True)
    shutil.copytree(d, C.MBIN_DIR)
    (C.MBIN_DIR/C.MBINC.name).chmod(0o755)
    shutil.rmtree(cache, ignore_errors=True)
    shutil.rmtree(scratch, ignore_errors=True)

    # Extracted vanilla files are per-build. Wipe them so the next build
    # re-extracts from the updated paks instead of reusing stale data.
    stale = [C.WORK/"vanilla", C.WORK/"strafe", C.WORK/"build",
             C.WORK/"probe_vanilla.mbin", C.WORK/"_rt", C.WORK/"_extract"]
    wiped = 0
    for pth in stale:
        if pth.is_dir():
            shutil.rmtree(pth, ignore_errors=True); wiped += 1
        elif pth.exists():
            pth.unlink(); wiped += 1
    for junk in C.WORK.glob("*.MXML"):
        junk.unlink(); wiped += 1
    for junk in C.WORK.glob("*.MBIN"):
        junk.unlink(); wiped += 1
    if wiped:
        print(f"  cleared {wiped} stale cache entries (they belonged to the old build)")

    C.save_state({"steam_buildid": bid, "nms_build": nms, "mbincompiler": tag})
    print(f"\n  installed MBINCompiler {tag} -> tools/mbin/")
    print(f"  validated for steam buildid {bid} / NMS build {nms}")
    print("\n  Next:  python3 install.py   (or package.py for a release zip)\n")


if __name__ == "__main__":
    main()
