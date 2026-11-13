#version 450

#extension GL_ARB_separate_shader_objects : enable
#extension GL_GOOGLE_include_directive : enable

#if defined(VIRTUAL_SHADOW)
#include "virtual_shadow/vsm_common.glsl"
#endif

#include "materials_common.glsl"
#include "water/gerstner_wave.glsl"
#include "lighting/shadow_sampling.glsl"
#include "lighting/tonemapping.glsl"

#if defined(MAT_VARYINGS)
layout(location = 0) in flat uint bucketId;
layout(location = 1) in Varyings  shInp;
#endif

#if defined(VIRTUAL_SHADOW)
layout(location = 3) in flat uint vsmMipId;
#endif

#if DEBUG_DRAW
layout(location = DEBUG_DRAW_LOC) in flat uint debugId;
#endif

#if defined(GBUFFER)
layout(location = 0) out vec4 outDiffuse;
layout(location = 1) out uint outNormal;
#elif defined(WATER)
layout(location = 0) out vec4 outColor;
layout(location = 1) out vec4 outDiffuse;
layout(location = 2) out uint outNormal;
#elif !defined(DEPTH_ONLY)
layout(location = 0) out vec4 outColor;
#endif

#if defined(VIRTUAL_SHADOW)
layout(push_constant, std430) uniform Push {
  uint commandId;
  } push;
#endif

#if defined(WATER) || defined(GHOST)
float unproject(float depth) {
  mat4 projInv = scene.projectInv;
  vec4 o;
  o.z = depth * projInv[2][2] + projInv[3][2];
  o.w = depth * projInv[2][3] + projInv[3][3];
  return o.z/o.w;
  }
#endif

bool isFlat() {
#if defined(GBUFFER) && defined(FLAT_NORMAL)
  {
    vec3 pos   = shInp.pos;
    vec3 dx    = dFdx(pos);
    vec3 dy    = dFdy(pos);
    vec3 flatN = (cross(dx,dy));
    if(dot(normalize(flatN),scene.sunDir)<=0.01)
      return true;
  }
#endif
  return false;
  }

float encodeHintBits() {
  const int flt  = (isFlat() ? 1 : 0) << 1;
#if defined(ATEST)
  const int atst = (1) << 2;
#else
  const int atst = (0) << 2;
#endif

#if defined(WATER)
  const int water = (gl_FrontFacing) ? 0 : (1 << 3);
#elif defined(LVL_OBJECT)
  // const int water = (bucket.envMapping>0.01 ? 1 : 0) << 3;
  const int water = (0) << 3;
#else
  const int water = (0) << 3;
#endif

  return float(flt | atst | water)/255.0;
  }

#if defined(GBUFFER)
vec3 flatNormal() {
#if defined(FLAT_NORMAL)
  vec3 pos   = shInp.pos;
  vec3 dx    = dFdx(pos);
  vec3 dy    = dFdy(pos);
  return normalize(cross(dx,dy));
#else
  return shInp.normal;
#endif
  }
#endif

#if defined(FORWARD)
float lambert(const vec3 normal) {
  return clamp(dot(scene.sunDir,normal), 0.0, 1.0);
  }

float henyeyGreenstein(float cosTheta, float g) {
  //g = clamp(g, -0.99, 0.99);
  float g2 = g * g;
  float denom = 1.0 + g2 - 2.0 * g * cosTheta;
  return (1.0 - g2) / (4.0 * M_PI * pow(denom, 1.5));
  }

vec3 diffuseLight(float a) {
  vec3  norm   = normalize(shInp.normal);
#if (MESH_TYPE==T_PFX)
  vec3  view   = normalize(shInp.pos - scene.camPos);
  float light  = henyeyGreenstein(-dot(view,scene.sunDir), a*0.63);
#else
  float light  = lambert(norm);
#endif
  float shadow = calcShadow(vec4(shInp.pos,1), 0, scene, textureSm0, textureSm1);

  vec3  lcolor  = scene.sunColor * light * shadow;
  vec3  ambient = scene.ambient + (norm.y*0.25+0.75) * NightAmbient * Fd_Lambert;
  vec3  sky     = vec3(0); // TODO: irradiance

  return (lcolor + ambient + ambient);
  }

vec4 dbgLambert() {
  vec3  norm = normalize(shInp.normal);
  float l    = lambert(norm);
  return vec4(l,l,l,1.0);
  }
#endif

#if defined(MAT_UV)
vec4 diffuseTex() {
#if !defined(SIMPLE_MAT) && (MESH_TYPE!=T_PFX)
  ivec2 texAniMapDirPeriod = bucket[bucketId].texAniMapDirPeriod;
  float alphaWeight        = bucket[bucketId].alphaWeight;
#else
  ivec2 texAniMapDirPeriod = ivec2(0);
  float alphaWeight        = 1;
#endif

#if !defined(SIMPLE_MAT)
  vec2 texAnim = vec2(0);
  {
    // FIXME: this not suppose to run for every-single material
    if(texAniMapDirPeriod.x!=0) {
      uint fract = scene.tickCount32 % abs(texAniMapDirPeriod.x);
      texAnim.x  = float(fract)/float(texAniMapDirPeriod.x);
      }
    if(texAniMapDirPeriod.y!=0) {
      uint fract = scene.tickCount32 % abs(texAniMapDirPeriod.y);
      texAnim.y  = float(fract)/float(texAniMapDirPeriod.y);
      }
  }
  const vec2 uv = shInp.uv + texAnim;
#else
  const vec2 uv = shInp.uv;
#endif

#if defined(BINDLESS)
  nonuniformEXT uint tId = bucketId;
#else
  const         uint tId = 0;
#endif

  vec4 tex = texture(sampler2D(textureMain[tId], samplerMain),uv);

#if !defined(SIMPLE_MAT)
  tex.a *= alphaWeight;
#endif

  // return vec4(1,1,1, tex.a);
  return tex;
  }
#endif

#if defined(GBUFFER) && (MESH_TYPE!=T_PFX)
// Snow lying on what faces up, and wet ground (docs/plan-weather.md): landscape, roofs, rocks, the tops of trees, but
// no characters, and nothing under a static roof (the roof map). Patches grow with the cover.
float snowHash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7)))*43758.5453);
  }

float snowNoise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f*f*(3.0-2.0*f);
  return mix(mix(snowHash(i), snowHash(i+vec2(1,0)), f.x), mix(snowHash(i+vec2(0,1)), snowHash(i+vec2(1,1)), f.x), f.y);
  }

vec3 weatherWorldPos() {
#if defined(MAT_POSITION)
  return shInp.pos;
#else
  // objects carry no position: from the fragment's depth, as fog.frag does
  vec4 p = scene.viewProjectInv * vec4(gl_FragCoord.xy*scene.screenResInv*2.0-1.0, gl_FragCoord.z, 1.0);
  return p.xyz/p.w;
#endif
  }

vec3 snowCover(vec3 albedo) {
  if(scene.weatherCover<=0.001 && scene.weatherWet<=0.001)
    return albedo;
#if !defined(SIMPLE_MAT)
  if((bucket[bucketId].flags & (BK_SKIN|BK_MORPH))!=0)
    return albedo;   // people and animals stay as they are
#endif
  const vec3 pos = weatherWorldPos();
  const vec3 n   = normalize(shInp.normal);
  const vec2 ruv = (pos.xz - scene.weatherBox.xy) * scene.weatherBox.zw;
  float shelter = 0.0;
  if(all(greaterThanEqual(ruv, vec2(0))) && all(lessThanEqual(ruv, vec2(1)))) {
    // The map holds one height per cell; on a slope the surface itself rises within its cell, so the tolerance
    // grows with the cell's width and the surface's steepness before something counts as a roof above it. Five
    // samples around the point, each eased over 80 cm, let the snow thin out towards a wall instead of ending in a
    // hard line at a cell's edge.
    const float cell  = 1.0/(scene.weatherBox.z*float(textureSize(roofMap, 0).x));
    const float slope = sqrt(max(1.0-n.y*n.y, 0.0))/max(abs(n.y), 0.2);
#if defined(ATEST)
    const float tol   = 150.0 + cell*slope;   // foliage: the outer layer of a crown, not only its very top
#else
    const float tol   = 50.0 + cell*slope;
#endif
    const vec2  du    = vec2(0.75*cell*scene.weatherBox.z, 0.0);
    const vec2  dv    = vec2(0.0, 0.75*cell*scene.weatherBox.w);
    const vec2  taps[5] = vec2[](ruv, ruv+du, ruv-du, ruv+dv, ruv-dv);
    for(int i=0; i<5; ++i)
      shelter += smoothstep(tol, tol+80.0, textureLod(roofMap, taps[i], 0).r - pos.y);
    shelter /= 5.0;
    if(shelter>=0.999)
      return albedo;   // under a roof
    }
#if defined(ATEST)
  // Leaves are thin and mostly steep: snow catches on them well before they face up.
  const float up = smoothstep(0.0, 0.5, abs(n.y)) * 0.85;
#else
  const float up = smoothstep(0.55, 0.85, n.y);
#endif
  // Wet ground is darker; v1 has no gloss, the G-buffer has no channel for it (plan-weather.md).
  // Wet surfaces are darker and deeper in colour: soaked earth, stone and wood.
  const float wetness = scene.weatherWet*mix(0.6, 1.0, up)*(1.0-shelter);
  albedo = mix(albedo, pow(albedo, vec3(1.4))*0.72, wetness);
  if(scene.weatherCover<=0.001)
    return albedo;
  const vec2  p      = pos.xz/100.0;                       // metres
  const float noise  = snowNoise(p*0.35)*0.6 + snowNoise(p*1.7)*0.4;
  float       amount = clamp(scene.weatherCover*1.6 - (1.0-noise), 0.0, 1.0) * up * (1.0-shelter);
  // Footprints: packed snow, the ground half showing through.
  if(scene.weatherTrail.w>0.0) {
    // Four cells blended by where the point lies between their centres, so a print has round edges, not squares.
    const vec2  t  = (pos.xz - scene.weatherTrail.xy)*scene.weatherTrail.z - 0.5;
    const ivec2 c0 = ivec2(floor(t));
    const vec2  f  = t - vec2(c0);
    const int   n  = int(scene.weatherTrail.w);
    float print = 0.0;
    for(int k=0; k<4; ++k) {
      const ivec2 c = c0 + ivec2(k&1, k>>1);
      if(c.x<0 || c.y<0 || c.x>=n || c.y>=n)
        continue;
      const int   i    = c.y*n + c.x;
      const uint  cell = (trailCells[i>>1] >> uint((i&1)*16)) & 0xFFFFu;
      const float made = scene.weatherTrailY + (float(cell>>8) - 128.0)*25.0;   // where his foot was
      if(abs(pos.y - made) >= 150.0)   // not on a ledge above the path (the hero's position may sit at hip height)
        continue;
      const float w = ((k&1)!=0 ? f.x : 1.0-f.x) * ((k>>1)!=0 ? f.y : 1.0-f.y);
      print += w * float(cell & 0xFFu)/255.0;
      }
    amount *= 1.0 - smoothstep(0.05, 0.9, print)*0.75;
    }
  // A crystal storm's frost: glassy and blue, the ground still showing a little through it (plan-weather.md).
  const vec3 frost = mix(vec3(0.62, 0.79, 0.95), albedo*vec3(0.75, 0.9, 1.15) + vec3(0.12, 0.16, 0.22), 0.3);
  return mix(albedo, mix(vec3(0.86, 0.88, 0.92), frost, scene.weatherFrost), amount);   // texture space: lighting decodes it
  }
#endif

#if defined(GBUFFER)
void mainGBuffer(vec4 t) {
#if (MESH_TYPE!=T_PFX)
  t.rgb = snowCover(t.rgb);
#endif
  outDiffuse.rgb = t.rgb;
  outDiffuse.a   = encodeHintBits();
  outNormal      = encodeNormal(shInp.normal);
  // outNormal      = vec4(flatNormal()*0.5 + vec3(0.5), 1.0);
#if DEBUG_DRAW
  outDiffuse.rgb *= debugColors[debugId%debugColors.length()];
#endif
  }
#endif

#if defined(FORWARD)
void mainForward(vec4 t) {
  vec3  color = t.rgb;
  float alpha = t.a;

#if defined(ATEST)
  alpha = (alpha-0.5)*2.0;
#endif

  color = textureAlbedo(color.rgb);
  color *= diffuseLight(alpha);
  color *= scene.exposure;

  outColor = vec4(color,alpha);
  }
#endif

#if defined(EMISSIVE)
void mainEmissive(vec4 t) {
  vec3 color = textureEmmisive(t.rgb);
  outColor = vec4(color,t.a);
  }
#endif

#if defined(GHOST)
void mainGhost(vec4 t) {
  vec3  color  = textureAlbedo(t.rgb) * 5.0;
  vec3  normal = normalize(shInp.normal);

  normal = (scene.viewProject*vec4(normal,0.0)).xyz;

  vec2  fragCoord = (gl_FragCoord.xy*scene.screenResInv)*2.0-vec2(1.0);
  fragCoord += normal.xy * 0.01;

  vec4 back = textureLod(sceneColor, (fragCoord*0.5+0.5), 0);

  outColor = vec4(mix(back.rgb * color, back.rgb, vec3(0.6)), t.a);
  }
#endif

#if defined(WATER)
vec4 underWaterColorDepth(vec3 normal) {
  const vec2  fragCoord = (gl_FragCoord.xy*scene.screenResInv)*2.0-vec2(1.0);
  const float ior       = IorWater;
  //return vec4(0);

  const vec3  camPos = scene.camPos;
  const vec3  view   = normalize(shInp.pos - camPos);
  const vec3  refr   = refract(view, normal, ior);

  vec3        back   = texelFetch(sceneColor,   ivec2(gl_FragCoord.xy), 0).rgb;
  const float depth  = texelFetch(gbufferDepth, ivec2(gl_FragCoord.xy), 0).r;

  const float ground = unproject(depth);
  const float water  = unproject(gl_FragCoord.z);
  float       dist   = (ground-water);

  const vec2 p2 = (gl_FragCoord.xy*scene.screenResInv) + normal.xz * min(dist*0.01,1.0) * 0.1;

  float depth2 = textureLod(gbufferDepth, p2, 0).r;
  if(depth2>gl_FragCoord.z) {
    back   = textureLod(sceneColor, p2, 0).rgb;
    const float ground2 = unproject(depth2);
    dist = (ground2-water);
    } else {
    depth2 = depth;
    }

  vec4 fragPos1 = scene.viewProjectInv*vec4(fragCoord,depth2,1.0);
  fragPos1.xyz /= fragPos1.w;

  //return vec4(back,length(fragPos1.xyz - fragPos0.xyz));
  return vec4(back,length(fragPos1.xyz - shInp.pos.xyz));
  }

vec3 waterScatter(vec3 back, vec3 normal, float len) {
  vec3  transmittance = waterTransmittance(len);
  // note: less sun light and less obsevable light
  transmittance = transmittance*transmittance;

  const float f       = fresnel(scene.sunDir,normal,IorWater);
  const vec3  scatter = f * scene.sunColor * (1-exp(-len/20000.0)) * max(scene.sunDir.y, 0);
  return (back + scatter*scene.exposure)*transmittance;
  }

vec4 waterShading(vec4 t, const vec3 normal) {
  const bool underWater = (scene.underWater!=0);

  const float ior = underWater ? IorAir : IorWater;

  vec4 camPos = scene.viewProjectInv*vec4(0,0,0,1.0);
  camPos.xyz /= camPos.w;

  const vec3  view   = normalize(shInp.pos - camPos.xyz);
  const vec3  refr   = refract(view, normal, ior);
        vec3  refl   = reflect(view, normal);

  const float f      = fresnel(refl,normal,ior);

  if(underWater) {
    vec3 back = texelFetch(sceneColor, ivec2(gl_FragCoord.xy), 0).rgb;
    return vec4(back.rgb * (1.0-f),1);
    }

  const vec4 back  = underWaterColorDepth(normal);
  const vec3 color = waterScatter(back.rgb, normal, back.a) * (1.0-f);
  // color = waterColor(color,normal) * WaterAlbedo ;
  return vec4(color,1);
  }

void mainWater(vec4 t) {
  const float waveMaxAmplitude = bucket[bucketId].waveMaxAmplitude;

  vec3 lx = dFdx(shInp.pos), ly = dFdy(shInp.pos);
  float minLength = max(length(lx),length(ly));

  Wave wx = wave(shInp.pos, minLength, waveIterationsHigh, waveAmplitude(waveMaxAmplitude));

  if(gl_FrontFacing) {
    // BROKEN: water mesh is two sided
    wx.normal = -wx.normal;
    }

  outColor       = waterShading(t,wx.normal);
  outDiffuse.rgb = t.rgb;
  outDiffuse.a   = encodeHintBits();
  outNormal      = encodeNormal(wx.normal);
  }
#endif

void main() {
#if defined(MAT_UV)
  vec4 t = diffuseTex();
#  if defined(ATEST)
  if(t.a<0.5)
    discard;
#  endif
#endif

#if defined(MAT_COLOR)
  t *= shInp.color;
#endif

#if defined(GBUFFER)
  mainGBuffer(t);
#elif defined(WATER)
  mainWater(t);
#elif defined(FORWARD) && !defined(DEPTH_ONLY)
  mainForward(t);
#elif defined(EMISSIVE) && !defined(DEPTH_ONLY)
  mainEmissive(t);
#elif defined(GHOST) && !defined(DEPTH_ONLY)
  mainGhost(t);
#endif

#if DEBUG_DRAW && !defined(GBUFFER) && !defined(DEPTH_ONLY)
  outColor   = vec4(debugColors[debugId%debugColors.length()],1.0);
#endif

  //outColor = vec4(inZ.xyz/inZ.w,1.0);
  //outColor = vec4(vec3(inPos.xyz)/1000.0,1.0);
  //outColor = vec4(vec3(shMap),1.0);
  //outColor = vec4(vec3(calcLight()),1.0);
  //outColor = vec4(vec3(calcShadow()),1.0);
  //vec3 shPos0  = (shInp.shadowPos[0].xyz)/shInp.shadowPos[0].w;
  //outColor   = vec4(vec3(shPos0.xy,0),1.0);
  //outColor = dbgLambert();
  }
