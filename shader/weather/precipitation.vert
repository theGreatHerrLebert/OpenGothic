#version 450
#extension GL_ARB_separate_shader_objects : enable
#extension GL_GOOGLE_include_directive    : enable

#include "scene.glsl"
#include "common.glsl"

// Snow and rain as world-anchored particles (docs/plan-weather.md). Nothing is stored: each particle's place comes from
// its number and the time, inside a box around the camera that it wraps through, so the field never ends and never
// follows the camera. Six vertices per particle, one instance each.
// Magical weather uses the same pass: embers (fire rain), shards (crystal storm), motes (arcane mist), and in a draw
// of their own a handful of meteors far off in the sky, which never pass through the box.

layout(binding = 0, std140) uniform UboScene {
  SceneDesc scene;
  };

layout(push_constant, std430) uniform Push {
  vec4  heightBox;  // the roof map's (min x, min z, 1/width, 1/depth) in world cm
  vec2  wind;       // cm per second along x and z
  float time;       // seconds of game time
  float intensity;  // 0..1
  uint  kind;       // 1 snow, 2 rain, 3 fire, 4 crystal, 5 motes, 6 meteors, 7 shooting stars
  uint  pad0, pad1, pad2;
  vec4  tint;       // motes: their colour in rgb, the height of their layer's base in w (world cm)
  } push;

layout(binding = 2) uniform sampler2D roofMap;   // highest static surface over each square, seen from above

layout(location = 0) out vec2  outUv;
layout(location = 1) out float outAlpha;
layout(location = 2) out vec3  outPos;
layout(location = 3) out float outGlint;   // shards: a glint; embers and motes: their flicker; meteors: unused

const float BoxSide   = 3000.0;   // cm around the camera, x and z
const float BoxHeight = 2000.0;
const float MoteLayer = 900.0;    // cm: the motes' layer, from a little under its base upwards

const uint KSnow = 1u, KRain = 2u, KFire = 3u, KCrystal = 4u, KMotes = 5u, KMeteor = 6u, KStar = 7u;

uint hashU(uint x) {
  x ^= x >> 16; x *= 0x7feb352du;
  x ^= x >> 15; x *= 0x846ca68bu;
  x ^= x >> 16;
  return x;
  }

float rnd(uint id, uint salt) {
  return float(hashU(id*4u + salt) & 0xFFFFFFu) / float(0xFFFFFF);
  }

vec3 wrapAround(vec3 p, vec3 c, float height) {
  p.xz = c.xz + mod(p.xz - c.xz + BoxSide*0.5, BoxSide) - BoxSide*0.5;
  p.y  = c.y  + mod(p.y  - c.y  + height*0.5, height) - height*0.5;
  return p;
  }

void hide(vec2 c, vec3 p) {
  gl_Position = vec4(0.0, 0.0, -2.0, 1.0);   // outside the clip volume: nothing drawn
  outUv = c; outAlpha = 0.0; outPos = p; outGlint = 0.0;
  }

// A meteor: one of a few slots, each with its own rhythm; in each of its cycles a new path, far off over the land.
// A shooting star on a clear night is the same, higher up, rarer, quicker and finer.
void meteor(vec2 c, bool star) {
  const uint  id     = uint(gl_InstanceIndex);
  const float period = (star ? mix(25.0, 70.0, rnd(id, 0)) : mix(9.0, 22.0, rnd(id, 0))) / max(push.intensity, 0.25);
  const float shown  = star ? mix(0.5, 0.9, rnd(id, 2)) : 1.6;   // seconds it crosses the sky
  const float tt     = push.time + rnd(id, 1)*period;
  const uint  cycle  = uint(floor(tt/period));
  const float u      = tt - float(cycle)*period;
  if(u>shown) {
    hide(c, scene.camPos);
    return;
    }
  const uint  h    = hashU(id*7919u + cycle);
  const float az   = rnd(h, 0)*6.2832;
  const float el   = star ? mix(0.6, 1.3, rnd(h, 1)) : mix(0.4, 1.0, rnd(h, 1));   // 34 to 75, or 23 to 57 degrees up
  const vec3  dirS = vec3(cos(az)*cos(el), sin(el), sin(az)*cos(el));
  const vec3  side = normalize(vec3(-sin(az), 0.0, cos(az))) * (rnd(h, 2)<0.5 ? -1.0 : 1.0);
  const vec3  mv   = normalize(side + vec3(0.0, -(star ? mix(0.15, 0.5, rnd(h, 3)) : mix(0.45, 0.9, rnd(h, 3))), 0.0));
  const float far  = 80000.0;                                // 800 m: within the camera's 1 km
  const float speed = star ? 60000.0 : 30000.0;
  const vec3  head = scene.camPos + dirS*far + mv*(u - shown*0.5)*speed;
  const float len  = (star ? 9000.0 : 15000.0) * smoothstep(0.0, shown*0.22, u);   // the trail grows behind it
  const vec3  mid  = head - mv*len*0.5;
  const vec3  toCam = normalize(scene.camPos - mid);
  const vec3  right = normalize(cross(mv, toCam)) * (star ? 90.0 : 260.0);
  const vec3  wp    = mid + right*c.x + mv*(len*0.5)*c.y;
  outUv       = c;
  outAlpha    = sin(3.14159*u/shown);                          // flares up and burns out
  outPos      = wp;
  outGlint    = 0.0;
  gl_Position = scene.viewProject * vec4(wp, 1.0);
  }

void main() {
  const vec2 corners[6] = vec2[](vec2(-1,-1), vec2(1,-1), vec2(1,1), vec2(-1,-1), vec2(1,1), vec2(-1,1));
  const vec2 c    = corners[gl_VertexIndex % 6];
  if(push.kind==KMeteor || push.kind==KStar) {
    meteor(c, push.kind==KStar);
    return;
    }
  const uint id   = uint(gl_InstanceIndex);
  const uint kind = push.kind;
  const bool streak = kind==KRain || kind==KFire;

  float fall = 110.0;
  if(kind==KRain)    fall = 900.0;
  if(kind==KFire)    fall = 520.0;
  if(kind==KCrystal) fall = 240.0;
  if(kind==KMotes)   fall = -22.0;                    // they rise, slowly
  fall *= mix(0.8, 1.25, rnd(id,3));

  // Embers come down slanting, as from somewhere over there; shards ride the wind harder than snow.
  vec2 drift = push.wind;
  if(kind==KFire)    drift += vec2(140.0, 70.0);
  if(kind==KCrystal) drift *= 1.6;
  if(kind==KMotes)   drift *= 0.15;

  vec3 p;
  p.x = rnd(id,0)*BoxSide   + drift.x*push.time;
  p.z = rnd(id,1)*BoxSide   + drift.y*push.time;
  p.y = rnd(id,2)*BoxHeight - fall*push.time;
  if(kind==KSnow || kind==KCrystal || kind==KMotes) {
    // each flake flutters at its own pace, so the snow never slides down as one sheet; shards less, motes wander
    const float f   = mix(0.6, 1.4, rnd(id,4)) * (kind==KMotes ? 0.4 : 1.0);
    const float amp = kind==KCrystal ? 8.0 : kind==KMotes ? 45.0 : 18.0;
    p.x += sin(push.time*f        + rnd(id,5)*6.2832)*amp;
    p.z += cos(push.time*f*0.73   + rnd(id,6)*6.2832)*amp;
    }
  // Motes hang in a layer over the ground (the fog's, if any): wrapped around its middle, not the camera's height.
  vec3 centre = scene.camPos;
  float height = BoxHeight;
  if(kind==KMotes) {
    p.y    = rnd(id,2)*MoteLayer - fall*push.time;
    height = MoteLayer;
    centre.y = (push.tint.w < -1.0e8 ? scene.camPos.y - 250.0 : push.tint.w) + MoteLayer*0.5 - 150.0;
    }
  p = wrapAround(p, centre, height);

  const vec3  d    = p - scene.camPos;
  const float dist = length(d);
  float a = 1.0 - smoothstep(0.7, 1.0, max(abs(d.x), abs(d.z))/(BoxSide*0.5));   // no popping at the box's sides
  if(kind==KMotes) {
    const float y = (p.y - centre.y)/(height*0.5);
    a *= 1.0 - smoothstep(0.6, 1.0, abs(y));                                     // fading at the layer's top and foot
    a *= mix(1.0, 0.45, smoothstep(-0.6, 0.8, y));                               // denser low down
    } else {
    a *= 1.0 - smoothstep(0.8, 1.0, abs(d.y)/(BoxHeight*0.5));
    }
  a *= smoothstep(40.0, 120.0, dist);                                            // nothing right in the eye
  // Under a roof: something static above this point, higher than the particle, keeps it dry. Motes are in the air
  // itself, indoors too.
  const vec2  roofUv = (p.xz - push.heightBox.xy) * push.heightBox.zw;
  if(kind!=KMotes && all(greaterThanEqual(roofUv, vec2(0))) && all(lessThanEqual(roofUv, vec2(1)))) {
    const float roof = textureLod(roofMap, roofUv, 0).r;
    if(roof > p.y + 30.0)
      a = 0.0;
    }

  vec3  right, up;
  float glint = 0.0;
  if(streak) {
    const vec3 vel = normalize(vec3(drift.x, -fall, drift.y));
    right = normalize(cross(vel, d)) * (kind==KFire ? 1.4 : 0.7);
    up    = vel * (kind==KFire ? 13.0 : 32.0);
    glint = kind==KFire ? 0.55 + 0.45*sin(push.time*mix(9.0, 17.0, rnd(id,4)) + rnd(id,5)*6.2832) : 0.0;
    } else if(kind==KCrystal) {
    // a flat shard turning about itself: it catches the light when it faces just so
    const float size = mix(1.2, 2.8, rnd(id,7));
    const float spin = push.time*mix(1.5, 4.0, rnd(id,4)) + rnd(id,6)*6.2832;
    const float cs = cos(spin), sn = sin(spin);
    right = (scene.pfxLeft*cs + scene.pfxTop*sn) * size;
    up    = (scene.pfxTop*cs  - scene.pfxLeft*sn) * size * mix(1.6, 2.6, rnd(id,5));
    glint = pow(max(sin(spin*2.0 + rnd(id,2)*3.0), 0.0), 24.0);
    } else {
    const float size = kind==KMotes ? mix(1.5, 3.2, rnd(id,7)) : mix(1.6, 3.6, rnd(id,7));
    right = scene.pfxLeft * size;
    up    = scene.pfxTop  * size;
    if(kind==KMotes)
      glint = 0.35 + 0.65*pow(0.5 + 0.5*sin(push.time*mix(0.7, 1.8, rnd(id,4)) + rnd(id,6)*6.2832), 3.0);
    }
  const vec3 wp = p + right*c.x + up*c.y;

  if(a<=0.0) {
    hide(c, p);
    return;
    }
  outUv       = c;
  outAlpha    = a;
  outPos      = wp;
  outGlint    = glint;
  gl_Position = scene.viewProject * vec4(wp, 1.0);
  }
