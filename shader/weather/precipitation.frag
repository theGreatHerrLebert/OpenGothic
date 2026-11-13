#version 450
#extension GL_ARB_separate_shader_objects : enable
#extension GL_GOOGLE_include_directive    : enable

#include "sky/sky_common.glsl"
#include "scene.glsl"
#include "common.glsl"

// Lit by the sky like the game's own particles, fogged at the particle's own depth (it is drawn after the fog pass,
// which only knows the surface behind it), and written premultiplied into the linear scene.

layout(binding = 0, std140) uniform UboScene {
  SceneDesc scene;
  };
layout(binding = 1) uniform sampler3D fogLut;

layout(push_constant, std430) uniform Push {
  vec4  heightBox;  // the roof map's (min x, min z, 1/width, 1/depth) in world cm
  vec2  wind;       // cm per second along x and z
  float time;       // seconds of game time
  float intensity;  // 0..1
  uint  kind;       // 1 snow, 2 rain
  } push;

layout(location = 0) in  vec2  inUv;
layout(location = 1) in  float inAlpha;
layout(location = 2) in  vec3  inPos;
layout(location = 0) out vec4  outColor;

void main() {
  const bool rain = push.kind==2u;
  float shape = rain ? (1.0 - abs(inUv.x)) * (1.0 - abs(inUv.y)*0.6)
                     : 1.0 - smoothstep(0.35, 1.0, length(inUv));
  float alpha = shape * inAlpha * (rain ? 0.35 : 0.85);
  if(alpha<=0.002)
    discard;

  const vec3 albedo = rain ? vec3(0.55, 0.6, 0.65) : vec3(0.9, 0.92, 0.95);
  const vec3 light  = scene.sunColor * max(scene.sunDir.y, 0.0) * 0.6 + scene.ambient * 2.0
                    + NightAmbient * Fd_Lambert;
  vec3 color = albedo * light;

  // fog at this particle's own depth
  const vec2  uv    = gl_FragCoord.xy * scene.screenResInv;   // as fog.frag reads its LUT
  const float dZ    = linearDepth(gl_FragCoord.z, scene.clipInfo);
  const float d0    = linearDepth(dFogMin, scene.clipInfo);
  const float d1    = linearDepth(dFogMax, scene.clipInfo);
  const vec4  fog   = textureLod(fogLut, vec3(uv, (dZ-d0)/(d1-d0)), 0);
  color = color*fog.a + fog.rgb*scene.GSunIntensity;

  color   *= scene.exposure;
  outColor = vec4(color*alpha, alpha);
  }
