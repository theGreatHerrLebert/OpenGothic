# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

OpenGothic is an open-source re-implementation of the **Gothic 2: Night of the Raven** game client. It ships no assets — it loads the original Gothic 2 install via the `-g <path>` CLI argument. Development is focused on Gothic 2; Gothic 1 is tolerated but not actively tested. See `README.md` for the full CLI argument list (renderer toggles, world/save loading, `-devmode` etc.).

## Build

- Requires a recursive submodule checkout (`git clone --recurse-submodules` / `git submodule update --init --recursive`).
- Toolchain: CMake ≥ 3.16, C++20. `glslangValidator` must be on PATH — shaders are compiled to SPIR-V at build time and linked as the `GothicShaders` static library (`sprv/shader.{h,cpp}` is generated into the build tree).
- Configure + build:
  ```bash
  cmake -B build -DCMAKE_BUILD_TYPE=RelWithDebInfo
  cmake --build build --target Gothic2Notr -j
  ```
  Output: `build/opengothic/Gothic2Notr`.
- `-Werror -Wall -Wconversion` is on for all non-MSVC builds — warnings break the build.
- `CMAKE_BUILD_TYPE=Debug` automatically adds AddressSanitizer + LeakSanitizer (compile and link flags).
- There is **no test suite**. Validation is manual: run the binary against real game data.
- CI (`.github/workflows/build.yml`) generates `game/build.h` with a version string. A committed `game/build.h` already exists locally; if you remove or regenerate it, keep a valid `appBuild` definition so `main.cpp` still links.
- Platform renderers: Vulkan (Linux/Windows), DirectX 12 (Windows, `-dx12`), Metal (macOS, auto). On macOS, ray query and mesh shading are off by default.

## High-level architecture

### Entry flow
`game/main.cpp` → picks a graphics API → creates `Tempest::Device`, `Resources`, `Gothic` (singleton, `Gothic::inst()`), `GameMusic`, then `MainWindow` → `Tempest::Application::exec()` drives the event loop. Almost everything in the engine reaches back to `Gothic::inst()` for game-global state.

### Source layout (`game/`)
- `gothic.*` — global game state/options; owns `GameSession`, exposes script/definition singletons, camera/sound/fight-AI definitions, and load/save orchestration.
- `commandline.*` — parses CLI flags; exposes toggles (`isRayQuery`, `isMeshShading`, `isVirtualShadow`, `isDevMode`, `doForceG1`/`G2`/`G2NR`, …) that feature code queries directly.
- `mainwindow.*` — Tempest `Window` subclass; input routing, top-level UI, calls into `Renderer`.
- `marvin.*` — in-game developer console (the “Marvin mode” activated by `-devmode`).
- `resources.*` — asset loader built on `ZenKit` plus VDF archives; texture/mesh/animation caches.
- `camera.*` — gameplay camera; driven by `CameraDefinitions` (script data).

- `game/` — high-level game logic
  - `gamesession.*` — a running session; owns the active `World` and world-state cache for inactive worlds (`worldstatestorage.*`).
  - `gamescript.*` — the bridge to the embedded **Daedalus VM** (from ZenKit). All original Gothic scripting runs here; `GameScript` wires VM externs to engine-side `Npc`/`Item`/`World` callbacks. This is the single biggest surface area.
  - `serialize.*` — save-game binary format; every serializable object implements `load(Serialize&)`/`save(Serialize&)` with version gating.
  - `playercontrol.*`, `movealgo.*`, `fightalgo.*`, `damagecalculator.*`, `aistate.*`, `aiouputpipe.*` — gameplay systems called from script or input.
  - `definitions/` — typed wrappers around script-defined tables (cameras, sounds, SVMs, particles, spells, VFX, FightAI). Populated when scripts are first loaded, queried by gameplay code.
  - `compatibility/` — partial emulation for Ikarus/LeGo-style mods: `mem32`, `directmemory`, `phoenix`. These implement a simulated 32-bit address space so a handful of memory-hack script patterns still work. Full Ikarus/LeGo/Union support is out of scope (see README).

- `world/` — the live world instance
  - `world.*` + `worldobjects.*` — containers and id lookup for `Npc`, `Item`, `Interactive`, `Bullet`, VOBs.
  - `objects/` — entity types (`npc`, `item`, `interactive`, `vob`, `staticobj`, `pfxemitter`, `fireplace`, `sound`, …).
  - `triggers/` — ZEN trigger VOBs (mover, touch-damage, codemaster, cutscene-camera, message filter, …). Each subclasses `AbstractTrigger`.
  - `waymatrix.*`, `waypath.*`, `waypoint.*` — NPC navigation graph loaded from the world.
  - `spaceindex.*` — spatial index used for focus/AOI queries.
  - `aiqueue.*`, `focus.*` — AI scheduling and the player’s focus/targeting system.

- `graphics/` — renderer, built on **Tempest** (Vulkan/DX12/Metal abstraction from `lib/Tempest`)
  - `renderer.*` — per-frame orchestrator; selects passes based on CommandLine toggles (volumetrics, epipolar sky, path-trace, RT-GI, virtual shadows, software RT).
  - `worldview.*` — per-world draw list; talks to `visualobjects`, `meshobjects`, `lightgroup`, `pfx/`.
  - `drawcommands.*`, `drawclusters.*`, `drawbuckets.*`, `instancestorage.*` — cluster/meshlet-style GPU submission; mesh-shader path lives here.
  - `mesh/` — skeletal animation (`animation`, `animationsolver`, `pose`, `skeleton`), landscape, proto/static/packed meshes under `submesh/`.
  - `pfx/` — particle buckets and emitters.
  - `sky/`, plus `shader/sky/` + `shader/epipolar/` — atmospheric sky + volumetric fog.
  - `rtscene.*` — TLAS/BLAS management for ray-query / RT-GI.
  - `shaders.*` — `Tempest::RenderPipeline` cache keyed by material + feature flags; materials map 1:1 to `shader/materials/*`.

- `physics/` — thin Bullet 2 wrappers (`dynamicworld`, `collisionworld`, `physicmesh`, `physicvbo`). Characters and bullets are kinematic; static world geometry lives in `PhysicMeshShape`.

- `sound/` + `game/gamemusic.*` + `dmusic/` — SFX via Tempest audio, music via `lib/dmusic` (DirectMusic reimplementation), MIDI via TinySoundFont.

- `ui/` — in-game menus (`gamemenu`, `dialogmenu`, `inventorymenu`, `documentmenu`, `chapterscreen`, `consolewidget`) and the `videowidget` (plays Bink via `game/bink/`).

- `utils/` — `Workers` thread pool, `KeyCodec`, `InstallDetect` (platform-specific Gothic path detection — `.mm` on macOS/iOS), `CrashLog`, INI parsing.

### `shader/`
GLSL sources grouped by function (`materials/`, `lighting/`, `lighting/rt/`, `sky/`, `epipolar/`, `virtual_shadow/`, `rtsm/`, `swrt/`, `software_rendering/`, `ssao/`, `antialiasing/`, `upscale/`, `water/`, `hiz/`, `inventory/`, `bink/`). `shader/CMakeLists.txt` enumerates every pipeline variant (preprocessor defines, target env, workgroup size) and produces the `GothicShaders` library. New shaders must be added to that CMake list — the `file(GLOB_RECURSE …)` only controls dependency tracking, not which pipelines are built.

### `lib/` (submodules)
- `Tempest/` — rendering + window + audio engine. The renderer’s type vocabulary (`Tempest::Device`, `RenderPipeline`, `Encoder<CommandBuffer>`, `StorageImage`, `AccelerationStructure`, …) all come from here. Engine features are gated on `Tempest::Device::properties()`.
- `ZenKit/` — reads Gothic VDF archives, ZEN worlds, models, animations, and hosts the Daedalus script VM. Always prefer ZenKit APIs over reimplementing parsers.
- `bullet3/` — used as Bullet 2 only (`BULLET2_MULTITHREADING=ON`, Bullet 3 disabled).
- `dmusic/`, `TinySoundFont/`, `miniz/`, `edd-dbg/` (Windows crash backtraces only).

## Conventions worth knowing

- Many systems are reached via the `Gothic::inst()` / `CommandLine::inst()` singletons. When adding a feature gate, pipe it through `CommandLine` + `Gothic::Options` rather than a new global.
- Save-game compatibility is enforced by version gating inside `Serialize`. Changing a persisted field requires bumping the version and handling the old layout.
- Script-visible data types live in `game/game/definitions/`. Parsing is done once at script-load time and the parsed structs are queried by gameplay code — don’t re-read DAT files at runtime.
- Daedalus extern bindings (script → C++) all live in `GameScript`; adding a new extern means registering it there and keeping the signature in sync with the Gothic script API.
- Warnings are errors: `-Wconversion` in particular rejects implicit narrowing. Be explicit about `size_t`/`uint32_t`/`int32_t` conversions.
