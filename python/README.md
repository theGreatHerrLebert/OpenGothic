# Python scripts for OpenGothic

Any `.py` file in this directory is importable from the Marvin `py`
REPL (F2). The engine adds `$CWD/python/` to `sys.path` at startup, so
launching the game from the repo root picks this folder up.

## Auto-exec

`init.py` — if present — runs in the REPL's persistent global namespace
as soon as the interpreter initializes. Any names imported/defined
there are available the moment you open the console.

## Workflow

1. Edit a module in this directory (e.g. `tools.py`) in your normal
   editor.
2. In game, press **F2** to open the console.
3. Call it: `py where()` (if `init.py` imports it) or
   `py import tools; tools.where()`.
4. Save your edits. In game: `py gothic.reload("tools")`. Next call
   runs the new code — no game restart.

## The `gothic` module

See `game/script/pybindings.cpp` for the full surface. Current
highlights:

- `gothic.player` — the active hero. Read: `position`, `rotation`,
  `hp`, `hp_max`, `alive`, `name`. Mutate: `set_position(x, y, z)`,
  `set_hp(hp)`, `heal()`.
- `gothic.world` — the loaded world. Read: `time`, `day`, `tick_count`,
  `npc_count`, `npcs`. Mutate: `set_time(h, m)`.
- `gothic.Npc` — other NPCs (`position`, `name`, `hp`, `alive`,
  `set_position`, `heal`).
- `gothic.reload(name)` — hot-reload a previously-imported module.
- `gothic.on_tick(fn)` / `gothic.clear_tick_callbacks()` — register a
  Python callable that runs every simulation tick with `dt` (ms) as
  argument. Callbacks that raise are logged, not fatal.

### `gothic.daedalus` — bridge to the live Daedalus VM

Instead of rebinding every engine extern in C++, we expose a single
gateway. Any Daedalus function registered by name — engine externs *or*
shipped game scripts — is callable from Python:

```python
gothic.daedalus.call("Hlp_GetCurrentHour")       # returns an int
gothic.daedalus.call("Wld_SetTime", 12, 0)        # no return
gothic.daedalus.get("hero")                       # symbol index of hero
gothic.daedalus.get("FIGHT_STRAFEDISTANCE")       # INT/FLOAT/STRING global
gothic.daedalus.set("FIGHT_STRAFEDISTANCE", 500)
```

Argument marshaling supports `int`, `float`, `bool`, `str`,
`gothic.Player`, and `gothic.Npc`. NPC-shaped args get pushed as live
Daedalus instances, so externs like `Npc_ChangeAttribute(slf, atr, v)`
work:

```python
gothic.daedalus.call(
    "Npc_ChangeAttribute",
    gothic.player,
    0,    # ATR_HITPOINTS
    -10,  # delta
)
```

Return values of INT / FLOAT / STRING come back as the matching Python
type. INSTANCE returns are reported as the underlying symbol index for
now — correlating them back to `PyNpc` wrappers is future work.

## External REPL bridge (opt-in)

Launch Gothic with `OPENGOTHIC_PY_BRIDGE=1` to enable a filesystem REPL
bridge — an external process can send Python snippets into the running
game without going through the Marvin console:

```sh
OPENGOTHIC_PY_BRIDGE=1 ./build/opengothic/Gothic2Notr -g "$HOME/Games/GothicII-Gold"

# From another terminal / tool:
scripts/pyeval 'gothic.player.position'
scripts/pyeval 'gothic.player.set_hp(50)'
scripts/pyeval 'sum(n.hp for n in gothic.world.npcs if n.alive)'
```

Semantics are identical to typing into Marvin — the snippet runs on the
main thread via `PythonVM::eval()`. The bridge is polled from
`World::tick()`, so **a world must be loaded** before requests are
processed (main menu is idle).

Bridge layout: `/tmp/opengothic-$USER-bridge/{in,processing,out}`. Write
to `in/<id>.py`, read reply from `out/<id>.out` (first line is `OK` or
`ERR`, body follows). Override the root with
`OPENGOTHIC_PY_BRIDGE_DIR=/some/path` on both sides.

Security: opt-in, user-scoped path. Don't enable on a machine other
users can access unless you're comfortable giving them `exec` on the
game's Python runtime.

## Thread safety

Mutations are safe only from the main thread. The Marvin console pump
is on the main thread, so anything you type into `py …` is fine. Don't
call engine mutations from worker threads.
