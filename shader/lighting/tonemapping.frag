#version 450

#extension GL_ARB_separate_shader_objects : enable
#extension GL_GOOGLE_include_directive : enable
#extension GL_EXT_control_flow_attributes : enable

#include "scene.glsl"
#include "common.glsl"
#include "lighting/tonemapping.glsl"
#include "lighting/purkinje_shift.glsl"

#include "upscale/lanczos.glsl"

layout(push_constant, std140) uniform PushConstant {
  VideoSettings settings;
  } push;

layout(binding  = 0, std140) uniform UboScene {
  SceneDesc scene;
  };
layout(binding  = 1) uniform sampler2D textureD;
layout(binding  = 2) uniform sampler2D depthD;   // for the heat's shimmer (docs/plan-weather.md)

layout(location = 0) in  vec2 uv;
layout(location = 0) out vec4 outColor;

const uvec3 TONEMAP_DITHER_TARGET_BITS =  uvec3(8, 8, 8); // hardcoded for now -> adjust in future for HDR support or 6 bit monitors

// https://advances.realtimerendering.com/s2021/jpatry_advances2021/index.html
// https://citeseerx.ist.psu.edu/viewdoc/download?doi=10.1.1.40.9608&rep=rep1&type=pdf
vec4 rgb2lmsr(vec3 c) {
  const mat4x3 m = mat4x3(
        0.31670331, 0.70299344, 0.08120592,
        0.10129085, 0.72118661, 0.12041039,
        0.01451538, 0.05643031, 0.53416779,
        0.01724063, 0.60147464, 0.40056206);
  return c * m;
  }

vec3 lms2rgb(vec3 c) {
  const mat3 m = mat3(
        4.57829597, -4.48749114,  0.31554848,
        -0.63342362,  2.03236026, -0.36183302,
        -0.05749394, -0.09275939,  1.90172089);
  return c * m;
  }

// https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2630540/pdf/nihms80286.pdf
vec3 _purkinjeShift(vec3 c) {
  const vec3  m  = vec3(0.63721, 0.39242, 1.6064);
  const float K  = 45.0;
  const float S  = 10.0;
  const float k3 = 0.6;
  const float k5 = 0.2;
  const float k6 = 0.29;
  const float rw = 0.139;
  const float p  = 0.6189;

  vec4 lmsr = rgb2lmsr(c);

  vec3 g = vec3(1.0) / sqrt(vec3(1.0) + (vec3(0.33) / m) * (lmsr.xyz + vec3(k5, k5, k6) * lmsr.w));

  float rc_gr = (K / S) * ((1.0 + rw * k3) * g.y / m.y - (k3 + rw) * g.x / m.x) * k5 * lmsr.w;
  float rc_by = (K / S) * (k6 * g.z / m.z - k3 * (p * k5 * g.x / m.x + (1.0 - p) * k5 * g.y / m.y)) * lmsr.w;
  float rc_lm = K * (p * g.x / m.x + (1.0 - p) * g.y / m.y) * k5 * lmsr.w;

  vec3 lms_gain = vec3(-0.5 * rc_gr + 0.5 * rc_lm, 0.5 * rc_gr + 0.5 * rc_lm, rc_by + rc_lm);
  vec3 rgb_gain = lms2rgb(lms_gain);

  return rgb_gain;
  }

float luminance(vec3 rgb) {
  const vec3 W = vec3(0.2125, 0.7154, 0.0721);
  return dot(rgb, W);
  }

// Heat: how far away a pixel is (cm) and how much of the shimmer and bleaching it gets, from 15 m on and
// strongest along the ground towards the horizon, never above it.
float heatAt(vec2 at, out float dist) {
  const float z   = textureLod(depthD, at, 0).r;
  dist            = linearDepth(z, scene.clipInfo);
  if(z>=1.0)
    return 0.0;   // the sky: no shimmer, no bleaching
  const vec4  wp  = scene.viewProjectInv*vec4(at*2.0-vec2(1.0), z, 1.0);
  const vec3  dir = normalize(wp.xyz/wp.w - scene.camPos);
  const float low = 1.0 - smoothstep(0.02, 0.12, dir.y);   // land below the eye and just above it, not hills high up
  return smoothstep(800.0, 6000.0, dist) * low;
  }

// The nearest surface the colour at `at` is made from. A shimmered pixel is read with one bilinear tap (not the
// upscale filter), so its footprint is exactly the 2x2 texels around it.
float nearestAround(vec2 at) {
#if defined(UPSCALE)
  const ivec2 size = textureSize(depthD, 0);
  const ivec2 c    = ivec2(floor(at*vec2(size) - 0.5));
  float n = 1.0e30;
  for(int i=0; i<4; ++i) {
    const ivec2 t = clamp(c + ivec2(i&1, i>>1), ivec2(0), size-1);
    n = min(n, linearDepth(texelFetch(depthD, t, 0).r, scene.clipInfo));
    }
  return n;
#else
  float n;
  heatAt(at, n);
  return n;
#endif
  }

void main() {
  float exposure   = scene.exposure;

  vec2  at         = uv;
  float bleach     = 0.0;
  if(scene.weatherHeat>0.001) {
    // Rising waves of air, finer and faster far away; a sample that would come from something nearer is not taken,
    // so the shimmer never smears a close silhouette over the distance.
    float dist;
    const float k   = heatAt(uv, dist) * scene.weatherHeat;
    const float t   = float(scene.tickCount32 % 600000u)/1000.0;
    const float f   = 1.0 + dist/20000.0;
    // as the trip's Emberheart, milder: slow, broad waves rising, a second one across
    const vec2  off = vec2(sin(uv.y*120.0*f - t*4.8 + sin(uv.x*18.0 + t*0.6)*2.0),
                           sin(uv.y*90.0*f  - t*3.0 + uv.x*30.0)*0.7) * (0.0045*k);
    if(k>0.0 && nearestAround(uv + off)>dist*0.6)
      at = uv + off;
    bleach = k;
  }

#if defined(UPSCALE)
  // where it shimmers, one bilinear tap whose footprint was checked; the sharp filter everywhere else
  vec3  color      = at!=uv ? textureLod(textureD, at, 0).rgb : lanczosUpscale(textureD, at).rgb;
#else
  vec3  color      = textureLod(textureD, at, 0).rgb;
#endif
  // the whole day a little warmer, as the trip's ember wash but faint
  color *= mix(vec3(1.0), vec3(1.07, 1.0, 0.88), scene.weatherHeat);
  if(bleach>0.0) {
    // the far land pales and warms in the haze of a hot day
    const float l = luminance(color);
    color = mix(color, vec3(l)*vec3(1.12, 1.0, 0.78)*1.15, bleach*scene.weatherHeat*0.6);
  }

  {
    // outColor = vec4(srgbEncode(color), 1);
    // outColor = vec4(color, 1);
    // return;
  }

  {
    // outColor = vec4(vec3(luminance(color/exposure)/100000.0), 1);
    // return;
  }

  {
    // night shift
    // const vec3 shift = purkinjeShift(color/exposure)*exposure;
    const vec3 shift = purkinjeShift(color/exposure, 1.5)*exposure;
    //color += shift;
    // in vanilla game night time attenuated as rgb{18 16 60}
    // color += vec3(shift.r, 0, shift.b);
  }

  color    = gameTonemap(color, push.settings);
  color   += dither(gl_FragCoord.xy, TONEMAP_DITHER_TARGET_BITS); 
  outColor = vec4(color, 1.0);
  }
