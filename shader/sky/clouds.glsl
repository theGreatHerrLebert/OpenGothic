#ifndef CLOUDS_GLSL
#define CLOUDS_GLSL

vec4 clouds(vec3 at, float nightPhase, vec3 highlight,
            vec2 dxy0, vec2 dxy1,
            in sampler2D dayL1,   in sampler2D dayL0,
            in sampler2D nightL1, in sampler2D nightL0) {
  vec3  cloudsAt = normalize(at);
  vec2  texc     = 2000.0*vec2(atan(cloudsAt.z,cloudsAt.y), atan(cloudsAt.x,cloudsAt.y));

#if defined(SKY_LOD)
  vec4  cloudDL1 = textureLod(dayL1,   texc*0.3 + dxy1, SKY_LOD);
  vec4  cloudDL0 = textureLod(dayL0,   texc*0.3 + dxy0, SKY_LOD);
  vec4  cloudNL1 = textureLod(nightL1, texc*0.3 + dxy1, SKY_LOD);
  vec4  cloudNL0 = textureLod(nightL0, texc*0.6 + vec2(0.5), SKY_LOD); // stars
#else
  vec4  cloudDL1 = texture(dayL1,   texc*0.3 + dxy1);
  vec4  cloudDL0 = texture(dayL0,   texc*0.3 + dxy0);
  vec4  cloudNL1 = texture(nightL1, texc*0.3 + dxy1);
  vec4  cloudNL0 = texture(nightL0, texc*0.6 + vec2(0.5)); // stars
#endif

  cloudDL0.a   = cloudDL0.a*0.2;
  cloudDL1.a   = cloudDL1.a*0.2;
  cloudNL0.a   = cloudNL0.a*1.0; // stars
  cloudNL1.a   = cloudNL1.a*0.1;

  vec4 day       = (cloudDL0+cloudDL1)*0.5;
  vec4 night     = (cloudNL0+cloudNL1)*0.5;

  // Clouds (LDR textures from original game) - need to adjust
  day.rgb   = srgbDecode(day.rgb);
  night.rgb = srgbDecode(night.rgb);

  day.rgb   = day.rgb  *highlight*5.0;
  night.rgb = night.rgb*0.000014;

  day  .a   = day  .a*(1.0-nightPhase);
  //night.a   = night.a*(nightPhase);

  vec4 color = mixClr(day,night);
  // color.rgb += hday;

  return color;
  }

// Weather clouds (docs/plan-weather.md): the same cloud layers pulled together into a closed, dark cover with their
// structure kept; slate grey for rain, a milky grey for snow. They cover the sky rather than brighten it.
vec3 weatherClouds(vec3 clear, vec3 skyColor, vec3 lum, vec3 at, vec2 dxy0, vec2 dxy1,
                   in sampler2D dayL1, in sampler2D dayL0, float overcast, float snowy, float nightPhase) {
  if(overcast<=0.001)
    return clear;
  vec3  cloudsAt = normalize(at);
  vec2  texc     = 2000.0*vec2(atan(cloudsAt.z,cloudsAt.y), atan(cloudsAt.x,cloudsAt.y));
  float a0       = texture(dayL0, texc*0.3 + dxy0).a;
  float a1       = texture(dayL1, texc*0.3 + dxy1).a;
  float a2       = texture(dayL1, texc*0.11 + dxy0*0.7).a;           // a broader layer for big shapes
  float density  = clamp(0.35 + 0.9*(a0*0.35 + a1*0.35 + a2*0.5), 0.0, 1.0);
  float cover    = clamp(overcast*1.25*density + overcast*0.25, 0.0, 1.0);
  float shade    = 0.55 + 0.45*(1.0 - density);                      // thick parts are darker underneath
  vec3  sky      = dot(lum, vec3(0.3, 0.59, 0.11)) * vec3(1.0) * 0.25;
  vec3  rain     = sky * vec3(0.55, 0.60, 0.68) * shade;
  vec3  snow     = sky * vec3(1.05, 1.08, 1.15) * mix(0.8, 1.0, shade);
  vec3  cloud    = mix(rain, snow, snowy) * (1.0 - nightPhase*0.8);
  return mix(clear, cloud, cover);
  }

vec3 applyClouds(vec3 skyColor, in sampler2D skyLUT, vec3 plPos, vec3 sunDir, vec3 view, float nightPhase,
                 vec2 dxy0, vec2 dxy1,
                 in sampler2D dayL1,   in sampler2D dayL0,
                 in sampler2D nightL1, in sampler2D nightL0,
                 float overcast, float snowy) {
  float L = rayIntersect(plPos, view, RClouds);
  // TODO: http://killzone.dl.playstation.net/killzone/horizonzerodawn/presentations/Siggraph15_Schneider_Real-Time_Volumetric_Cloudscapes_of_Horizon_Zero_Dawn.pdf
  // fake cloud scattering inspired by Henyey-Greenstein model
  vec3 lum  = vec3(0);
  lum += textureSkyLUT(skyLUT, plPos, vec3( view.x, view.y*0.0, view.z), sunDir);
  lum += textureSkyLUT(skyLUT, plPos, vec3(-view.x, view.y*0.0, view.z), sunDir);
  lum += textureSkyLUT(skyLUT, plPos, vec3(-view.x, view.y*0.0,-view.z), sunDir);
  lum += textureSkyLUT(skyLUT, plPos, vec3( view.x, view.y*0.0,-view.z), sunDir);
  //return lum;

  vec4 cloud = clouds((plPos + view*L)*0.01, nightPhase, lum,
                      dxy0, dxy1,
                      dayL1,dayL0, nightL1,nightL0);
  vec3 clear = skyColor + cloud.rgb * cloud.a;
  return weatherClouds(clear, skyColor, lum, (plPos + view*L)*0.01, dxy0, dxy1, dayL1, dayL0, overcast, snowy,
                       nightPhase);
  // return mix(skyColor, cloud.rgb, cloud.a);
  }

vec3 applyClouds(vec3 skyColor, in sampler2D skyLUT, vec3 plPos, vec3 sunDir, vec3 view, float nightPhase,
                 vec2 dxy0, vec2 dxy1,
                 in sampler2D dayL1,   in sampler2D dayL0,
                 in sampler2D nightL1, in sampler2D nightL0) {
  return applyClouds(skyColor, skyLUT, plPos, sunDir, view, nightPhase, dxy0, dxy1, dayL1, dayL0, nightL1, nightL0,
                     0.0, 0.0);
  }

#endif
