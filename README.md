# Better Flight — No Man's Sky

Star Citizen-style flight for No Man's Sky: real strafing, momentum, the ability
to stop, and no forced banking.

The mod runs on Windows and on Linux (Proton) — the same files on both. **Players:**
use the release zip from Nexus, nothing to build. This README is for building from
source, which also works on both. See [RESEARCH.md](RESEARCH.md) for the technical
background.

---

## Build and install from source

Needs Python 3 (3.12+ recommended) and No Man's Sky installed through Steam. On
Linux, also Wine (the DLL's tests run under it; on Windows they run natively).
Everything else is fetched by `setup_tools.py` into `tools/`, user-local, no admin:
.NET 8 runtime, HGPAKtool, MBINCompiler (the version that matches your game build)
and llvm-mingw (the C compiler).

**Quit the game first.** Linux: run the scripts directly (`./install.py`) or with
`python3`. Windows: `py install.py`.

```bash
python3 setup_tools.py        # once, and after every game update
python3 install.py            # builds and installs everything
python3 install.py --status   # what's installed + tail of the in-game log
python3 install.py --uninstall
```

After a game update: `python3 update.py` (`setup_tools.py` then `install.py`).

If the game isn't found, set `NMS_PATH` to the folder containing `Binaries` and
`GAMEDATA`.

On Linux the installer writes the one Wine DLL override the mod needs straight
into the game's Proton prefix (backing up `user.reg` first), so **no Steam launch
option is required**. If you prefer a launch option instead:
`WINEDLLOVERRIDES="winmm=n,b" %command%` — note `n,b`, not `n`; plain `n` breaks it.

---

## Controls

| Key | Action | | Key | Action |
|---|---|---|---|---|
| **W / S** | thrust / brake | | **LShift** | boost |
| **A / D** | **strafe left / right** | | **B** | pulse jump |
| **Space** | **thrust up** | | **N** | land |
| **LCtrl** | **thrust down** | | **F** | exit ship / tag / follow |
| **Q / E** | roll left / right | | **C** | scan |
| **Z** | **coupled / decoupled** | | **F8** | all native features on/off |
| mouse | pitch / yaw (no auto-bank) | | | |

Bold = new. Everything else on the ship keyboard map is unchanged.

**Coupled** (default at launch): every axis you aren't commanding is braked toward
zero as one vector, so releasing the throttle stops the ship along its direction of
travel. **Decoupled**: no braking — velocity is world-fixed through turns and flips.
Above `MomentumMinSpeed` the game's own velocity changes on uncommanded axes are
discarded; below it, and during pulse/landing/follow hand-offs, the game flies.

Any action takes several inputs, mouse buttons included:
`StrafeLeft = KeyA, Mouse4`, `Ship_RollLeft = KeyQ, Mouse4`.

Pulse jump also still fires if both roll keys are held — that's hard-coded game
behaviour, so it moved from A+D to **Q+E**.

All of this lives in [`controls.ini`](controls.ini). Change a key there and re-run
`./install.py`; the build refuses to install a layout where one key does two things
in flight.

---

## Tuning while you play

`Binaries/BetterFlight.ini` is re-read about once a second while flying — edit it
with the game running.

| Setting | Default | |
|---|---|---|
| `LateralAccel` | 70 | strafe thruster, m/s² |
| `VerticalAccel` | 55 | up/down thruster, m/s² |
| `MaxStrafeSpeed` | 140 | strafe won't push that axis past this |
| `RetroAccel` / `MainAccel` | 60 / 120 | coupled braking of forward / backward motion, m/s² |
| `ThrustKey` / `BrakeKey` / `BoostKey` | W / S / LShift | the game's throttle keys, as coupled mode sees them |
| `AutopilotKeys` / `AutopilotSeconds` | N, B, F / 6 | keys that hand control to the game, and for how long |
| `WorldMomentum` / `MomentumMinSpeed` | 1 / 30 | discard the game's velocity changes on uncommanded axes above this speed |
| `DriftSpeedCap` | 3500 | safety cap on sideways + vertical speed |
| `FlightRetune` | 1 | apply the flight retune on top of the loaded flight data (0 restores the loaded values) |
| `InvertLateral` / `InvertVertical` | 0 | flip if a direction is backwards |
| `Debug` | 1 | per-second flight telemetry in `BetterFlight.log` |

The rest of the feel — momentum, stopping, roll coupling — is the flight retune. Its
tables live in `build_mod.py` (`SPACE` / `ATMOS` / `GLOBAL_TUNING`). `native/build.py`
generates `native/src/flight_tuning.inc` from them, and the DLL applies them in memory
(RESEARCH.md §16). Changing a table needs a rebuild; `FlightRetune` works live.

---

## How it works

Built from this repo:

| Piece | Type | Does |
|---|---|---|
| flight retune | in `winmm.dll` | 176 flight values (no yaw→roll coupling, the ship can stop, flight assist cut so momentum exists), found by name via the game's reflection metadata and applied in memory on top of whatever the game loaded, so ship-globals mods such as PTSd still work |
| `BetterFlightControls` | data mod | Moves vanilla roll / pulse / land / exit off the keys strafe needs |
| `winmm.dll` | native mod | Adds strafe. Post-hooks `cGcSpaceshipComponent::UpdateControlled`; each frame reads ship velocity, adds thruster Δv along the ship's own right/up axes, writes it back |

The DLL is loaded because `NMS.exe` imports `winmm.dll`. Once it is loaded under
that name, **every** module in the game process that uses winmm binds to it too
(Steam's client DLL, overlays, frame generation), so it forwards the complete winmm
interface to the real system DLL: all 189 exports of Windows 10/11 plus Wine, at
Windows' own ordinals. The export set is generated by `native/gen_winmm_exports.py`
from the reference lists in `native/reference/`. It hard-codes **nothing** from a game
build: the five functions it needs are found by unique byte signature, and struct
offsets are read out of the matched machine code. If a future patch breaks a
signature, the log names it and the game runs normally without strafe.

### Why strafe needs native code

The game *does* define strafe actions — "Horizontal Thrust" and "Vertical Thrust",
translated into every language. We bound them and proved the binding loaded (a
test key fired the scanner). They do nothing: flatscreen flight code never reads
them. So the DLL supplies the thrust itself.

---

## Troubleshooting

`./install.py --status` shows the end of `Binaries/BetterFlight.log`. A healthy
start looks like:

```
BetterFlight 1.1.0 loaded into NMS.exe (...)
resolved: UpdateControlled=+0x... GetVelocity=+0x... SetLinearVelocity=+0x... GetTransform=+0x...
offsets:  ship->physics=0x6248  physics->rigidbody=0x60  rigidbody->state=0x290
hook installed.
diag: |v|= 120.3  right=   0.4 up=  -1.2 at= 120.2  input x=+0 y=+0  dt=0.0166
```

With `Debug = 1` you get one `diag:` line per second while flying, plus an `input:`
line whenever a strafe key changes. Anything that stops strafe from applying is
logged as `SKIP (...)` with the reason, every few seconds.

| Symptom | Likely cause |
|---|---|
| No log file at all | DLL not loading — on Linux, the override is missing (`--status` checks it) |
| `hook installed` but no `diag:` lines | the flight hook isn't running — open an issue and attach the log |
| `SKIP (...)` lines | strafe found a problem each frame; the reason is in the line |
| `sig ... FAIL` | Game patch changed code; strafe disabled, game unaffected |
| Strafe goes the wrong way | `InvertLateral` / `InvertVertical` |
| A/D still roll | Controls mod not installed, or toolchain stale — run `update.py` |

---

## Making a release

```bash
python3 package.py      # Windows: py package.py
```

Rebuilds everything against the installed game, round-trip-checks the controls data
mod, runs the flight simulator, self-tests the DLL against the real `NMS.exe`, turns
debug logging off in the shipped settings, and writes:

- `dist/BetterFlight-<version>-steambuild<id>.zip` — extract-into-game-folder layout
- `dist/nexus_description.bbcode` — paste into the Nexus description editor
- sha256 of the zip and the DLL

Player docs live in `release/`. Bump `VERSION` in `package.py` and `BF_VERSION`
in `native/src/betterflight.c` together; the packager refuses a mismatch.

Licence: MIT (`LICENSE`). Third-party notices: `THIRD-PARTY-LICENSES.txt`.

---

## Repo layout

```
install.py         one-shot build + install + uninstall (your own game)
package.py         build a Nexus release zip
release/           player README, Nexus page text, Linux override helper
update.py          run after a game update (update.sh: Linux shortcut)
controls.ini       key layout + live tuning (single source of truth)
build_mod.py       flight retune tables (compiled into the DLL; --diff lists them)
controls_mod.py    data: vanilla key relocation
setup_tools.py     installs the toolchain; picks the MBINCompiler matching the game
common.py          game discovery, build detection, round-trip verification
native/            the DLL (C + vendored MinHook), build.py
strafe_test.py     superseded probe that proved the strafe actions are unused
tools/             llvm-mingw, MBINCompiler, HGPAKtool (all user-local, no admin)
```
