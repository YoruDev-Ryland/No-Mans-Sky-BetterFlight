import os
import sys
import shutil
import subprocess
import configparser
import re
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path

GAME_DIR = Path(r"A:\SteamLibrary\steamapps\common\No Man's Sky")
TOOLS_DIR = GAME_DIR / "_BetterFlight_src" / "tools" / "win"
HGPAK = TOOLS_DIR / "hgpaktool.exe"
MBINC = TOOLS_DIR / "MBINCompiler.exe"
PAK = GAME_DIR / "GAMEDATA" / "PCBANKS" / "NMSARC.MetadataEtc.pak"
MODS_DIR = GAME_DIR / "GAMEDATA" / "MODS"
MOD_NAME = "BetterFlightControls"
CONTROLS_INI = GAME_DIR / "Binaries" / "BetterFlight.ini"
WORK_DIR = GAME_DIR / "_BetterFlight_src" / "work" / "controls_win"

FILES = {
    "keyboard": "gcinputbindings_win_keyboard",
    "mouse": "gcinputbindings_win_mouse"
}
EQUIV = {"LCtrl": "Ctrl", "RCtrl": "Ctrl", "LShift": "Shift", "RShift": "Shift", "LAlt": "Alt", "RAlt": "Alt"}
HARMLESS = {"TextChatPasteHold"}

def tokens(spec):
    return [t for t in re.split(r"[,\s]+", spec or "") if t]

def is_mouse(tok):
    return tok.lower().startswith("mouse")

def load_ini(path):
    cp = configparser.ConfigParser(inline_comment_prefixes=(";", "#"), strict=False)
    cp.optionxform = str
    cp.read(path, encoding="utf-8")
    return cp

def get(node, name):
    for p in node:
        if p.get("name") == name:
            return p
    return None

def dest(stem):
    return Path("METADATA") / "INPUT" / "BINDINGS" / f"{stem.upper()}.MBIN"

def ship_container(tree):
    for s in list(tree.getroot())[0]:
        t = get(s, "Type")
        if t is not None:
            ast = get(t, "ActionSetType")
            if ast is not None and ast.get("value") == "ShipControls":
                return get(s, "InputBindings")
    sys.exit("ShipControls set not found")

def act(b):
    a = get(b, "Action")
    return get(a, "InputAction").get("value") if a is not None else None

def btn(b):
    btn_elem = get(b, "Button")
    return get(btn_elem, "InputButton").get("value") if btn_elem is not None else None

def axis(b):
    ax = get(b, "Axis")
    return get(ax, "InputAxis").get("value") if ax is not None else None

def make_row(template, action, button):
    n = deepcopy(template)
    get(get(n, "Action"), "InputAction").set("value", action)
    get(get(n, "Button"), "InputButton").set("value", button)
    get(get(n, "Axis"), "InputAxis").set("value", "None")
    return n

def rebind(cont, template, action, inputs):
    rows = [b for b in list(cont) if act(b) == action and axis(b) == "None"]
    old = [btn(b) for b in rows]
    kids = list(cont)
    pos = kids.index(rows[0]) if rows else len(kids)
    for b in rows:
        cont.remove(b)
    for j, inp in enumerate(inputs):
        cont.insert(pos + j, make_row(rows[0] if rows else template, action, inp))
    return old

def apply(trees, cp):
    conts = {k: ship_container(t) for k, t in trees.items()}
    tmpl  = {k: deepcopy(list(c)[0]) for k, c in conts.items()}
    remap = dict(cp["remap"])
    moved, unknown = [], []
    touched = {"keyboard": False, "mouse": False}

    for action, spec in remap.items():
        toks = tokens(spec)
        want = {"keyboard": [t for t in toks if not is_mouse(t)], "mouse": [t for t in toks if is_mouse(t)]}
        present = any(act(b) == action for c in conts.values() for b in c)
        if not present:
            unknown.append(action)
            continue
        old = []
        for kind in ("keyboard", "mouse"):
            had = any(act(b) == action and axis(b) == "None" for b in conts[kind])
            if had or want[kind]:
                old += rebind(conts[kind], tmpl[kind], action, want[kind])
                touched[kind] = True
        moved.append((action, "+".join(old) or "-", "+".join(toks) or "(unbound)"))

    for c in conts.values():
        for i, b in enumerate(list(c)):
            b.set("_index", str(i))

    return conts, moved, unknown, touched

def main():
    print("=== BetterFlight Controls Mod Builder ===")
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Extrair os arquivos de bindings do pak
    print("1. Extraindo arquivos de bindings do NMSARC.MetadataEtc.pak...")
    for kind, stem in FILES.items():
        print(f"   Extraindo {stem}...")
        r = subprocess.run([str(HGPAK), "--platform", "windows", "-f", f"*{stem}*", "-O", str(WORK_DIR), str(PAK)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"Erro ao extrair {stem}:\n{r.stderr}")
            sys.exit(1)

    mxml_paths = {}
    for kind, stem in FILES.items():
        # Procurar o mbin extraído
        found = list(WORK_DIR.rglob(f"{stem}.mbin"))
        if not found:
            print(f"Arquivo {stem}.mbin nao encontrado na pasta de extracao!")
            sys.exit(1)
        src_mbin = found[0]
        dest_mbin = WORK_DIR / f"{stem}.mbin"
        if src_mbin != dest_mbin:
            shutil.copy2(src_mbin, dest_mbin)
            
        print(f"2. Decompilando {stem}.mbin para MXML...")
        r = subprocess.run([str(MBINC), "-y", str(dest_mbin)], capture_output=True, text=True)
        dest_mxml = dest_mbin.with_suffix(".MXML")
        if not dest_mxml.exists():
            print(f"Falha ao gerar MXML para {stem}:\n{r.stdout}\n{r.stderr}")
            sys.exit(1)
        mxml_paths[kind] = dest_mxml

    # 3. Ler o INI e aplicar as alterações
    print("3. Carregando BetterFlight.ini e aplicando remaps...")
    cp = load_ini(CONTROLS_INI)
    trees = {kind: ET.parse(p) for kind, p in mxml_paths.items()}
    conts, moved, unknown, touched = apply(trees, cp)

    print("\nAções vanilla remapeadas:")
    for action, old, new in moved:
        print(f"   {action:24s} {old:>14s} -> {new}")
    for u in unknown:
        print(f"   [AVISO] {u}: não encontrado em ShipControls - ignorado")

    # 4. Salvar e recompilar MXML para MBIN
    built = {}
    for kind, tree in trees.items():
        if not touched[kind]:
            continue
        p = mxml_paths[kind]
        tree.write(p, encoding="utf-8", xml_declaration=True)
        print(f"\n4. Recompilando {kind} ({p.name}) para MBIN...")
        r = subprocess.run([str(MBINC), "-y", str(p)], capture_output=True, text=True)
        out_mbin = p.with_suffix(".MBIN")
        if not out_mbin.exists():
            print(f"Falha ao compilar {kind}:\n{r.stdout}\n{r.stderr}")
            sys.exit(1)
        built[kind] = out_mbin

    # 5. Instalar em GAMEDATA\MODS\BetterFlightControls
    dest_mod_dir = MODS_DIR / MOD_NAME
    if dest_mod_dir.exists():
        shutil.rmtree(dest_mod_dir)

    for kind, out in built.items():
        target = dest_mod_dir / dest(FILES[kind])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out, target)
        print(f"   Instalado: {target}")

    print("\n[SUCESSO] Mod BetterFlightControls instalado com sucesso!")

if __name__ == "__main__":
    main()
