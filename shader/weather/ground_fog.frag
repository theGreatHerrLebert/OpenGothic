#version 450
#extension GL_ARB_separate_shader_objects : enable
#extension GL_GOOGLE_include_directive    : enable
#extension GL_EXT_control_flow_attributes : enable

#include "sky/sky_common.glsl"
#include "scene.glsl"
#include "common.glsl"

// Ground fog (docs/plan-weather.md): fog that lies on the ground and thins upwards, broken into banks by
// world-anchored noise that drifts with the wind. Marched from the camera to the surface (or 600 m), lit by the sky's
// ambient and the sun with forward scattering, and blended as scene*T + light (the fog pass's blend state).

layout(binding = 0, std140) uniform UboScene {
  SceneDesc scene;
  };
layout(binding = 1) uniform sampler2D depth;

layout(push_constant, std430) uniform Push {
  vec4 fog;    // density 0..1, height in m, base in world cm, time in s
  vec4 drift;  // wind displacement x, z in m; snowy; unused
  vec4 tint;   // its colour (white: ordinary fog); a coloured fog glows a little of itself, by night too
  } push;

layout(location = 0) out vec4 outColor;

float hash3(vec3 p) {
  p  = fract(p*0.3183099 + vec3(0.1, 0.2, 0.3));
  p *= 17.0;
  return fract(p.x*p.y*p.z*(p.x+p.y+p.z));
  }

float noise3(vec3 x) {
  vec3 i = floor(x);
  vec3 f = fract(x);
  f = f*f*(3.0-2.0*f);
  return mix(mix(mix(hash3(i+vec3(0,0,0)), hash3(i+vec3(1,0,0)), f.x),
                 mix(hash3(i+vec3(0,1,0)), hash3(i+vec3(1,1,0)), f.x), f.y),
             mix(mix(hash3(i+vec3(0,0,1)), hash3(i+vec3(1,0,1)), f.x),
                 mix(hash3(i+vec3(0,1,1)), hash3(i+vec3(1,1,1)), f.x), f.y), f.z);
  }

// metres; banks some 40 m across, flatter than wide, with finer wisps over them
float banks(vec3 p) {
  vec3 q = vec3(p.x - push.drift.x, p.y*2.5, p.z - push.drift.y) / 40.0;
  float n = noise3(q)*0.65 + noise3(q*2.7 + vec3(5.2, 1.3, 7.1))*0.35;
  return smoothstep(0.25, 0.75, n);
  }

void main() {
  const float density = push.fog.x;
  if(density<=0.001) {
    outColor = vec4(0, 0, 0, 0);
    return;
    }
  const float heightM = max(push.fog.y, 1.0);
  const float baseM   = push.fog.z*0.01;

  const vec2  uv   = gl_FragCoord.xy*scene.screenResInv;
  const vec2  ndc  = uv*2.0 - vec2(1.0);
  const float z    = texelFetch(depth, ivec2(gl_FragCoord.xy), 0).r;
  const vec4  wp4  = scene.viewProjectInv*vec4(ndc, z, 1.0);
  const vec3  cam  = scene.camPos*0.01;
  const vec3  surf = (wp4.xyz/wp4.w)*0.01;

  vec3        ray  = surf - cam;
  float       dist = length(ray);
  const vec3  dir  = ray/max(dist, 1e-4);
  if(z>=1.0 || dist>600.0)
    dist = 600.0;

  // Extinction in 1/m: at full density, at the base, about 50 m of visibility.
  const float sigma0 = 0.06*density;

  // Skip a ray that stays far above the fog: the profile at 6 heights is under 0.3 %.
  const float top  = baseM + heightM*6.0;
  const float yEnd = cam.y + dir.y*dist;
  if(cam.y>top && yEnd>top) {
    outColor = vec4(0, 0, 0, 0);
    return;
    }

  // Light: the sky's ambient and the sun (dimmed by the weather's clouds already), forward-scattered, as the
  // precipitation is lit; grey-blue at night from the moon's ambient.
  const float cosT   = dot(dir, scene.sunDir);
  const float g      = 0.55;
  const float hg     = (1.0-g*g)/(4.0*M_PI*pow(max(1.0 + g*g - 2.0*g*cosT, 1e-4), 1.5));
  const vec3  sunL   = scene.sunColor*max(scene.sunDir.y, 0.0)*(0.25 + hg*2.2);
  const vec3  tint   = push.tint.rgb;
  const float glow   = max(tint.r, max(tint.g, tint.b)) - min(tint.r, min(tint.g, tint.b));   // 0 for grey fog
  const vec3  light  = (sunL + scene.ambient*2.0 + NightAmbient*Fd_Lambert)*0.85*tint;

  const int   steps = 12;
  const float ds    = dist/float(steps);
  const float jit   = interleavedGradientNoise(gl_FragCoord.xy);
  float T = 1.0;
  vec3  L = vec3(0);
  [[dont_unroll]]
  for(int i=0; i<steps; ++i) {
    const vec3  p   = cam + dir*(ds*(float(i)+jit));
    const float h   = max(p.y - baseM, 0.0);
    const float prf = exp(-h/heightM);
    if(prf<0.003)
      continue;
    const float s   = sigma0*prf*(0.15 + 1.35*banks(p));
    const float a   = 1.0 - exp(-s*ds);
    L += T*a*(light*scene.exposure + tint*glow*0.35*(0.6 + 0.4*banks(p*1.7 + vec3(0.0, push.fog.w*0.05, 0.0))));
    T *= 1.0 - a;
    if(T<0.01)
      break;
    }

  outColor = vec4(L, 1.0 - T);   // the light is exposed in the loop; the glow is our own, as the motes
  }
