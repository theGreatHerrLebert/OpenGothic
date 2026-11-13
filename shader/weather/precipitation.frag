#version 450
#extension GL_ARB_separate_shader_objects : enable
#extension GL_GOOGLE_include_directive    : enable

#include "sky/sky_common.glsl"
#include "scene.glsl"
#include "common.glsl"

// Lit by the sky like the game's own particles, fogged at the particle's own depth (it is drawn after the fog pass,
// which only knows the surface behind it), and written premultiplied into the linear scene.
// What glows (embers, motes, meteors, a shard's glint) is written with alpha 0: added to the scene, dimmed by the
// fog between it and the eye but not given the fog's light a second time.

layout(binding = 0, std140) uniform UboScene {
  SceneDesc scene;
  };
layout(binding = 1) uniform sampler3D fogLut;

layout(push_constant, std430) uniform Push {
  vec4  heightBox;  // the roof map's (min x, min z, 1/width, 1/depth) in world cm
  vec2  wind;       // cm per second along x and z
  float time;       // seconds of game time
  float intensity;  // 0..1
  uint  kind;       // 1 snow, 2 rain, 3 fire, 4 crystal, 5 motes, 6 meteors
  uint  pad0, pad1, pad2;
  vec4  tint;       // motes: their colour in rgb, the height of their layer's base in w (world cm)
  } push;

layout(location = 0) in  vec2  inUv;
layout(location = 1) in  float inAlpha;
layout(location = 2) in  vec3  inPos;
layout(location = 3) in  float inGlint;
layout(location = 0) out vec4  outColor;

const uint KSnow = 1u, KRain = 2u, KFire = 3u, KCrystal = 4u, KMotes = 5u, KMeteor = 6u;

vec4 fogAt() {
  const vec2  uv = gl_FragCoord.xy * scene.screenResInv;   // as fog.frag reads its LUT
  const float dZ = linearDepth(gl_FragCoord.z, scene.clipInfo);
  const float d0 = linearDepth(dFogMin, scene.clipInfo);
  const float d1 = linearDepth(dFogMax, scene.clipInfo);
  return textureLod(fogLut, vec3(uv, clamp((dZ-d0)/(d1-d0), 0.0, 1.0)), 0);
  }

void main() {
  const uint kind = push.kind;

  if(kind==KMeteor) {
    // a white-hot head at the leading end (uv.y 1), an orange trail burning out behind it
    const float along = inUv.y*0.5 + 0.5;            // 0 tail .. 1 head
    const float core  = 1.0 - abs(inUv.x);
    const float a     = core*core * pow(along, 2.2) * inAlpha;
    if(a<=0.002)
      discard;
    const vec3  cl    = mix(vec3(1.0, 0.35, 0.08), vec3(1.0, 0.92, 0.75), smoothstep(0.75, 1.0, along));
    outColor = vec4(cl * a * 3.0, 0.0);
    return;
    }

  if(kind==KFire || kind==KMotes) {
    float shape;
    vec3  cl;
    if(kind==KFire) {
      shape = (1.0 - abs(inUv.x)) * (1.0 - abs(inUv.y)*0.5) * smoothstep(-1.0, 0.2, inUv.y);    // hot at the front
      cl    = mix(vec3(1.0, 0.28, 0.04), vec3(1.0, 0.75, 0.3), inGlint) * 2.2;
      } else {
      const float r = length(inUv);
      shape = exp(-r*r*4.0);
      cl    = push.tint.rgb * 1.6 * inGlint;
      }
    const float a = shape * inAlpha;
    if(a<=0.002)
      discard;
    outColor = vec4(cl * a * fogAt().a, 0.0);
    return;
    }

  const bool rain = kind==KRain;
  float shape;
  if(rain)
    shape = (1.0 - abs(inUv.x)) * (1.0 - abs(inUv.y)*0.6);
  else if(kind==KCrystal)
    shape = 1.0 - smoothstep(0.75, 1.0, abs(inUv.x) + abs(inUv.y));   // a sharp lozenge
  else
    shape = 1.0 - smoothstep(0.35, 1.0, length(inUv));
  float alpha = shape * inAlpha * (rain ? 0.35 : kind==KCrystal ? 0.6 : 0.85);
  if(alpha<=0.002)
    discard;

  const vec3 albedo = rain ? vec3(0.55, 0.6, 0.65) : kind==KCrystal ? vec3(0.72, 0.86, 1.0) : vec3(0.9, 0.92, 0.95);
  const vec3 light  = scene.sunColor * max(scene.sunDir.y, 0.0) * 0.6 + scene.ambient * 2.0
                    + NightAmbient * Fd_Lambert;
  vec3 color = albedo * light;

  // fog at this particle's own depth
  const vec4 fog = fogAt();
  color = color*fog.a + fog.rgb*scene.GSunIntensity;

  color   *= scene.exposure;
  vec3 glow = vec3(0.0);
  if(kind==KCrystal)
    glow = vec3(0.85, 0.95, 1.0) * inGlint * shape * inAlpha * 2.5 * fog.a;   // a glint, by night as by day
  outColor = vec4(color*alpha + glow, alpha);
  }
