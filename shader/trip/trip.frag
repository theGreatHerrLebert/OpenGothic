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
  float pad;
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

vec3 hueColor(float h) {
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

void main() {
  const float I  = push.intensity;
  const float t  = push.time;
  const vec2  px = 1.0/vec2(textureSize(sceneImage, 0));

  // A slow, gentle warp: long waves that drift rather than flutter. The beat's pulse is a zoom, set from Python.
  const float amp1 = 0.0035*I*(1.0 + push.bass*0.3);
  const float amp2 = 0.0012*I*(1.0 + push.mid *0.3);
  vec2 warp = vec2(cos(uv.y*9.0 + t*0.5)*amp1 + sin(uv.x*7.0 + uv.y*5.0 + t*0.9)*amp2,
                   sin(uv.x*8.0 + t*0.4)*amp1 + cos(uv.y*6.0 - uv.x*4.0 + t*0.7)*amp2);
  vec2 suv = clamp(uv + warp, vec2(0.0), vec2(1.0));

  // Chromatic split: red and blue drift apart, wider with the treble.
  float split = 0.0017*I*(1.0 + push.treble*0.8);
  vec3  c = vec3(texture(sceneImage, suv + vec2(split, 0.0)).r,
                 texture(sceneImage, suv).g,
                 texture(sceneImage, suv - vec2(split, 0.0)).b);

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

  // Saturation and a slowly turning hue: the bass pushes the saturation.
  float a  = t*0.24*I + push.mid*0.15;
  float ca = cos(a), sa = sin(a);
  vec3  n  = vec3(c.r*(0.667 + ca*0.333) + c.g*(0.333 - ca*0.333 + sa*0.577) + c.b*(0.333 - ca*0.333 - sa*0.577),
                  c.r*(0.333 - ca*0.333 - sa*0.577) + c.g*(0.667 + ca*0.333) + c.b*(0.333 - ca*0.333 + sa*0.577),
                  c.r*(0.333 - ca*0.333 + sa*0.577) + c.g*(0.333 - ca*0.333 - sa*0.577) + c.b*(0.667 + ca*0.333));
  float L   = lum(n);
  float sat = 1.0 + (0.4 + push.bass*0.2)*I;
  c = clamp(vec3(L) + (n - vec3(L))*sat, 0.0, 1.0);

  // Tracers: the previous finished frame, drifting slightly, bled SUBTRACTIVELY. A bright trail survives many frames,
  // the dim haze is gone in a few, so trails never build up into a white-out (see Solaris's bled_feedback).
  vec2 drift = vec2(sin(t*0.35)*1.2, cos(t*0.25)*0.8)*I*(1.0 + push.bass*0.2)*px*2.0;
  vec3 prev  = max(texture(historyImage, clamp(uv + drift, vec2(0.0), vec2(1.0))).rgb - vec3(26.0/255.0), 0.0);
  float keep = clamp((0.50 + push.bass*0.18)*I*push.tracers, 0.0, 0.85);
  c = mix(c, prev, keep);

  outColor   = vec4(c, 1.0);
  outHistory = vec4(c, 1.0);
  }
