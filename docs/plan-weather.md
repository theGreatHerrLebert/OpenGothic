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

## Step 5 as built (2026-11-13)

Instead of a top-down render view with its own visibility (the review's suggestion), the roof map is computed once
per world on the CPU from the static world mesh: the highest non-water surface over each square metre (coarser cells
for a world wider than 2 km), uploaded as an R32F texture. A particle more than 30 cm below it is not drawn. No pass
per frame and the same on every backend; it misses dynamic objects, trees and houses built from vobs rather than the
world mesh, so the room rule stays as a fallback. Using it for snow cover on objects and roofs is still open.

## Ground fog (plan, 2026-11-13)

The engine's fog is atmospheric haze over distance; it has no fog that lies on the ground. Ground fog makes a place:
morning fog in valleys, mist over the swamp, sea fog at the harbour.

- **State:** `fog` (density 0..1, eased like the rest), `fogHeight` (metres it reaches above its base) and a base
  height in world cm: by default a little below the hero's feet when it is set, so he stands in it; a story or the
  climate may set it as a fixed level, so valleys fill and hills stay clear. Python `weather.fog(density, height,
  base=None, fade)`, the weather op gains `fog`; the climate brings morning fog at dawn now and then.
- **Pass:** after `drawFog` and before precipitation, a full-screen fragment pass reads the depth buffer and marches
  the view ray from the camera to the surface (at most 600 m; sky pixels end there): 12 steps of an exponential height
  profile, `exp(-(y-base)/height)`, broken into banks and wisps by world-anchored 3D noise that drifts with the wind.
  In-scattering from the sky's ambient (view LUT) and a forward-scattering phase towards the sun (a glow when looking
  into the light), grey-blue at night; colour and transmittance out, blended as `scene*T + light`.
- **Cost:** full resolution first, measured; half resolution with a depth-aware upsample if it is too slow.
- **Not yet:** shadows in the fog (light shafts), fog over water specially, path tracing.

## Heat (2026-11-13)

A hot day as weather in the world, not the trip's lens (Emberheart's shimmer stays the trip's). For the drought in a
story ("The Mage and the Weather Spell") and for summer afternoons.

- **State:** `heat` 0..1, eased over seconds like the rest; it does not touch the sky, the caller clears it.
  Python `weather.heat(level, fade=120)`; the story op `weather` gains `heat` (and `fog`, `fog_height`, `fog_base`),
  kept in the log like `cover` and set again at once after a load; when a story's hours run out, its heat and fog go.
- **Shimmer:** in the tonemapping pass, which already reads the whole linear scene: a small UV offset of rising waves,
  finer far away, from 15 m and strongest along the ground towards the horizon (none above it). The depth buffer is
  bound there; an offset sample that comes from something nearer than 60 % of the pixel's own distance is not taken,
  so a close silhouette never smears over the distance. No extra pass, no copy of the scene.
- **Light and haze:** the sun's colour harder and warmer, the sky light a little paler and warmer
  (`setWeatherSky`); far land bleached towards a warm grey, by the same distance weight as the shimmer.
- **Dry:** wet ground dries up to five times faster.
- **Talk:** people speak of the heat when it is over 0.4 and nothing falls; farmers of their fields, mercenaries of
  their armour, townsfolk of the stink at the harbour; the hero of the sun and of water.
- **Not yet:** the climate's own hot days, cicadas, sweat, dust devils; the shimmer is a screen effect and does not
  bend reflections.

### Summer: cicadas, crickets, the Milky Way (2026-11-13)

On a hot day (heat over 0.3, full from 0.6) the cicadas saw away from 8:30 to 19:30 unless the sky has closed; on the
warm night after it, under a clear sky (20:30 to 5:30), the crickets sing and the trips' Milky Way stands over the land,
a little warm, without their colours or nebulae, turning slowly. Nothing falling, no summer. `python/dm/summer.py` looks
every two seconds; the engine loops our own WAVs by name (`weather.loop(name, path, volume, fade)`). The sounds are CC0
recordings from Freesound kept with the rest of our runtime assets (`python/dm_runtime/assets/sounds/CREDITS.md`). A trip
owns the sky while it runs; the sounds keep following the weather; a load sets everything again. Not yet: quieter
indoors (the loops are heard everywhere, like the rain).

## Magical weather (plan, 2026-11-13)

Weather no front brings: a story's or a mage's. Three kinds, each built from what exists (the precipitation pass, the
ground fog, the weather sky, lightning, named loops), never chosen by the climate.

- **Fire rain** (`kind="fire"`): embers fall instead of rain: short glowing streaks, slanted, fewer than raindrops
  (about a quarter), each flickering, emissive (orange to yellow, not lit by the sky), blended additively so they glow
  at night. Now and then a meteor: one of a handful of reserved particles placed on a far sky direction (2–6 km), a
  long bright trail crossing the sky in one to two seconds, a few per minute at full intensity. The sky goes a dull red
  (overcast with a red tint in `setWeatherSky`, sun dimmed); the light on the land warm and low. An impact now and
  then: an orange flash (the lightning flash with a colour) and a deep rumble after it. Nothing gets wet; it dries.
- **Crystal storm** (`kind="crystal"`): shards ride a hard wind: snow's paths, faster and straighter, as small
  flat quads that turn and catch the light: a glint where their facing lines up with the sun or the camera
  (sparkle), cold blue-white. The ground frosts: the snow cover with a blue, glassy tint (`frost` instead of white).
  The sky goes cold and pale, cyan-grey; wind loud.
- **Arcane mist** (`kind="motes"`, with `fog`): the ground fog tinted (a colour parameter, violet by default), and
  motes in it: slow, rising and drifting glowing points that pulse, emissive, few (about 2k), denser low near the
  ground. Without fog it is motes in clear air ("magic dust").
- **Engine:** `Precipitation` gains `Fire`, `Crystal`, `Motes`; the precipitation shaders take the kind and switch
  shape, speed, colour and blend (emissive kinds additive: `One, One`; lit kinds as now). `falling()` and
  `isRaining()` keep their meaning for rain and snow only (scripts asking `Wld_IsRaining` hear no for fire). Snow
  cover grows only under snow, frost only under crystal, as one cover value with a tint that eases.
  `setWeatherSky` takes a sky tint (vec3) and how much of it; the fog pass's colour too. `flash` gains a colour.
- **Python:** `weather.set("fire" | "crystal" | "motes", intensity, fade, wind)`, `weather.fog(..., tint=(r,g,b))`;
  `state()` reports kind and the tints. The story op `weather` accepts the three kinds (validated) and `fog_tint`.
  The climate leaves story weather alone as now, and its own fronts never pick these. A fire rain's impacts come from
  a small Python ticker like the storm's lightning.
- **Talk:** fear and wonder, not small talk: "Innos steh uns bei!", "Der Himmel brennt!", "Das ist kein Schnee, das
  ist Glas!"; the mages know what it is ("Das ist kein Wetter. Das ist Magie."). Voices baked as before.
- **Sounds:** the game's own spell sounds where they fit (fire rain, ice, the magic hum), played by name; loops of our
  own only if the game has none.
- **Not yet:** damage, burning grass, shards that stay on the ground, the motes reacting to the hero.

### Revision after Codex review, as built (2026-11-13)

- **Drawn at all:** the precipitation pass maps every kind explicitly (fire 7k, crystal 18k, motes 2.5k particles at
  full strength); `falling()` covers the magic kinds (motes need no clouds, a fire rain brings a broken sky of 0.55–0.75
  so its meteors show), `isRaining()` and wet ground stay rain's alone, and summer is silent under any of them.
- **Blending:** one pipeline: what glows is written premultiplied with alpha 0, which adds it; it is dimmed by the
  fog's transmittance at its depth and not given the fog's light again. Not yet: motes dimmed by the ground fog they
  hang in.
- **Meteors:** a second draw of six instances in the same shaders with their own path (800 m out, inside the
  camera's 1 km), no box, no wrap, no roof test. **Motes:** a 9 m layer from the fog's base (or under the camera
  without fog), no roof test: they are in the air, indoors too.
- **Frost:** one cover value; a crystal storm makes it grow like snow (the climate's automatic cover covers crystal),
  and `frost` (0..1) follows what settles, as fast as it settles, so old snow is not recoloured at once.
- **Tints:** only the fog's tint is stored (`fog_tint` in the op, validated as three numbers 0..1, kept with the fog
  like its height, cleared to grey when new fog comes without one, replayed after a load); the sky's colour and the
  flash's come from the kind. Fading fog out keeps its colour.
- **Owners:** a story's op is the way to set magical weather; the climate never picks it and leaves story weather
  alone. A bare `weather.set` (the console, a demo) is overwritten by the next front change, as for rain.
- **Talk:** magic categories come first (fire, crystal, magic for motes or a coloured fog), before thunder, rain and
  the relief after it. A fire rain's strikes come from the same ticker as lightning; the engine gives them an orange
  flash and the game's fire-storm blast instead of thunder.
- **Sounds:** the game's own `MFX_FIRERAIN_RAIN`, `MFX_THUNDERSTORM_ICERAIN` and (faint) `MFX_TRANSFORM_INVEST`,
  restarted when they end.

### Fire rain, round 2 (plan, 2026-11-13)

After the first look in game: the night sky was grey-white, the game's fire-rain sound repeats audibly (it is short and
restarted), and nothing happens where the fire comes down.

- **Sky:** the bellies' glow is added in the cloud pass in sky radiance, which the night's high exposure blows out to
  white. Scale it by `1/exposure`, so it is a dull red ember-light by night as by day.
- **Sound:** a long CC0 recording of a big fire (Freesound, like the cicadas), cut to a seamless loop and played as a
  named loop from Python while the fire rain falls; the game's short spell sound is no longer looped. The impacts keep
  the game's own sounds, now where they land (the spell effect carries its sound).
- **Impacts in the world:** Python picks a point now and then (a strike about every 10–20 s at full strength): 8–45 m
  from the hero in a random direction, rarely nearer, never right on him; its height from the roof map (the highest
  static surface there: ground, a roof or a tree's crown, so trees and roofs are hit too). There the game's own spell
  effect plays (`SPELLFX_FIRESTORM_COLLIDE`: explosion, light, sound) through a new `gothic.world.play_effect(name,
  x, y, z)` (as `Wld_PlayEffect` at a point), followed by a lingering fire there for half a minute (the firestorm's
  spread effect, or whichever of the game's burning effects looks right), with an orange flash
  (`weather.flash(level)`, a flash without thunder).
- **Creatures:** anyone within 4 m of a strike, hero, people and animals, takes fire damage that falls off with
  distance (up to about 40), never below 1 hp: the fire rain wounds, it does not kill or break a story. No perception
  is sent (it would blame the hero for the strike and set people on him).
- **Not yet:** scorched ground that stays, grass catching fire, animals fleeing (no AI hook for that without blaming
  someone), burning NPC animations.

### Fire rain round 2 and after, as built (2026-11-13)

- **Sky:** the clouds' ember glow is a few times the sky's own light on them (not `1/exposure`: the exposure is 1, the
  night's darkness is in the sky LUT), deep red in the bellies, yellow where they thin. Seen in game by night and day.
- **Sound:** `feuer.wav`, a CC0 recording of a large fire (craigsmith, Freesound 483318), looped by
  `python/dm/magic_weather.py`.
- **Strikes:** `magic_weather.py`: the firestorm's blast and spread effects with physics off down the chain,
  `play_effect(..., seconds)` bounding the fire's life (not saved), an orange `weather.flash`, wounds (never fatal,
  `hurt`) for the hero and animals within 4 m, not under a roof, nobody in a dialogue, people never.
- **Ash:** the cover's third colour: a fire rain lays grey soot with charred patches (60 % at full strength), a crystal
  storm thin frost (35 %), snow 80 %; what lies takes the colour of what falls on it while it falls. Seen in game.
- **Shooting stars:** on summer's warm clear nights, white-blue, quick and rare (`weather.shooting_stars(rate)`, the
  meteors' path as kind 7, none under clouds). Not yet seen in game.
- **Arcane mist:** seen in game by day (violet fog, motes): fine as it is.

## Characters: wet clothes and a dusting of snow (2026-11-13)

- **What drives it:** four values of their own in `GlobalEffects::Weather`, eased in `tickWeather` and passed to the
  shaders beside the ground's (`weatherSoak`, `weatherDust`, `weatherDustFrost`, `weatherSoot` in `SceneDesc`).
  `soak` follows the rain that falls: soaked within half a minute, dry in about four minutes (faster in heat). `dust`
  follows snow or a crystal storm: within a minute, melting in three (half a minute once it rains). `dustFrost` is how
  much of the dusting is frost; it turns towards what falls within 20 s. `soot` follows a fire rain: a minute to
  settle, five to fade (one in rain). They do not wait for the ground: a man is wet before the road is.
- **Shading:** `weatherOnCharacter` in `main.frag`, for buckets with `BK_SKIN` or `BK_MORPH` (people, animals, heads).
  Wet is darker and deeper in colour (the ground's formula, a little gentler); faces (the morph heads) only 30 % of it.
  The dusting is snow white, or the ground's glassy blue frost under a crystal storm, on what faces up (shoulders, the
  top of the head or hat, an animal's back), patchy and at most about 40 % of it; noise on the mesh's texture
  coordinates keeps the patches on him as he moves. A face looking forward does not face up and gets none. Soot is a
  faint grey-brown darkening, most on top. Motes leave nothing.
- **Shelter:** the roof map, as for the ground, with the tolerance of a moderate slope (50 cm plus one cell), per
  fragment. There is no per-character memory: stepping under a roof dries him and clears the snow at once, and
  stepping out wets him at once to however wet the weather has made everyone in the open.
- **Not done:** no gloss or drips (the G-buffer has no channel for it); no per-character state (an NPC who has been
  indoors all along is as wet as one outside the moment he steps out); weapons and items on a character are static
  meshes and get the ground's treatment; patches can break at texture seams; a character under a tree counts as
  sheltered, as the ground does. Untested in game.
