#!/usr/bin/env python3
"""
Better Flight - one-shot installer.

Installs everything, from controls.ini:
  1. GAMEDATA/MODS/BetterFlightControls  vanilla key relocation    (controls_mod.py)
  2. Binaries/winmm.dll + BetterFlight.ini   native mod: strafe, coupled flight
     and the flight retune (applied in memory since 1.2.0; the old
     GAMEDATA/MODS/BetterFlight data mod is removed if present)
  3. Linux only: the Wine DLL override for NMS.exe, written into the Proton
     prefix registry, so no Steam launch option is needed.

    ./install.py              install / update everything
    ./install.py --status     report what is installed, change nothing
    ./install.py --uninstall  remove everything, restore the registry entry

Refuses to run while No Man's Sky is running: Wine rewrites the registry on exit
(which would silently drop the override) and the game holds its files open.
"""
import argparse, os, re, shutil, subprocess, sys, time
from pathlib import Path
import common as C

BIN      = C.GAME / "Binaries"
DLL_SRC  = C.ROOT / "native" / "build" / "winmm.dll"
DLL_DST  = BIN / "winmm.dll"
INI_DST  = BIN / "BetterFlight.ini"
LOG      = BIN / "BetterFlight.log"
COMPAT   = C.GAME.parent.parent / "compatdata" / C.APPID
USER_REG = COMPAT / "pfx" / "user.reg"
SECTION  = r"[Software\\Wine\\AppDefaults\\NMS.exe\\DllOverrides]"
MARK     = "winmm"


def game_running():
    return C.game_running()


def sh(cmd):
    if str(cmd[0]).endswith(".py"):          # Windows can't execute .py files directly
        cmd = [sys.executable, *cmd]
    print(f"\n$ {' '.join(str(c) for c in cmd)}")
    r = subprocess.run([str(c) for c in cmd], cwd=C.ROOT)
    if r.returncode != 0:
        sys.exit(f"step failed: {cmd[0]}")


def is_linux_proton():
    return USER_REG.exists()


def reg_has_override(text):
    i = text.find(SECTION)
    if i < 0:
        return False
    block = text[i:].split("\n\n", 1)[0]
    return re.search(r'^"winmm"="native,builtin"$', block, re.M) is not None


def reg_install():
    text = USER_REG.read_text(encoding="utf-8", errors="surrogateescape")
    if reg_has_override(text):
        print("  registry: winmm override already present")
        return
    backup = USER_REG.with_suffix(".reg.betterflight-backup")
    if not backup.exists():
        shutil.copy2(USER_REG, backup)
        print(f"  registry: backed up user.reg -> {backup.name}")
    unix = int(time.time())
    ft = (unix + 11644473600) * 10_000_000
    i = text.find(SECTION)
    if i >= 0:                                     # section exists, add our value
        head, rest = text[:i], text[i:]
        first_nl = rest.find("\n")
        # skip the "#time=" line if present
        insert_at = first_nl + 1
        if rest[insert_at:].startswith("#time="):
            insert_at = rest.find("\n", insert_at) + 1
        rest = rest[:insert_at] + '"winmm"="native,builtin"\n' + rest[insert_at:]
        text = head + rest
    else:
        if not text.endswith("\n"):
            text += "\n"
        text += f'\n{SECTION} {unix}\n#time={ft:x}\n"winmm"="native,builtin"\n'
    USER_REG.write_text(text, encoding="utf-8", errors="surrogateescape")
    print('  registry: added AppDefaults\\NMS.exe\\DllOverrides "winmm"="native,builtin"')


def reg_uninstall():
    """Exact inverse of reg_install: delete only our value line. Drop the section
    only if that leaves it with no values, along with the blank line before it."""
    if not USER_REG.exists():
        return
    text = USER_REG.read_text(encoding="utf-8", errors="surrogateescape")
    i = text.find(SECTION)
    if i < 0:
        return
    k = text.find("\n\n", i)
    end = len(text) if k < 0 else k + 1              # block ends with its own '\n'
    block = text[i:end]
    line = '"winmm"="native,builtin"\n'
    if line not in block:
        return
    block = block.replace(line, "", 1)
    values = [l for l in block.splitlines()[1:] if l and not l.startswith("#")]
    if values:
        text = text[:i] + block + text[end:]
    else:
        start = i - 1 if i >= 2 and text[i - 1] == "\n" and text[i - 2] == "\n" else i
        text = text[:start] + text[end:]
    USER_REG.write_text(text, encoding="utf-8", errors="surrogateescape")
    print("  registry: removed winmm override")


def status():
    bid, _ = C.game_build()
    st = C.load_state()
    print(f"  game          : {C.GAME}")
    print(f"  steam build   : {bid}   toolchain validated for: {st.get('steam_buildid')}"
          f"  -> {'CURRENT' if st.get('steam_buildid') == bid else 'STALE (./setup_tools.py)'}")
    print(f"  game running  : {'YES' if game_running() else 'no'}")
    for m in ("BetterFlight", "BetterFlightControls", "StrafeTest"):
        print(f"  mod {m:22s}: {'installed' if (C.MODS / m).exists() else '-'}")
    print(f"  winmm.dll     : {'installed' if DLL_DST.exists() else '-'}"
          f"{'  (matches build)' if DLL_DST.exists() and DLL_SRC.exists() and DLL_DST.read_bytes() == DLL_SRC.read_bytes() else ''}")
    print(f"  BetterFlight.ini: {'installed' if INI_DST.exists() else '-'}")
    if is_linux_proton():
        ok = reg_has_override(USER_REG.read_text(encoding='utf-8', errors='surrogateescape'))
        print(f"  wine override : {'present' if ok else 'MISSING'}")
    if LOG.exists():
        print(f"\n  --- last lines of {LOG.name} ---")
        for line in LOG.read_text(errors="replace").splitlines()[-12:]:
            print("   ", line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    a = ap.parse_args()

    if a.status:
        status(); return

    if game_running():
        sys.exit("\n  No Man's Sky is running. Quit the game first, then re-run.\n"
                 "  (Wine rewrites the registry on exit and the game holds its files open.)\n")

    if a.uninstall:
        sh([C.ROOT / "build_mod.py", "--uninstall"])
        sh([C.ROOT / "controls_mod.py", "--uninstall"])
        for p in (DLL_DST, INI_DST, LOG):
            if p.exists():
                p.unlink(); print(f"  removed {p}")
        reg_uninstall()
        print("\n  Better Flight fully removed.")
        return

    C.require_current_toolchain()
    sh([C.ROOT / "build_mod.py", "--uninstall"])   # the DLL applies the retune now
    sh([C.ROOT / "controls_mod.py"])
    sh([C.ROOT / "native" / "build.py"])

    shutil.copy2(DLL_SRC, DLL_DST)
    shutil.copy2(C.ROOT / "controls.ini", INI_DST)
    print(f"\n  installed {DLL_DST}\n  installed {INI_DST}")
    if is_linux_proton():
        reg_install()
    else:
        print("  (no Proton prefix found - on Windows no override is needed)")
    print("""
  Done. Launch No Man's Sky normally.

  Check it worked:  ./install.py --status   (shows the tail of BetterFlight.log)
  Tune live:        edit  Binaries/BetterFlight.ini  while flying
""")


if __name__ == "__main__":
    main()
