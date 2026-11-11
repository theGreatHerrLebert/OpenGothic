// Shelved: Solaris's Roseglass as a screen overlay, not built (it is not in shader/CMakeLists.txt).
// As a flat overlay, folding a 3D world into a kaleidoscope reads as a screen effect rather than as seeing differently,
// so it was taken out of trip.frag. Kept for a version anchored in the world: stained glass on real surfaces, or the
// light that falls through it. It expects trip.frag's push constants, lum(), hash12() and sceneImage.

// --- Roseglass, after Solaris (render_trip_roseglass) ---------------------------------------------------------------
// A stained-glass kaleidoscope: the world folds into six mirrored wedges round the middle, its colours become flat,
// saturated glass panels lit from behind, strong edges turn into lead, and coloured shards drift slowly outward.
// Solaris tumbles real crystals with physics; here the shards are procedural.

vec3 glassColor(float h) {
  // Jewel glass: ruby, amber, gold, emerald, cobalt, violet.
  h = fract(h)*6.0;
  if(h<1.0) return vec3(0.90, 0.10, 0.20);
  if(h<2.0) return vec3(1.00, 0.58, 0.10);
  if(h<3.0) return vec3(1.00, 0.85, 0.25);
  if(h<4.0) return vec3(0.10, 0.75, 0.38);
  if(h<5.0) return vec3(0.15, 0.32, 0.95);
  return vec3(0.58, 0.20, 0.88);
  }

vec3 roseglass(vec3 c, vec2 uv, float G, float t) {
  if(G<=0.001)
    return c;
  vec2  size  = vec2(textureSize(sceneImage, 0));
  vec2  ctr   = vec2(0.5, 0.5);
  vec2  d     = (uv - ctr)*vec2(push.aspect, 1.0);
  float r     = length(d);
  float wedge = 6.2832/6.0;
  // The bounce: on every beat (push.pulse, the trip's contraction with its damped rebound) the kaleidoscope pulls in
  // towards the middle and kicks round a little, then springs back.
  float beat  = push.pulse/0.04;                                 // 0..about 1 at the peak's strongest beat
  float rot   = t*0.18 + min(push.bass, 1.0)*0.15 + beat*0.25;
  float a     = atan(d.y, d.x) + rot;
  float fold  = abs(mod(a, wedge) - wedge*0.5);                 // six mirrored wedges
  float kr    = r*(1.0 - beat*0.2);
  vec2  kd    = vec2(cos(fold), sin(fold))*kr;
  vec2  kuv   = clamp(ctr + kd/vec2(push.aspect, 1.0), vec2(0.0), vec2(1.0));
  vec3  s     = texture(sceneImage, kuv).rgb;

  // The mosaic: rings drifting outward, three tiles across each half wedge, each tile its own jewel colour. The
  // world is the light falling through it: bright places glow, dark ones stay deep, and its shapes stay readable.
  vec2  tp    = vec2(kr*7.0 - t*0.2, fold/(wedge*0.5)*3.0);
  vec2  tile  = floor(tp);
  vec2  inner = fract(tp);
  vec3  jewel = glassColor(hash12(tile + 11.7));
  float light = 0.45 + lum(s)*1.1;
  vec3  pane  = jewel*light;
  pane = mix(pane, clamp(vec3(lum(s)) + (s - vec3(lum(s)))*2.2, 0.0, 1.0), 0.25);

  // Shards: a few tiles hold a second, brighter piece of glass.
  float shard = step(0.65, hash12(tile + 3.3))*smoothstep(0.15, 0.3, min(min(inner.x, 1.0 - inner.x), min(inner.y, 1.0 - inner.y)));
  pane = mix(pane, glassColor(hash12(tile))*1.25, shard*0.6);
  pane *= 1.1 + beat*0.16;   // light pulses through the glass on the beat (rate capped with the pulse)

  // Lead: round every tile, and thick along the world's own strong edges.
  float border = 1.0 - smoothstep(0.0, 0.07, min(min(inner.x, 1.0 - inner.x), min(inner.y, 1.0 - inner.y)));
  vec2  e  = 2.5/size;
  float ex = lum(texture(sceneImage, clamp(kuv + vec2(e.x, 0.0), vec2(0.0), vec2(1.0))).rgb)
           - lum(texture(sceneImage, clamp(kuv - vec2(e.x, 0.0), vec2(0.0), vec2(1.0))).rgb);
  float ey = lum(texture(sceneImage, clamp(kuv + vec2(0.0, e.y), vec2(0.0), vec2(1.0))).rgb)
           - lum(texture(sceneImage, clamp(kuv - vec2(0.0, e.y), vec2(0.0), vec2(1.0))).rgb);
  float lead = max(border, smoothstep(0.08, 0.16, length(vec2(ex, ey))));
  pane = mix(pane, vec3(0.05, 0.04, 0.03), lead*0.9);

  return mix(c, pane, G);
  }

