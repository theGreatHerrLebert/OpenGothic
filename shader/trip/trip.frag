#version 450

// A trip over the finished frame, ported from Solaris's Mindcap (render_trip_mindcap): a breathing warp, a chromatic
// split, glowing edges, saturation with a turning hue, and tracers from the previous trip frame. Solaris counts in
// frames at 60 fps on a small framebuffer; here time is in seconds and offsets are fractions of the screen.

#extension GL_ARB_separate_shader_objects : enable

layout(push_constant, std140) uniform PushConstant {
  float intensity;  // 0 sober .. 1 peak
  float time;       // seconds since the trip began
  float bass;       // music bands, smoothed, about 0..1
  float mid;
  float treble;
  float edges;      // how strongly edges glow, 0..1 (scaled by intensity)
  float tracers;    // how strongly the previous frame persists, 0..1 (scaled by intensity)
  float snow;       // falling snow, 0 none .. 1 a blizzard; independent of the trip
  float yaw;        // the camera, in radians: snow shifts as the view turns
  float pitch;
  float clock;      // seconds, for the snow, which also falls without a trip
  float pulse;      // the beat's contraction now, 0..about 0.05: flakes swell with it
  float look;       // 0 Mindcap, 1 Emberheart
  float aspect;     // screen width over height
  float eye;        // DragonflyEye over the trip, 0..1
  float afterglow;  // Afterglow over the trip, 0..1: bright things burn in and smear (history holds the glow)
  } push;

layout(binding = 0) uniform sampler2D sceneImage;
layout(binding = 1) uniform sampler2D historyImage;

layout(location = 0) in  vec2 uv;
layout(location = 0) out vec4 outColor;
layout(location = 1) out vec4 outHistory;

float lum(vec3 c) {
  return dot(c, vec3(0.299, 0.587, 0.114));
  }

// Mindcap's palette instead of the whole rainbow: hot pink (Solaris's 0xff44ff), violet and a bright green, visited
// pink, violet, green, violet, pink. Blends keep their colourfulness, so a midpoint never turns grey.
vec3 vividMix(vec3 a, vec3 b, float f) {
  vec3  c    = mix(a, b, f);
  float l    = lum(c);
  float want = mix(max(a.r, max(a.g, a.b)) - min(a.r, min(a.g, a.b)), max(b.r, max(b.g, b.b)) - min(b.r, min(b.g, b.b)), f);
  float have = max(c.r, max(c.g, c.b)) - min(c.r, min(c.g, c.b));
  if(have>1e-6)
    c = vec3(l) + (c - vec3(l))*(want/have);
  return clamp(c, 0.0, 1.0);
  }

vec3 desertColor(float h) {
  // Emberheart's desert, from Solaris: pale sand, gold, deep ochre, amber.
  const vec3 sand  = vec3(1.00, 0.91, 0.63);
  const vec3 gold  = vec3(1.00, 0.80, 0.33);
  const vec3 ochre = vec3(0.87, 0.60, 0.20);
  const vec3 amber = vec3(1.00, 0.67, 0.27);
  h = fract(h)*4.0;
  float f = smoothstep(0.0, 1.0, fract(h));
  if(h<1.0)
    return mix(sand, gold, f);
  if(h<2.0)
    return mix(gold, ochre, f);
  if(h<3.0)
    return mix(ochre, amber, f);
  return mix(amber, sand, f);
  }

vec3 mindcapColor(float h);

vec3 hueColor(float h) {
  return push.look>0.5 ? desertColor(h) : mindcapColor(h);
  }

vec3 mindcapColor(float h) {
  const vec3 pink   = vec3(1.00, 0.27, 1.00);
  const vec3 violet = vec3(0.55, 0.25, 1.00);
  const vec3 green  = vec3(0.30, 1.00, 0.45);
  h = fract(h)*4.0;
  float f = smoothstep(0.0, 1.0, fract(h));
  if(h<1.0)
    return vividMix(pink, violet, f);
  if(h<2.0)
    return vividMix(violet, green, f);
  if(h<3.0)
    return vividMix(green, violet, f);
  return vividMix(violet, pink, f);
  }

float hash12(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx)*0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y)*p3.z);
  }

// One layer of flakes. The screen is a grid of cells, some holding a flake; each column of cells falls at its own pace
// with a slant in the wind, and each flake flutters sideways at its own rate, so the snow never slides down as one
// pattern. A pixel looks at its own column and both neighbours, and at the cells above and below, so a flake that
// sways or glows past its cell is still drawn whole instead of being cut off at the cell's edge. Near layers have
// fewer, bigger, faster flakes and shift more as the camera turns. Returns the flake (x) and a halo (y), which only a
// trip lights up.
vec2 snowLayer(vec2 uv, float aspect, float t, float scale, float speed, float size, float amount, float parallax) {
  vec2 p = vec2(uv.x*aspect, uv.y)*scale;
  // A full turn shifts by a whole number of cells, so 360 degrees and 0 show the same snow and nothing pops.
  float turn = round(6.2832*scale*parallax);
  p += vec2(push.yaw/6.2832*turn, -push.pitch*scale*parallax);
  p.x += t*speed*0.15 + sin(t*0.27 + scale)*0.6;   // the wind's slant and a slow gust

  vec2  best = vec2(0.0);
  float home = floor(p.x);
  for(int dx=-1; dx<=1; ++dx) {
    float column = home + float(dx);
    float py     = p.y - t*speed*(0.7 + 0.6*hash12(vec2(column, scale)));   // each column falls at its own pace
    float row    = floor(py);
    for(int dy=-1; dy<=1; ++dy) {
      vec2  cell = vec2(column, row + float(dy));
      float h    = hash12(cell);
      if(h>amount)
        continue;
      vec2 pos = vec2(0.25 + 0.5*hash12(cell + 7.13), 0.2 + 0.6*hash12(cell + 3.71));
      pos.x += sin(t*(1.6 + h*1.4) + h*6.283)*0.2;   // the flutter: each flake wobbles at its own rate
      float d = length(vec2(p.x, py) - (cell + pos));
      best = max(best, vec2(smoothstep(size, size*0.25, d), smoothstep(size*3.0, size*0.5, d)));
      }
    }
  return best;
  }

// A few ice crystals among the flakes: sparse six-pointed stars, larger, slowly turning as they fall, each glinting now
// and then. Returns their brightness.
float crystalLayer(vec2 uv, float aspect, float t, float density) {
  const float scale = 3.5;
  vec2 p = vec2(uv.x*aspect, uv.y)*scale;
  float turn = round(6.2832*scale*0.7);
  p += vec2(push.yaw/6.2832*turn, -push.pitch*scale*0.7);
  p += vec2(t*0.08 + sin(t*0.21)*0.4, -t*0.9);
  vec2  cell = floor(p);
  float h    = hash12(cell + 19.3);
  if(h>density*0.12)
    return 0.0;
  vec2  pos   = vec2(0.25 + 0.5*hash12(cell + 2.9), 0.25 + 0.5*hash12(cell + 5.3));
  vec2  d     = fract(p) - pos;
  float r     = length(d);
  float ang   = atan(d.y, d.x) + t*(0.3 + h*0.8);
  float arms  = pow(abs(cos(3.0*ang)), 12.0);                      // six thin arms
  float star  = smoothstep(0.11, 0.0, r)*(0.35 + 0.65*arms) + smoothstep(0.025, 0.0, r);
  float glint = 0.55 + 0.45*pow(max(0.0, sin(t*(1.5 + h*2.0) + h*40.0)), 8.0)*2.0;
  return clamp(star*glint, 0.0, 1.0);
  }

// On a trip the snow joins in: it spirals round the middle of the screen, rides the warp, swells on the beat, and its
// flakes glow in the trip's colours. Sober (I = 0) it is plain white snow, falling straight.
vec3 snowfall(vec3 c, vec2 uv, vec2 warp, float density, float t, float I) {
  if(density<=0.001)
    return c;
  vec2  size   = vec2(textureSize(sceneImage, 0));
  float aspect = size.x/size.y;

  vec2  d   = uv - vec2(0.5);
  float a   = I*0.7*sin(t*0.35)*(1.0 - smoothstep(0.0, 0.75, length(d)));
  vec2  suv = vec2(0.5) + mat2(cos(a), -sin(a), sin(a), cos(a))*d + warp*2.0;
  float swell = 1.0 + push.pulse*12.0;

  vec2 l0 = snowLayer(suv, aspect, t,  5.0, 2.6, 0.13*swell, density*0.30, 0.55)*0.95;
  vec2 l1 = snowLayer(suv, aspect, t,  9.0, 3.4, 0.10*swell, density*0.45, 0.35)*0.80;
  vec2 l2 = snowLayer(suv, aspect, t, 15.0, 4.2, 0.08*swell, density*0.60, 0.22)*0.65;
  vec2 l3 = snowLayer(suv, aspect, t, 26.0, 5.6, 0.06*swell, density*0.75, 0.12)*0.50;
  float crystals = crystalLayer(suv, aspect, t, density);
  float flakes = max(max(max(l0.x, l1.x), max(l2.x, l3.x)), crystals);
  float halo   = max(max(l0.y, l1.y), max(l2.y, l3.y));

  vec3 tone = mix(vec3(0.93, 0.95, 1.00), hueColor(t*0.36 + uv.y*0.5), I*0.75);
  c = mix(c, vec3(0.80, 0.84, 0.90), density*0.22*(1.0 - I*0.6));   // heavy snow swallows the distance
  c += hueColor(t*0.36 + 0.33 + uv.x*0.5)*halo*I*0.45;                // the glow, only on a trip
  return mix(c, tone, flakes);
  }

// --- DragonflyEye, after Solaris (render_trip_dragonfly_eye) ----------------------------------------------------
// A compound eye under a rose window: the picture breaks into hexagonal facets, each showing its own slightly magnified
// piece of the world, while rings and turning petals pull it outward and around, with lead seams between them.

float eyeRing(float r, float centre, float width) {
  return clamp(1.0 - abs(r - centre)/width, 0.0, 1.0);
  }

float eyeSeam(float ang, float n, float spin) {
  float s = fract((ang*n + spin)/6.2832);
  return 1.0 - abs(s - 0.5)*2.0;
  }

// Iridescence in the scorpion's colours: gold, amber, a metallic silver and pale gold.
vec3 eyeColor(float h) {
  const vec3 gold   = vec3(1.00, 0.82, 0.45);
  const vec3 amber  = vec3(1.00, 0.60, 0.22);
  const vec3 silver = vec3(0.84, 0.87, 0.90);
  const vec3 pale   = vec3(0.95, 0.88, 0.62);
  h = fract(h)*4.0;
  float f = smoothstep(0.0, 1.0, fract(h));
  if(h<1.0)
    return mix(gold, amber, f);
  if(h<2.0)
    return mix(amber, silver, f);
  if(h<3.0)
    return mix(silver, pale, f);
  return mix(pale, gold, f);
  }

vec3 dragonflyEye(vec3 c, vec2 uv, float E, float t) {
  if(E<=0.001)
    return c;
  vec2  size  = vec2(textureSize(sceneImage, 0));
  vec2  d     = uv - vec2(0.5, 0.46);
  vec2  dn    = d*vec2(push.aspect, 1.0);
  float r     = length(d);
  float ang   = atan(dn.y, dn.x);
  float peak  = smoothstep(0.78, 1.0, push.intensity);
  float bass  = min(push.bass, 1.0);
  float outer = t*(0.09 + bass*0.07 + peak*0.066);
  float inner = -t*(0.066 + peak*0.036);

  float oculus = eyeRing(r, 0.00, 0.22);
  float nave   = eyeRing(r, 0.27, 0.12);
  float choir  = eyeRing(r, 0.49, 0.15);
  float crown  = eyeRing(r, 0.74, 0.18);
  float petal6  = pow(cos(ang*6.0 + inner)*0.5 + 0.5, 2.4);
  float petal8  = pow(cos(ang*8.0 - outer)*0.5 + 0.5, 2.0);
  float petal12 = pow(cos(ang*12.0 + outer*1.7)*0.5 + 0.5, 1.7);
  float lens    = clamp(oculus*0.95 + nave*petal6 + choir*petal8 + crown*petal12*(0.78 + 0.22*sin(t*0.6)), 0.0, 1.4);

  // The facets: the nearest centre of a hexagonal grid, in pixels.
  vec2  px   = uv*size;
  float hs   = size.y/30.0;
  float rowH = hs*0.8660254;
  float row0 = floor(px.y/rowH);
  vec2  best = px;
  float bestD2 = 1e20;
  for(int dy=-1; dy<=1; ++dy) {
    float row = row0 + float(dy);
    float off = mod(row, 2.0)<0.5 ? 0.0 : hs*0.5;
    float col0 = floor((px.x - off)/hs);
    for(int dx=-1; dx<=1; ++dx) {
      vec2  cc = vec2((col0 + float(dx))*hs + off, row*rowH);
      vec2  dd = px - cc;
      float d2 = dot(dd, dd);
      if(d2<bestD2) {
        bestD2 = d2;
        best   = cc;
        }
      }
    }
  vec2  cellD = px - best;
  float cellN = clamp(sqrt(bestD2)/(hs*0.72), 0.0, 1.5);
  float core  = clamp(1.0 - cellN, 0.0, 1.0);
  float cellPhase = (sin(best.x*0.0173 + best.y*0.0119 + t*0.11)*0.5 + 0.5)*0.7
                  + (cos(atan(cellD.y, cellD.x)*3.0 + t*0.6)*0.5 + 0.5)*0.3;

  // Each facet shows its own piece of the world, pulled outward and around by the rose window.
  vec2  dir   = dn/max(length(dn), 1e-4);
  dir        /= vec2(push.aspect, 1.0);
  vec2  tang  = vec2(-dir.y, dir.x);
  float breath = sin(t*1.08 + r*16.0)*0.5 + 0.5;
  float pull   = lens*(1.4 + breath*2.4 + peak*1.8);
  float twist  = (petal8 - 0.5)*(1.8 + peak*1.2);
  float focus  = clamp(0.82 + core*0.48 + lens*0.22 + peak*0.24, 0.65, 1.55);
  // Each facet shows a large, near-true piece of the world, so the game stays readable through the eye.
  vec2  src    = (best + cellD*0.6*focus)/size + dir*pull*E*0.006 + tang*twist*E*0.004;
  src = clamp(src, vec2(0.0), vec2(1.0));

  vec3 sampled = texture(sceneImage, src).rgb;
  if(peak>0.01) {
    // At the peak the world refracts along the rings.
    float split = (1.0 + peak*3.0)*(0.45 + lens*0.55 + core*0.25)/size.y;
    sampled.r = texture(sceneImage, clamp(src + tang*split, vec2(0.0), vec2(1.0))).r;
    sampled.b = texture(sceneImage, clamp(src - tang*split, vec2(0.0), vec2(1.0))).b;
    }
  vec3 hive = texture(sceneImage, clamp(best/size, vec2(0.0), vec2(1.0))).rgb;

  // The world keeps its own colours: only a light pull towards the facet's centre colour.
  vec3 o = mix(sampled, hive, E*(0.08 + core*0.12));

  // The colour lives in the structure: facet rims and the rose window's seams glow in gold, amber and silver,
  // framing the world instead of tinting it over.
  float rim     = smoothstep(0.80, 1.0, cellN);
  float rings   = eyeRing(r, 0.22, 0.02) + eyeRing(r, 0.38, 0.024) + eyeRing(r, 0.62, 0.028);
  float tracery = clamp(nave*pow(eyeSeam(ang, 6.0, inner), 18.0) + choir*pow(eyeSeam(ang, 8.0, -outer), 18.0)
                        + crown*pow(eyeSeam(ang, 12.0, outer*1.7), 16.0) + rings*0.85, 0.0, 1.0);
  vec3 frame = eyeColor(t*0.054 + 1.5 + cellPhase*0.75);
  o = mix(o, frame, rim*E*0.45);
  o = mix(o, eyeColor(t*0.054 + r*0.55 + ang/6.2832)*1.1, tracery*E*0.6);
  return mix(c, o, E*0.7);   // never all of it: the eye lies over the game, it does not replace it
  }

void main() {
  const float I  = push.intensity;
  const float t  = push.time;
  const vec2  px = 1.0/vec2(textureSize(sceneImage, 0));

  // A slow, gentle warp: long waves that drift rather than flutter. The beat's pulse is a zoom, set from Python.
  const float amp1 = 0.0035*I*(1.0 + push.bass*0.3);
  const float amp2 = 0.0012*I*(1.0 + push.mid *0.3);
  vec2 warp = vec2(cos(uv.y*9.0 + t*0.5)*amp1 + sin(uv.x*7.0 + uv.y*5.0 + t*0.9)*amp2,
                   sin(uv.x*8.0 + t*0.4)*amp1 + cos(uv.y*6.0 - uv.x*4.0 + t*0.7)*amp2);
  if(push.look>0.5) {
    // Emberheart: heat shimmer in rings from the middle, strongest towards the edges of vision; the bass drives it.
    vec2  d     = (uv - vec2(0.5))*vec2(push.aspect, 1.0);
    float dist  = max(length(d), 1e-4);
    vec2  dir   = d/dist;
    vec2  side  = vec2(-dir.y, dir.x);
    float edge  = smoothstep(0.05, 0.45, dist);
    float boost = 1.0 + min(push.bass, 1.0)*0.8;
    float wave  = sin(dist*30.0 + t*4.8)*I*edge*0.007*boost;
    float wave2 = sin(dist*44.0 - t*3.0)*I*edge*0.0045*boost;
    warp = (dir*wave + side*wave2)/vec2(push.aspect, 1.0);
    }
  vec2 suv = clamp(uv + warp, vec2(0.0), vec2(1.0));

  // Chromatic split: red and blue drift apart, wider with the treble.
  float split = 0.0017*I*(1.0 + push.treble*0.8);
  vec3  c = vec3(texture(sceneImage, suv + vec2(split, 0.0)).r,
                 texture(sceneImage, suv).g,
                 texture(sceneImage, suv - vec2(split, 0.0)).b);

  c = dragonflyEye(c, suv, push.eye, t);

  // Glowing edges: a light Sobel on luminance, sampled a little wide at high resolution so the glow has body.
  vec2  e  = px*max(1.0, 1.0/(px.y*540.0));
  float ll = lum(texture(sceneImage, suv - vec2(e.x, 0.0)).rgb);
  float lr = lum(texture(sceneImage, suv + vec2(e.x, 0.0)).rgb);
  float lu = lum(texture(sceneImage, suv - vec2(0.0, e.y)).rgb);
  float ld = lum(texture(sceneImage, suv + vec2(0.0, e.y)).rgb);
  float edge      = length(vec2(lr - ll, ld - lu));
  float threshold = max(0.06 - push.treble*0.03, 0.02);
  float glow      = smoothstep(threshold, threshold*2.0, edge)*min(edge*4.0, 1.0)*(0.4 + push.mid*0.35)*I*push.edges;
  c = mix(c, hueColor(t*0.36 + push.mid*0.5 + lum(c)*3.0), clamp(glow, 0.0, 1.0));

  if(push.look>0.5) {
    // The ember: a warm wash, stronger with the mids, and no turning hue: heat, not neon.
    c = mix(c, vec3(1.00, 0.53, 0.20), I*0.12*(1.0 + min(push.mid, 1.0)*0.5));
    }

  // Saturation and a slowly turning hue: the bass pushes the saturation.
  float a  = push.look>0.5 ? 0.0 : t*0.24*I + push.mid*0.15;
  float ca = cos(a), sa = sin(a);
  vec3  n  = vec3(c.r*(0.667 + ca*0.333) + c.g*(0.333 - ca*0.333 + sa*0.577) + c.b*(0.333 - ca*0.333 - sa*0.577),
                  c.r*(0.333 - ca*0.333 - sa*0.577) + c.g*(0.667 + ca*0.333) + c.b*(0.333 - ca*0.333 + sa*0.577),
                  c.r*(0.333 - ca*0.333 + sa*0.577) + c.g*(0.333 - ca*0.333 - sa*0.577) + c.b*(0.667 + ca*0.333));
  float L   = lum(n);
  float sat = 1.0 + (0.4 + push.bass*0.2)*I;
  c = clamp(vec3(L) + (n - vec3(L))*sat, 0.0, 1.0);

  c = snowfall(c, uv, warp, push.snow, push.clock, I);

  // Afterglow, after Solaris (render_trip_afterglow): long exposure. Bright things burn into a glow that fades and
  // spreads a little every frame, so moving lights leave smeared trails; the bass lets more of the world burn in.
  // While it is on, the history images hold this glow instead of the finished frame, so tracers are off for it.
  if(push.afterglow>0.001) {
    float A    = push.afterglow;
    vec3  prev = vec3(0.0);
    vec2  o    = px*1.5;
    prev += texture(historyImage, clamp(uv, vec2(0.0), vec2(1.0))).rgb*0.4;
    prev += texture(historyImage, clamp(uv + vec2(o.x, 0.0), vec2(0.0), vec2(1.0))).rgb*0.15;
    prev += texture(historyImage, clamp(uv - vec2(o.x, 0.0), vec2(0.0), vec2(1.0))).rgb*0.15;
    prev += texture(historyImage, clamp(uv + vec2(0.0, o.y), vec2(0.0), vec2(1.0))).rgb*0.15;
    prev += texture(historyImage, clamp(uv - vec2(0.0, o.y), vec2(0.0), vec2(1.0))).rgb*0.15;
    float decay = clamp((235.0 + I*16.0 + min(push.bass, 1.0)*8.0 - min(push.treble, 1.0)*4.0)/256.0, 0.85, 0.985);
    vec3  burn  = prev*decay;
    vec3  scene = texture(sceneImage, suv).rgb;
    float threshold = clamp((180.0 - I*100.0 - min(push.bass, 1.0)*60.0)/255.0, 0.15, 0.9);
    if(lum(scene)>threshold)
      burn = max(burn, mix(scene, vec3(1.0, 0.82, 0.45)*lum(scene), 0.3));   // a touch of desert gold
    vec3 lit = vec3(1.0) - (vec3(1.0) - c)*(vec3(1.0) - burn*A*0.9);          // laid over as light
    outColor   = vec4(lit, 1.0);
    outHistory = vec4(burn, 1.0);
    return;
    }

  // Tracers: the previous finished frame, drifting slightly, bled SUBTRACTIVELY. A bright trail survives many frames,
  // the dim haze is gone in a few, so trails never build up into a white-out (see Solaris's bled_feedback).
  vec2 drift = vec2(sin(t*0.35)*1.2, cos(t*0.25)*0.8)*I*(1.0 + push.bass*0.2)*px*2.0;
  vec3 prev  = max(texture(historyImage, clamp(uv + drift, vec2(0.0), vec2(1.0))).rgb - vec3(26.0/255.0), 0.0);
  float keep = clamp((0.50 + push.bass*0.18)*I*push.tracers, 0.0, 0.85);
  c = mix(c, prev, keep);

  outColor   = vec4(c, 1.0);
  outHistory = vec4(c, 1.0);
  }
