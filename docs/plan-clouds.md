# Plan: volumetric weather clouds

Status: plan, not built. Reviewed by Codex before any code. Follows docs/plan-weather.md.

## Why

The weather's clouds today (shader/sky/clouds.glsl, `weatherClouds`) are the game's flat cloud textures pulled
into a darker, closed layer. They hide the sun well, but they have no depth: no towers, no lit tops or dark bellies,
no looking into them. The player asked for "real plastic" rain clouds.

## What exists

- `Renderer::prepareSky` renders the sky's LUTs (transmittance, multi-scattering, view LUT, clouds LUT) into their own
  targets before the frame; `Renderer::drawSky` draws `sky.frag` full screen into `sceneLinear` behind the scene,
  binding scene UBO, LUTs, fog LUTs, the game's four cloud layers and the galaxy textures (bindings 0–12).
- `sky.frag` main: `lum = sky(uv) - maxFog`, then `applyClouds`, then `* GSunIntensity * exposure`; the fog pass
  later adds the atmosphere over sky pixels (now faded by `weatherOvercast`).
- `SceneDesc` carries `weatherOvercast`, `weatherFlash`, `weatherSnowy`, the sun direction and colour, `cloudsDir`
  (cloud drift), `tickCount32`, `plPosY` (camera height in m), `isNight`.
- Pipelines are listed in `shader/CMakeLists.txt`; render targets are made in `Renderer::resetSwapchain`-style code.

## Design

### 1. A low-resolution cloud image, ray-marched

A new pass in `prepareSky` (only when `weatherOvercast > 0.01`): a fragment shader `weather_clouds.frag` draws a
full-screen triangle into `sky.weatherClouds`, an RGBA16F target at a quarter of the screen in each direction. For each
pixel it builds the view ray (as `sky.frag` does), intersects a cloud shell 1500–4500 m above the ground (spherical,
`RPlanet` as in sky_common.glsl), and marches it:

- **Density:** 3D noise — a cheap value/Worley-like FBM, 3 octaves, from hash functions (no 3D texture to start;
  a baked 3D noise texture is the optimisation if it is too slow), stretched horizontally, drifting with `cloudsDir`
  and the weather wind. Coverage: a height profile (rounded bottoms, anvil-flat tops) times a coverage value from the
  overcast: scattered cumulus near 0.3, a closed deck near 1.0; storm adds height.
- **Steps:** 32 along the view ray inside the shell (adaptive: big steps in empty space, small inside), jittered
  per pixel with interleaved gradient noise so banding becomes fine noise.
- **Light:** at each dense sample, 4 steps towards the sun for self-shadowing (Beer–Lambert), Henyey–Greenstein
  phase for the silver lining, an ambient term from the sky colour above, and "powder" darkening of thick parts.
  Lightning: `weatherFlash` adds light from inside, brightest in the densest parts.
- **Output:** premultiplied colour (rgb) and transmittance (a), in the same luminance units as `sky.frag`'s `lum`
  before `GSunIntensity`.

### 2. Composite in sky.frag

`sky.frag` samples `sky.weatherClouds` (binding 13, bilinear; nearest-depth upsampling is not needed since only sky
pixels show it) and composites: `lum = lum * transmittance + cloudColour`. The flat `weatherClouds` stays as the
fallback when the pass is off and fades out as the volumetric one fades in. Rain vs snow tint from `weatherSnowy`.

### 3. Fog and the horizon

Clouds far away must fade into the atmosphere: transmittance-weighted distance along the ray goes into a blend with
the sky colour at the horizon (aerial perspective), so the deck does not end in a hard line.

### 4. Cost control

- Pass skipped entirely when overcast is 0.
- Quarter resolution; if still too slow on Metal: eighth resolution or temporal reprojection (render a quarter of the
  pixels each frame, reproject with the previous view-projection).
- Early exit when transmittance < 0.02; empty-space skipping with a coarse coverage check.
- Measure GPU time of the pass alone at 0 / 0.5 / 1.0 overcast, looking up and at the horizon.

## Order

1. Target, pipeline, pass with a constant-density slab: verify the plumbing and the upsampled composite.
2. Noise density and height profile; coverage from overcast; drift.
3. Sun lighting (self-shadow, phase, powder), ambient, night.
4. Horizon fade into the atmosphere; snow tint; lightning from inside.
5. Measure; optimise (3D noise texture, lower resolution, temporal) as needed.

Each step its own commit, live-tested on the player's Mac; the flat clouds stay until this one looks better.

## Risks

- Performance on Metal (the player's machine) is the main risk.
- Quarter-resolution edges against the terrain silhouette: clouds only show where the depth is the far plane, so
  the upsample bleeds only into sky pixels; check mountains against a bright cloud.
- Units and exposure: getting the cloud luminance to match the sky's without a lot of tuning.
- The path-trace sky path is left out (as with the rest of the weather).

## Revision after Codex review (2026-11-13)

1. **Composite that keeps the fog cancellation.** The cloud image holds premultiplied cloud radiance C and
   transmittance T. `sky.frag` outputs `(S − F)·T + C`, and the fog pass multiplies what it adds over sky pixels by
   the same T (sampling the cloud image there too), so the final sky is `S·T + C`. Validated first with a constant slab.
2. **Sun and moon** sample T at their pixel, so a cloud in front hides the disc and a gap shows it.
3. **Coordinates:** the shell is in metres around the atmosphere's datum like the sky (`RPlanet` + `plPosY`); the density
   field is anchored in world metres (`camPos/100` for x/z) and moves with a continuous wind displacement passed in
   push constants (`cloudsDir` wraps and is not wind).
4. **Rays from the cloud target's own UV and size** (push constants) with `viewProjectLwcInv`, not `screenResInv`.
5. **Lighting contract:** output unexposed radiance in the units of `sky.frag`'s `lum` before `GSunIntensity`; sun light
   through the transmittance LUT, ambient from `viewLut`; night via `isNight` with the moon's own scale; the flash
   added once, in the cloud pass only.
6. **Out of scope for v1, known:** exposure, ambient and reflections still see the flat clouds (`viewCldLut`); the
   galaxy replaces the sky as before; path tracing.
7. **Target:** allocated in the viewport reset path from the internal resolution, `ceil(w/4) × ceil(h/4)` capped at
   480×270; cleared to C=0, T=1 when the pass is off. Pipeline registered in CMake and `Shaders`.
8. **Budget from step 1:** ≤2 ms typical, ≤3 ms worst on the player's Mac; 16–24 primary steps, at most 2 shadow
   samples on coarse density, 2–3 octaves of value noise; a baked 3D noise texture if hashing is too slow.
9. **Horizon:** shell intervals with planet clipping, a maximum ray distance (~30 km) and step length; aerial
   perspective inside the cloud pass by the transmittance LUT along the ray, not a colour mix.
10. **Upsampling:** bilinear over the whole image; stable per-pixel jitter; no temporal reprojection in v1.
