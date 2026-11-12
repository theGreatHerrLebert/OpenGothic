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
layout(push_constant, std140) uniform PushGalaxy {
  vec4 main;   // amount (0 the game's sky .. 1 the galaxy), gain, grade, spin
  vec4 tint;   // rgb the grading colour, w a glow from the music
  vec4 neb0;   // yaw, pitch, size across (radians), strength
  vec4 neb1;
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
                     textureDayL1,textureDayL0, textureNightL1,textureNightL0);
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
  return c*galaxy.main.y*(1.0 + galaxy.tint.w*0.6);
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
  lum = applyClouds(lum);
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
