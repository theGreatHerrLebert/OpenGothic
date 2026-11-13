#version 450
#extension GL_ARB_separate_shader_objects : enable
#extension GL_GOOGLE_include_directive    : enable

#include "sky_common.glsl"
#include "scene.glsl"
#include "common.glsl"

// Volumetric weather clouds (docs/plan-clouds.md), ray-marched into a small image: premultiplied cloud light in rgb
// and the sky's transmittance through the clouds in a, in the units of sky.frag's lum before GSunIntensity.
// The shell is 1.5–4.5 km above the atmosphere's datum, in metres like the sky; the density field is anchored in
// world metres and carried by the wind.

layout(binding = 0, std140) uniform UboScene {
  SceneDesc scene;
  };
layout(binding = 1) uniform sampler2D tLUT;
layout(binding = 2) uniform sampler2D skyLUT;

layout(push_constant, std140) uniform Push {
  vec4 target;   // xy the image's size in pixels; zw the wind's displacement in metres (x, z)
  vec4 weather;  // x coverage 0..1, y snow 0..1, z seconds, w lightning 0..1
  } push;

layout(location = 0) out vec4 outColor;

const float CloudBottom = RPlanet + 1500.0;
const float CloudTop    = RPlanet + 4500.0;
const int   Steps       = 20;
const float Sigma       = 0.0045;   // extinction per metre at full density

float hash31(vec3 p) {
  p = fract(p*0.3183099 + vec3(0.71, 0.113, 0.419));
  p *= 17.0;
  return fract(p.x*p.y*p.z*(p.x+p.y+p.z));
  }

float noise3(vec3 x) {
  vec3 i = floor(x);
  vec3 f = fract(x);
  f = f*f*(3.0-2.0*f);
  return mix(mix(mix(hash31(i+vec3(0,0,0)), hash31(i+vec3(1,0,0)), f.x),
                 mix(hash31(i+vec3(0,1,0)), hash31(i+vec3(1,1,0)), f.x), f.y),
             mix(mix(hash31(i+vec3(0,0,1)), hash31(i+vec3(1,0,1)), f.x),
                 mix(hash31(i+vec3(0,1,1)), hash31(i+vec3(1,1,1)), f.x), f.y), f.z);
  }

// Coverage over a wide area: heavier bands and lighter stretches some fifteen kilometres across.
float regional(vec2 w) {
  return noise3(vec3(w/15000.0, 0.37))*0.7 + noise3(vec3(w/6000.0, 1.91))*0.3;
  }

// x, z: world metres; y: metres above the shell's bottom.
float density(vec3 w, float h, bool coarse) {
  // rounded bellies, flatter tops; storms reach higher
  float profile = smoothstep(0.0, 0.12, h) * (1.0 - smoothstep(mix(0.55, 0.95, push.weather.x), 1.0, h));
  if(profile<=0.0)
    return 0.0;
  vec3  q    = vec3(w.x/2200.0, w.y/900.0, w.z/2200.0);
  float base = noise3(q)*0.6 + noise3(q*2.03 + vec3(3.1, 1.7, 5.3))*0.3 + noise3(q*4.1 + vec3(7.7, 2.3, 1.1))*0.1;
  float cover = clamp(mix(0.25, 0.97, push.weather.x) + (regional(w.xz) - 0.5)*0.45, 0.05, 1.0);
  float d = clamp((base - (1.0-cover))/max(cover, 0.05), 0.0, 1.0);
  if(!coarse && d>0.0) {
    // fine noise wears the edges away: frayed, cauliflower edges instead of soft blobs
    float detail = noise3(q*11.0 + vec3(push.weather.z*0.02, 0.0, 0.0))*0.6 + noise3(q*23.0)*0.4;
    d = clamp(d - (1.0-d)*detail*0.55, 0.0, 1.0);
    }
  return d * profile;
  }

float phaseHG(float c, float g) {
  float g2 = g*g;
  return (1.0-g2)/(4.0*3.14159265*pow(1.0+g2-2.0*g*c, 1.5));
  }

void main() {
  const vec2  uv     = gl_FragCoord.xy / push.target.xy;
  const vec2  inPos  = uv*2.0 - 1.0;
  vec4  far    = scene.viewProjectLwcInv*vec4(inPos, 1.0, 1.0);
  const vec3  dir    = normalize(far.xyz/far.w);
  const vec3  origin = vec3(0.0, RPlanet + scene.plPosY, 0.0);
  const vec2  camXZ  = scene.camPos.xz/100.0 + push.target.zw;

  // the shell along the ray, clipped by the planet and kept within 30 km
  float t0 = rayIntersect(origin, dir, CloudBottom);
  float t1 = rayIntersect(origin, dir, CloudTop);
  if(t0<0.0 || t1<=t0 || rayIntersect(origin, dir, RPlanet)>0.0) {
    outColor = vec4(0.0, 0.0, 0.0, 1.0);
    return;
    }
  t1 = min(t1, t0 + 30000.0);

  const vec3  sunDir   = scene.sunDir;
  const float cosTheta = dot(dir, sunDir);
  const float phase    = mix(phaseHG(cosTheta, 0.6), phaseHG(cosTheta, -0.2), 0.3);
  const vec3  ambient  = textureSkyLUT(skyLUT, origin, vec3(0.0, 1.0, 0.0), sunDir) * 1.4
                       + textureSkyLUT(skyLUT, origin, normalize(vec3(dir.x, 0.15, dir.z)), sunDir) * 0.6;
  const float albedo   = mix(0.55, 0.92, push.weather.y);   // rain clouds are darker than snow clouds

  const float stepLen  = (t1-t0)/float(Steps);
  float t = t0 + stepLen*interleavedGradientNoise(gl_FragCoord.xy);
  float T = 1.0;
  vec3  C = vec3(0.0);
  float depthSum = 0.0;
  for(int i=0; i<Steps; ++i, t+=stepLen) {
    const vec3  p = origin + dir*t;
    const float h = (length(p)-CloudBottom)/(CloudTop-CloudBottom);
    const vec3  w = vec3(camXZ.x + dir.x*t, h*(CloudTop-CloudBottom), camXZ.y + dir.z*t);
    const float d = density(w, h, false);
    if(d<=0.001)
      continue;
    // light reaching this point: two coarse steps towards the sun
    float od = 0.0;
    for(int s=1; s<=2; ++s) {
      const float ls = 220.0*float(s*s);
      const vec3  lp = p + sunDir*ls;
      const float lh = (length(lp)-CloudBottom)/(CloudTop-CloudBottom);
      od += density(vec3(w.x + sunDir.x*ls, lh*(CloudTop-CloudBottom), w.z + sunDir.z*ls), lh, true) * ls;
      }
    const vec3  sunAt   = textureLUT(tLUT, p, sunDir);
    const float shadow  = exp(-Sigma*od*0.6);
    const float powder  = 1.0 - exp(-d*Sigma*stepLen*2.0);            // thick parts darker inside
    vec3  light = sunAt*shadow*phase*12.0*mix(1.0, powder, 0.5) + ambient*(0.35 + 0.65*h);
    // colour varies between neutral grey and a cool navy: thick, low parts go dark navy, thin high ones light grey
    const float navy = clamp(d*0.8 + (1.0-h)*0.4 + (noise3(vec3(w.xz/4000.0, 2.7))-0.5)*0.8, 0.0, 1.0);
    light *= mix(vec3(1.0), vec3(0.62, 0.70, 0.92), navy*(1.0-push.weather.y*0.7));
    light += vec3(0.9, 0.92, 1.0) * push.weather.w * d * 40.0;        // lightning from inside
    const float ext = exp(-d*Sigma*stepLen);
    C += T*(1.0-ext)*light*albedo;
    depthSum += T*(1.0-ext)*t;
    T *= ext;
    if(T<0.02)
      break;
    }

  // far clouds fade into the atmosphere instead of ending in a line
  const float covered = 1.0-T;
  if(covered>0.0) {
    const float dist = depthSum/covered;
    const float haze = 1.0 - exp(-dist/45000.0);
    const vec3  sky  = textureSkyLUT(skyLUT, origin, dir, sunDir);
    C = mix(C, sky*covered, haze);
    }
  outColor = vec4(C, T);
  }
