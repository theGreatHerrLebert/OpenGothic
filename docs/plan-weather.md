# Plan: weather in the world

Status: plan, not built. Reviewed by Codex before any code.

## Why

The snow we have is a lens: `shader/trip/trip.frag` draws flakes over the finished, tonemapped frame (switched on by
`GlobalFx::snowDensity`, Python `gothic.weather.snow(d)`). It has no depth, falls indoors, settles nowhere and ignores
the scene's light. Gothic 2 had rain; OpenGothic never built it (`GameScript::wld_israining` logs "not implemented").
A weather system the game master can control needs weather in the world.

## What exists to build on

- Frame order (`Renderer::draw`, common/graphics/renderer.cpp ~664–741): visibility, Hi-Z, G-buffer, shadow maps,
  lighting into `sceneLinear` with `zbuffer` read-only, sky, water, then a pass with `sceneLinear` + `zbuffer` (depth
  test, no write) for sun/moon and `WorldView::drawTranslucent` (meshes, then particle buckets), then fog, then
  tonemapping, then the trip pass.
- `SceneGlobals` UBO (sceneglobals.h): view/projection, inverse, shadow matrices, sun direction, time.
- G-buffer material shader `shader/materials/main.frag`: writes diffuse and an encoded normal.
- `World::roomAt(pos)`: the portal room the camera is in ("FORESTHERBERGE01" is the crossroads tavern).
- Sky (`common/graphics/sky/`) with sun intensity, fog and an exposure pipeline.
- Pipelines are listed by hand in `shader/CMakeLists.txt`; `-Werror -Wconversion` on C++.

## Design

### 1. Precipitation as 3D particles (snow first, rain on the same pass)

A new pass `drawPrecipitation`, right after `drawTranslucent` in the same framebuffer (sceneLinear, zbuffer read-only
with depth test), so flakes are hidden behind walls, trees and the hero, and before fog, so distant flakes fade like
everything else.

- **Stateless and procedural.** One instanced draw of N camera-facing quads (snow ~20k, rain ~30k at full intensity;
  N scales with intensity). The vertex shader derives each particle's position from hash(instanceId) and time: a
  box of about 30 × 20 × 30 m centred on the camera, positions wrapped with `mod` so the field is endless and the
  camera never sees an edge. Fall speed, wind vector and a per-flake flutter are uniforms or hashed. No buffers to
  update, no CPU work, no state in the save.
- **Look.** Snow: soft round sprites, size 2–5 cm world space, alpha by distance (near clipping fade, far fade into
  fog). Rain: thin quads stretched along velocity (motion streak), short, faint. Lit by the sky: colour from ambient
  and sun intensity already in the scene globals, so night snow is grey-blue, not white.
- **Blending.** Additive-ish premultiplied alpha into the linear scene, before tonemapping and exposure.

### 2. Not under a roof

- **Version 1 (cheap):** if the camera is in a portal room (`World::roomAt(camera) != ""`), intensity goes to 0 with
  a short fade. Flakes outside seen through a door are wrong for that moment; accepted.
- **Version 2 (proper, later):** a top-down depth map (512² over the precipitation box, orthographic from above,
  static and dynamic geometry), rendered every few frames when the camera moves; a particle whose height is below
  the map's height is discarded. Also gives version 3 its occlusion. Reuses the shadow-map path with a vertical
  light; to be measured for cost.

### 3. On the ground

- **Snow cover:** in `main.frag`, blend the diffuse towards snow white where the normal points up
  (smoothstep on normal.y), scaled by a global `snowCover` (0..1, rising slowly while it snows, melting when it
  stops), with a noise mask so it is patchy. Version 1 has no occlusion (snow also on floors under roofs: indoor
  floors are mostly in rooms, so cover is off when the camera is inside); version 2 uses the top-down depth map.
  Excluded: water, characters (their materials take a flag), sky.
- **Wet (rain):** darken diffuse and raise specular/roughness hint on surfaces facing up, same mask. Puddles later.

### 4. Sky and sound

Couple to the sky module: overcast factor dims sun intensity, raises fog density and lowers visibility; wind and
rain ambience through the game's own sounds where they exist (else our own, like the dice rattle). Lightning later.

### 5. Game and stories

- `GameScript::wld_israining` returns true while it rains (scripts that ask get an answer).
- Python: `gothic.weather.set(kind, intensity, wind=(x, z), cover=None)` replacing the lens-only `snow(d)`; the trip's
  lens snow stays for trips.
- Story op `weather` (validated: kind snow|rain|clear, intensity 0..1, for at most N hours), so a story can use a
  blizzard as an occasion.
- A small Python weather controller: fronts come and go with slow transitions, by chapter and region; its state is
  saved with the story log so a load agrees.

## Order and checks

1. Pass 1 (snow particles) + roof rule v1, Python `weather.set`. Live test: falling snow outside the tavern, none
   inside, hidden behind the house, fading in fog, at day and night. Measure frame time with 0 / 50 / 100 %.
2. Snow cover v1 in `main.frag`, cover rising and melting. Live test on Onar's fields and roofs.
3. Rain on the same pass, wet surfaces, sky coupling, `Wld_IsRaining`.
4. Top-down depth map (roof v2, occlusion for cover) if v1 artefacts bother in play.
5. Story op and controller.

Each step is its own commit; no step changes the save format (weather state goes into the story log, not the game
save).

## Risks and open questions

- Mesh shading and the Metal path: the new pass must be a plain vertex/fragment pipeline that works on all three
  backends (Vulkan, DX12, Metal); no mesh shaders.
- Depth precision: flakes very close to the camera vs. the near plane; fade them out under ~0.5 m.
- Translucent order: particles after the game's own particle buckets may sort wrong against fire and smoke; accept
  for snow, check for rain.
- The G-buffer change touches every material; keep it a single uniform-driven branch so no pipeline variants
  multiply.
- Performance on the user's Mac (Metal): measure before adding version 2.

## Revision after Codex review (2026-11-13)

Codex checked the plan against the engine. Changes, which override the design above where they differ:

0. **State first.** Before any rendering: one authoritative weather state in `GlobalFx` (kind, intensity, wind,
   cover, their target values and fade times), set only from Python. The story log keeps it (`weather` op), so a
   load restores it; a story's weather outranks the controller until it expires. "No flakes indoors" is a render
   decision and never changes `Wld_IsRaining`. The lens snow of trips stays separate.
1. **Particles after fog.** The fog pass only knows the depth of the surface behind a flake. Precipitation is drawn
   after `drawFog` and fogs itself with the fog LUT at its own depth (as `fog.frag` does for surfaces).
2. **Exact pipeline state.** Depth test `LEqual`, no depth write, no culling, premultiplied alpha (`One`,
   `OneMinusSrcAlpha`), colour multiplied by `scene.exposure` like forward materials. Units: world cm.
3. **World-anchored particles.** Positions belong to world-space cells; the camera only chooses which cells are drawn.
   Fade at cell and box edges so nothing pops. Pausing stops the clock.
4. **Cover v1 on landscape only.** The material shader is compiled for landscape, objects, water, characters, ghosts
   and particles; a global branch would whiten them all. v1 covers the landscape G-buffer variant only (no indoor
   floors, which are objects). Objects and roofs follow with the top-down map. World position for the noise mask is
   reconstructed from depth.
5. **Wet v1 = darker albedo only.** There is no roughness/specular channel in the G-buffer; highlights need their own
   lighting work. Snow colour is written in the albedo encoding (`textureAlbedo`).
6. **Roof map is a real view** (own frustum, visibility list and depth target, before the G-buffer), so it is
   budgeted as its own step, not "reuse the shadow map". Sun shadows may light particles, never decide shelter.
7. **Reuse the particle conventions** of `pfx.vert` (billboards, velocity streaks, bindings); a quick look-prototype
   with an existing emitter first is fine.
8. **Measure.** GPU time of the pass by itself, at 0 / 50 / 100 %, looking up and along the ground, near flakes
   capped in size; a real zero-intensity skip.
9. **Raster only in v1.** The path-tracing renderer returns before this pass; weather there is out of scope.
10. **Test list:** transparent windows, water surface, underwater camera, ghosts, night, the tavern door, a load.

Revised order: state + Python API + `Wld_IsRaining` → snow particles (after fog) → landscape cover → rain and dark
wet → roof map (objects, roofs, shelter) → story op and controller.
