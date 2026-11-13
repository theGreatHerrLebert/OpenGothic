#version 450
#extension GL_ARB_separate_shader_objects : enable
#extension GL_GOOGLE_include_directive    : enable

#include "scene.glsl"
#include "common.glsl"

// Snow and rain as world-anchored particles (docs/plan-weather.md). Nothing is stored: each particle's place comes from
// its number and the time, inside a box around the camera that it wraps through, so the field never ends and never
// follows the camera. Six vertices per particle, one instance each.

layout(binding = 0, std140) uniform UboScene {
  SceneDesc scene;
  };

layout(push_constant, std430) uniform Push {
  vec4  heightBox;  // the roof map's (min x, min z, 1/width, 1/depth) in world cm
  vec2  wind;       // cm per second along x and z
  float time;       // seconds of game time
  float intensity;  // 0..1
  uint  kind;       // 1 snow, 2 rain
  } push;

layout(binding = 2) uniform sampler2D roofMap;   // highest static surface over each square, seen from above

layout(location = 0) out vec2  outUv;
layout(location = 1) out float outAlpha;
layout(location = 2) out vec3  outPos;

const float BoxSide   = 3000.0;   // cm around the camera, x and z
const float BoxHeight = 2000.0;

uint hashU(uint x) {
  x ^= x >> 16; x *= 0x7feb352du;
  x ^= x >> 15; x *= 0x846ca68bu;
  x ^= x >> 16;
  return x;
  }

float rnd(uint id, uint salt) {
  return float(hashU(id*4u + salt) & 0xFFFFFFu) / float(0xFFFFFF);
  }

vec3 wrapAround(vec3 p, vec3 c) {
  p.xz = c.xz + mod(p.xz - c.xz + BoxSide*0.5, BoxSide) - BoxSide*0.5;
  p.y  = c.y  + mod(p.y  - c.y  + BoxHeight*0.5, BoxHeight) - BoxHeight*0.5;
  return p;
  }

void main() {
  const vec2 corners[6] = vec2[](vec2(-1,-1), vec2(1,-1), vec2(1,1), vec2(-1,-1), vec2(1,1), vec2(-1,1));
  const uint id   = uint(gl_InstanceIndex);
  const bool rain = push.kind==2u;
  const vec2 c    = corners[gl_VertexIndex % 6];

  const float fall = (rain ? 900.0 : 110.0) * mix(0.8, 1.25, rnd(id,3));
  vec3 p;
  p.x = rnd(id,0)*BoxSide   + push.wind.x*push.time;
  p.z = rnd(id,1)*BoxSide   + push.wind.y*push.time;
  p.y = rnd(id,2)*BoxHeight - fall*push.time;
  if(!rain) {
    // each flake flutters at its own pace, so the snow never slides down as one sheet
    const float f = mix(0.6, 1.4, rnd(id,4));
    p.x += sin(push.time*f        + rnd(id,5)*6.2832)*18.0;
    p.z += cos(push.time*f*0.73   + rnd(id,6)*6.2832)*18.0;
    }
  p = wrapAround(p, scene.camPos);

  const vec3  d    = p - scene.camPos;
  const float dist = length(d);
  float a = 1.0 - smoothstep(0.7, 1.0, max(abs(d.x), abs(d.z))/(BoxSide*0.5));   // no popping at the box's sides
  a      *= 1.0 - smoothstep(0.8, 1.0, abs(d.y)/(BoxHeight*0.5));
  a      *= smoothstep(40.0, 120.0, dist);                                       // nothing right in the eye
  // Under a roof: something static above this point, higher than the particle, keeps it dry.
  const vec2  roofUv = (p.xz - push.heightBox.xy) * push.heightBox.zw;
  if(all(greaterThanEqual(roofUv, vec2(0))) && all(lessThanEqual(roofUv, vec2(1)))) {
    const float roof = textureLod(roofMap, roofUv, 0).r;
    if(roof > p.y + 30.0)
      a = 0.0;
    }

  vec3 right, up;
  if(rain) {
    const vec3 vel = normalize(vec3(push.wind.x, -fall, push.wind.y));
    right = normalize(cross(vel, d)) * 0.7;
    up    = vel * 32.0;
    } else {
    const float size = mix(1.6, 3.6, rnd(id,7));
    right = scene.pfxLeft * size;
    up    = scene.pfxTop  * size;
    }
  const vec3 wp = p + right*c.x + up*c.y;

  if(a<=0.0) {
    gl_Position = vec4(0.0, 0.0, -2.0, 1.0);   // outside the clip volume: nothing drawn
    outUv = c; outAlpha = 0.0; outPos = p;
    return;
    }
  outUv       = c;
  outAlpha    = a;
  outPos      = wp;
  gl_Position = scene.viewProject * vec4(wp, 1.0);
  }
