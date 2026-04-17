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

- `gothic.player` — the active hero (`position`, `hp`, `alive`, …)
- `gothic.world` — the loaded world (`time`, `npcs`, `set_time(h, m)`,
  …)
- `gothic.reload(name)` — hot-reload a previously-imported module.

Mutations are safe only from the main thread. The Marvin console pump
is on the main thread, so anything you type into `py …` is fine. Don't
call engine mutations from worker threads.
