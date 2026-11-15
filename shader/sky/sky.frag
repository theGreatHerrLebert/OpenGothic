#version 450
#extension GL_ARB_separate_shader_objects : enable
#extension GL_GOOGLE_include_directive    : enable

#include "sky_common.glsl"
#include "scene.glsl"
#include "clouds.glsl"

const uvec3 SKY_DITHER_TARGET_BITS = uvec3(11, 11, 10); // hardcoded for now -> adjust in future for HDR support or 6 bit monitors

layout(binding  = 0, std140) uniform UboScene {
  SceneDesc scene;
  };
layout(binding = 1) uniform sampler2D tLUT;
layout(binding = 2) uniform sampler2D mLUT;
layout(binding = 3) uniform sampler2D skyLUT;
layout(binding = 4) uniform sampler3D fogLut;
#if defined(SEPARABLE)
layout(binding = 5) uniform sampler3D fogLutMs;
#endif

layout(binding = 6) uniform sampler2D textureDayL0;
layout(binding = 7) uniform sampler2D textureDayL1;
layout(binding = 8) uniform sampler2D textureNightL0;
layout(binding = 9) uniform sampler2D textureNightL1;

// A galaxy in place of the sky, for trips (see common/graphics/sky/galaxy.h): a 360-degree panorama and two nebulae.
layout(binding = 10) uniform sampler2D galaxyPanorama;
layout(binding = 11) uniform sampler2D galaxyNebula0;
layout(binding = 12) uniform sampler2D galaxyNebula1;
// The weather's volumetric clouds (docs/plan-clouds.md): light in rgb, the sky's transmittance through them in a.
layout(binding = 13) uniform sampler2D weatherCloudImg;
layout(push_constant, std140) uniform PushGalaxy {
  vec4 main;   // amount (0 the game's sky .. 1 the galaxy), gain, grade, spin
  vec4 tint;   // rgb the grading colour, w a glow from the music
  vec4 neb0;   // yaw, pitch, size across (radians), strength
  vec4 neb1;
  vec4 aurora; // x strength of the northern lights, y seconds, z a blood-red moon
  } galaxy;

layout(location = 0) out vec4 outColor;

vec3 inverse(vec3 pos) {
  vec4 ret = scene.viewProjectLwcInv*vec4(pos,1.0);
  return (ret.xyz/ret.w)/100.f;
  }

vec3 viewVec() {
  const vec2 uv  = gl_FragCoord.xy*scene.screenResInv;
  const vec3 pos = vec3(uv*2.0-1.0, 1.0);
  vec4 ret = scene.viewProjectInv*vec4(pos,1.0);
  return normalize(ret.xyz/ret.w - scene.camPos); //TODO: LWC
  }

vec3 atmosphere(vec3 view, vec3 sunDir) {
  const vec3  viewPos = vec3(0.0, RPlanet + scene.plPosY, 0.0);
  return textureSkyLUT(skyLUT, viewPos, view, sunDir);
  }

// debug only
vec3 transmittance(vec3 pos0, vec3 pos1) {
  const int steps = 32;

  vec3  transmittance = vec3(1.0);
  vec3  dir  = pos1-pos0;
  float dist = length(dir);
  for(int i=1; i<=steps; ++i) {
    float t      = (float(i)/steps);
    float dt     = dist/steps;
    vec3  newPos = pos0 + t*dir + vec3(0,RPlanet,0);

    const ScatteringValues sc = scatteringValues(newPos, 0);
    transmittance *= exp(-dt*sc.extinction);
    }
  return transmittance;
  }

vec3 transmittanceAprox(in vec3 pos0, in vec3 pos1) {
  vec3 dir = pos1-pos0;

  const ScatteringValues sc0 = scatteringValues(pos0 + vec3(0,RPlanet,0), 0);
  const ScatteringValues sc1 = scatteringValues(pos1 + vec3(0,RPlanet,0), 0);

  vec3  extinction = sc1.extinction;//-extinction0;
  return exp(-length(dir)*sc0.extinction);
  }

vec3 sky(vec2 uv, vec3 sunDir) {
  const vec2 inPos  = (2.0*gl_FragCoord.xy)*scene.screenResInv - 1.0;

  vec3  pos  = vec3(0,RPlanet,0);
  vec3  pos1 = inverse(vec3(inPos,1.0));
  vec3  pos0 = inverse(vec3(inPos,0));

  vec3 view  = normalize(pos1);
  vec3 lum   = atmosphere(view, sunDir);
  return lum;
  }

vec3 applyClouds(vec3 skyColor) {
  const vec2 inPos = (2.0*gl_FragCoord.xy)*scene.screenResInv - 1.0;

  float night    = scene.isNight;
  vec3  plPos    = vec3(0, RPlanet + scene.plPosY, 0);
  vec3  pos1     = inverse(vec3(inPos,1.0));
  vec3  viewDir  = normalize(pos1);
  return applyClouds(skyColor, skyLUT, plPos, scene.sunDir, viewDir, night,
                     scene.cloudsDir.xy, scene.cloudsDir.zw,
                     textureDayL1,textureDayL0, textureNightL1,textureNightL0,
                     0.0, 0.0);   // weather clouds are volumetric here (weatherCloudImg), not the flat layer
  }

vec3 galaxyLinear(vec3 c) {
  return pow(c, vec3(2.2));
  }

// The sky's direction in the galaxy's frame: the galactic plane tilted so the Milky Way arcs up over the horizon
// instead of lying along it, then turned around the pole.
vec3 galaxyFrame(vec3 d) {
  const float tilt = 0.96;
  d = vec3(d.x, d.y*cos(tilt) - d.z*sin(tilt), d.y*sin(tilt) + d.z*cos(tilt));
  float s = galaxy.main.w;
  return vec3(d.x*cos(s) - d.z*sin(s), d.y, d.x*sin(s) + d.z*cos(s));
  }

// One nebula as a patch on the sky, seen straight on (a gnomonic projection), its edges fading out softly.
vec3 galaxyNebula(sampler2D tex, vec4 p, vec3 d) {
  if(p.w<=0.001)
    return vec3(0.0);
  vec3  c = vec3(cos(p.y)*sin(p.x), sin(p.y), -cos(p.y)*cos(p.x));
  float k = dot(d, c);
  if(k<=0.1)
    return vec3(0.0);
  vec3  right = normalize(cross(vec3(0.0, 1.0, 0.0), c) + vec3(1e-5, 0.0, 0.0));
  vec3  up    = cross(c, right);
  vec2  q     = vec2(dot(d, right), dot(d, up))/k;
  vec2  ts    = vec2(textureSize(tex, 0));
  float halfH = tan(p.z*0.5);
  vec2  uv    = vec2(q.x*ts.y/ts.x, -q.y)/halfH*0.5 + 0.5;
  vec2  e     = abs(uv - 0.5)*2.0;
  float mask  = (1.0 - smoothstep(0.7, 1.0, e.x))*(1.0 - smoothstep(0.7, 1.0, e.y));
  if(mask<=0.0)
    return vec3(0.0);
  return galaxyLinear(texture(tex, uv).rgb)*mask*p.w;
  }

// Northern lights (aurora): thin sheets of light hanging in a slab of the upper atmosphere, marched along the view
// ray. Every curtain is a folded line in the horizontal plane; sampling the same line at every height extrudes it into
// a hanging wall, so curtains get real perspective: overhead they are seen from below as thin bright bands, toward the
// horizon they fold, thin and converge. Lengths are in units of the curtains' lower edge (about 100 km).
const int   AURORA_STEPS  = 32;
const float AURORA_BASE   = 1.0;     // lower edge of the curtains
const float AURORA_TOP    = 2.6;     // where the red tail has faded
const float AURORA_TILT   = 0.22;    // curtains lean along the magnetic field, so rays converge south of the zenith
const float AURORA_WIDTH  = 0.035;   // thickness of a sheet in the plane
const float AURORA_RAYS   = 14.0;    // rays per unit along a curtain (a second octave runs 2.4 times finer)
const float AURORA_RED    = 0.10;    // how much of the high red tail shows
const float AURORA_GAIN   = 3.0;     // overall brightness (halved in game: a quieter sky)
const float AURORA_SPEED  = 2.0;     // how fast it all drifts, folds and shimmers (doubled in game)

float auroraHash(float n) {
  n = fract(n*0.1031);
  n *= n + 33.33;
  n *= n + n;
  return fract(n);
  }

float auroraNoise(float x) {
  float i = floor(x), f = fract(x);
  f = f*f*(3.0 - 2.0*f);
  return mix(auroraHash(i), auroraHash(i + 1.0), f);
  }

// The plane folded slowly by a few incommensurate waves; the curtains are level lines of its y, and x runs along them.
vec2 auroraWarp(vec2 p, float t) {
  p.y += 0.80*sin(p.x*0.43 + t*0.019) + 0.22*sin(p.x*1.17 - t*0.031 + 1.7);
  p.x += 0.45*sin(p.y*1.85 + t*0.023 + 0.4);   // shifting x by y makes a line curl back on itself: folds
  p.y += 0.10*sin(p.x*2.90 + t*0.043 + 2.3);
  return p;
  }

vec3 aurora(vec3 view, float strength, float t, float glow) {
  if(strength<=0.001)
    return vec3(0.0);
  t *= AURORA_SPEED;
  // where the view ray meets the plane at unit height, and how far that moves per pixel: rays finer than a pixel fade
  // to their mean instead of aliasing (taken before the horizon test below, so the derivative is well defined)
  vec2  dir  = view.xz/max(view.y, 0.005);
  float foot = length(fwidth(dir));
  if(view.y<=0.005)
    return vec3(0.0);
  // Seen low, the light crosses a lot of air: faint and slightly reddened near the horizon, without a hard edge.
  float horizon = smoothstep(0.005, 0.16, view.y);
  float airmass = exp(-0.06/(view.y + 0.02));

  const vec3 green  = vec3(0.10, 1.00, 0.32);   // 557.7 nm atomic oxygen: the bright lower curtain
  const vec3 red    = vec3(0.80, 0.10, 0.35);   // 630 nm oxygen high up: a diffuse tail
  const vec3 fringe = vec3(0.75, 0.15, 0.65);   // nitrogen pink at the lower edge of a strong display

  float dh     = (AURORA_TOP - AURORA_BASE + 0.12)/float(AURORA_STEPS);
  float ds     = dh/max(view.y, 0.12);          // emission integrates along the ray, the path bounded near the horizon
  float dither = fract(52.9829189*fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715))));
  float pulse  = 1.0 + 0.6*glow;

  vec3 col = vec3(0.0);
  for(int i=0; i<AURORA_STEPS; ++i) {
    float h = AURORA_BASE - 0.12 + (float(i) + dither)*dh;
    vec2  p = dir*h;
    p.y -= AURORA_TILT*(h - AURORA_BASE);
    vec2  q = auroraWarp(p, t);
    // three curtains at fixed levels: the main arc, a fainter one further north, a faint one overhead
    vec3  off = q.y - vec3(1.3, 3.1, -0.5);
    if(min(min(abs(off.x), abs(off.y)), abs(off.z))>0.9)
      continue;
    // the distance to a line is the level difference over the gradient, so folds don't smear a sheet's thickness
    const float e  = 0.02;
    float gx   = (auroraWarp(p + vec2(e, 0.0), t).y - q.y)/e;
    float gy   = (auroraWarp(p + vec2(0.0, e), t).y - q.y)/e;
    float grad = max(length(vec2(gx, gy)), 0.2);
    // how far the ray moves across the sheet per step: a sheet thinner than that is widened, keeping its light
    float rate = abs(dot(dir, vec2(gx, gy)) - AURORA_TILT*gy)/grad*dh;
    float far  = length(p);
    float w    = AURORA_WIDTH*(1.0 + 0.15*far);
    float W    = max(w, 0.7*rate);
    vec3  d    = off/grad;

    // its lower edge waves a little; above it the green falls off fast, the red takes over higher up
    float base = AURORA_BASE + 0.06*sin(q.x*0.9 + t*0.03) + 0.04*auroraNoise(q.x*3.0 + 11.0);
    float u    = (h - base)/(AURORA_TOP - AURORA_BASE);
    float edge = smoothstep(-0.02, 0.015, u);
    float gpro = edge*(0.7*exp(-max(u, 0.0)*2.6) + 0.6*exp(-max(u, 0.0)*16.0));
    float rpro = smoothstep(0.15, 0.55, u)*exp(-max(u - 0.45, 0.0)*2.5);
    float fpro = edge*(1.0 - smoothstep(0.0, 0.05, u));

    // fine rays along the sheet, drifting slowly sideways; they fade out where they would alias
    float f1   = foot*h*AURORA_RAYS;
    float r1   = mix(0.5, auroraNoise(q.x*AURORA_RAYS + t*0.12), 1.0 - smoothstep(0.3, 0.7, f1));
    float r2   = mix(0.5, auroraNoise(q.x*AURORA_RAYS*2.4 - t*0.3 + 5.0), 1.0 - smoothstep(0.3, 0.7, f1*2.4));
    float r    = 0.65*r1 + 0.35*r2;
    float rays = 0.15 + 1.7*r*r;

    // each curtain has its own length and brightness knots, so they don't repeat
    vec3 len   = vec3(1.0 - smoothstep(4.0, 9.0, abs(q.x - 0.5)),
                      1.0 - smoothstep(2.0, 6.0, abs(q.x + 2.5)),
                      1.0 - smoothstep(1.0, 3.5, abs(q.x - 1.5)));
    vec3 knots = vec3(auroraNoise(q.x*0.6 + t*0.012),
                      auroraNoise(q.x*0.6 - t*0.010 + 17.0),
                      auroraNoise(q.x*0.8 + t*0.015 + 41.0));
    vec3 amp   = len*(0.35 + 0.65*knots)*vec3(1.0, 0.55, 0.35);
    float sharp = dot(amp, exp(-d*d/(W*W)))*(w/W);
    float broad = dot(amp, exp(-d*d/(9.0*W*W)))*(w/W);

    col += (green*gpro*sharp*rays + red*rpro*broad*AURORA_RED + fringe*fpro*sharp*rays*glow*0.8)*ds;
    }
  col *= horizon*airmass*mix(vec3(1.0), vec3(1.0, 0.85, 0.8), 1.0 - airmass);
  col  = col*AURORA_GAIN*strength*pulse;
  // looking along a curtain piles up a lot of light: roll it off softly instead of blowing out
  return col/(1.0 + dot(col, vec3(0.2126, 0.7152, 0.0722))*0.6);
  }

float moonHash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7)))*43758.5453);
  }

float moonNoise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  f = f*f*(3.0 - 2.0*f);
  return mix(mix(moonHash(i), moonHash(i + vec2(1, 0)), f.x), mix(moonHash(i + vec2(0, 1)), moonHash(i + vec2(1, 1)), f.x), f.y);
  }

// A blood-red moon, large and low over the war: a disk with dark seas and craters, and a red haze around it.
vec3 bloodMoon(vec3 view, float m) {
  if(m<=0.001)
    return vec3(0.0);
  const vec3  dir    = normalize(vec3(0.62, 0.42, -0.66));
  const float radius = 0.085;   // radians: about four times the real moon
  float a = acos(clamp(dot(view, dir), -1.0, 1.0));
  vec3  right = normalize(cross(vec3(0.0, 1.0, 0.0), dir));
  vec3  up    = cross(dir, right);
  vec2  q     = vec2(dot(view, right), dot(view, up))/max(dot(view, dir), 1e-3)/tan(radius);
  float disk  = 1.0 - smoothstep(0.97, 1.0, length(q));
  float seas  = moonNoise(q*2.2 + 3.0)*0.6 + moonNoise(q*5.0)*0.3 + moonNoise(q*13.0)*0.1;
  float limb  = sqrt(max(1.0 - dot(q, q), 0.0));
  vec3  face  = mix(vec3(0.45, 0.04, 0.02), vec3(1.00, 0.25, 0.10), smoothstep(0.35, 0.75, seas))*(0.55 + 0.45*limb);
  float haze  = exp(-max(a - radius, 0.0)*18.0)*0.55 + exp(-max(a - radius, 0.0)*5.0)*0.15;
  return (face*disk*1.4 + vec3(0.8, 0.08, 0.03)*haze*(1.0 - disk))*m;
  }

vec3 galaxySky(vec3 view) {
  vec3  d = galaxyFrame(view);
  float u = atan(d.x, -d.z)/(2.0*3.14159265) + 0.5;
  float v = acos(clamp(d.y, -1.0, 1.0))/3.14159265;
  vec3  c = galaxyLinear(textureLod(galaxyPanorama, vec2(u, v), 0.0).rgb);
  vec3  n = galaxyNebula(galaxyNebula0, galaxy.neb0, view) + galaxyNebula(galaxyNebula1, galaxy.neb1, view);
  c = vec3(1.0) - (vec3(1.0) - c)*(vec3(1.0) - min(n, vec3(1.0)));   // the nebulae laid over it as light
  // Graded towards the trip's colour: dim light takes the tint, the brightest cores burn white.
  float L = dot(c, vec3(0.2126, 0.7152, 0.0722));
  vec3  graded = galaxy.tint.rgb*L*2.2 + vec3(pow(L, 2.0))*1.5;
  c = mix(c, graded, galaxy.main.z);
  c = c*galaxy.main.y*(1.0 + galaxy.tint.w*0.6);
  float m = galaxy.aurora.z;
  c = mix(c, c*vec3(1.0, 0.55, 0.5), m*0.5);   // under a blood moon the sky reddens too, but not the aurora's own light
  return c + aurora(view, galaxy.aurora.x, galaxy.aurora.y, galaxy.tint.w) + bloodMoon(view, m);
  }

void main() {
  const vec2 uv     = gl_FragCoord.xy*scene.screenResInv;
  const vec3 view   = viewVec();
  const vec3 sunDir = scene.sunDir;

  // accounted in additive fog later
  vec3  maxFog = textureLod(fogLut, vec3(uv, textureSize(fogLut,0).z-1), 0).rgb;
#if defined(SEPARABLE)
  maxFog += textureLod(fogLutMs, vec3(uv, textureSize(fogLut,0).z-1), 0).rgb;
#endif
  // Sky
  vec3  lum = sky(uv, sunDir) - maxFog;
  float tr  = 1.0;
  // Clouds
  // a hot day burns the sky clean: the game's own cloud layers thin out with the heat (plan-weather.md)
  lum = mix(applyClouds(lum), lum, 0.85*scene.weatherHeat);
  if(scene.weatherOvercast>0.01) {
    // sky behind them times their transmittance, plus their own light; the fog pass applies the same transmittance
    // a soft filter over the small image: the per-pixel jitter of the march would otherwise show as pixel noise
    const vec2 px = 1.0/vec2(textureSize(weatherCloudImg, 0));
    vec4 cl = textureLod(weatherCloudImg, uv, 0)*0.36;
    cl += textureLod(weatherCloudImg, uv + vec2( 0.9,  0.4)*px, 0)*0.16;
    cl += textureLod(weatherCloudImg, uv + vec2(-0.4,  0.9)*px, 0)*0.16;
    cl += textureLod(weatherCloudImg, uv + vec2(-0.9, -0.4)*px, 0)*0.16;
    cl += textureLod(weatherCloudImg, uv + vec2( 0.4, -0.9)*px, 0)*0.16;
    lum = lum*cl.a + cl.rgb;
    }
  lum = lum * scene.GSunIntensity;

  lum *= scene.exposure;
  if(galaxy.main.x>0.001) {
    // In place of the sky, above the horizon; the gain is relative to the scene's exposure, so day and night match.
    float above = smoothstep(-0.10, 0.06, view.y);
    lum = mix(lum, galaxySky(view)*scene.exposure*4.0, galaxy.main.x*above);
    }
  lum += dither(gl_FragCoord.xy, SKY_DITHER_TARGET_BITS);
  outColor = vec4(lum, tr);
  }
