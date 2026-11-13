#include "worldview.h"
#include "world/objects/npc.h"
#include <Tempest/Pixmap>
#include <cmath>
#include <algorithm>
#include <cstring>
#include "game/globaleffects.h"
#include "world/world.h"
#include "gothic.h"

#include <Tempest/Application>

#include "graphics/mesh/submesh/packedmesh.h"
#include "game/gametime.h"
#include "camera.h"
#include "shaders.h"

using namespace Tempest;

WorldView::WorldView(const PackedMesh& wmesh, std::string_view skyPreset)
    : aabb(wmesh.bbox()), gSky(skyPreset), gLights(sGlobal), visuals(sGlobal,wmesh.bbox()),
    objGroup(visuals), pfxGroup(*this,sGlobal,visuals), land(visuals,wmesh) {
  pfxGroup.resetTicks();
  buildWeatherHeight(wmesh);
  sGlobal.setWeatherRoof(weatherHeightMap, weatherHeightBox);
  snowTrail.init();
  }

WorldView::~WorldView() {
  // cmd buffers must not be in use
  Resources::device().waitIdle();
  }

const LightSource& WorldView::mainLight() const {
  return gSky.sunLight();
  }

const Tempest::Vec3& WorldView::ambientLight() const {
  return gSky.ambientLight();
  }

std::pair<Vec3, Vec3> WorldView::bbox() const {
  return aabb;
  }

bool WorldView::isInPfxRange(const Vec3& pos) const {
  return pfxGroup.isInPfxRange(pos);
  }

void WorldView::preFrameUpdate(const Camera& camera, uint64_t tickCount, uint8_t fId) {
  const auto ldir = gSky.sunLight().dir();
  Tempest::Matrix4x4 shadow   [Resources::ShadowLayers];
  Tempest::Matrix4x4 shadowLwc[Resources::ShadowLayers];
  for(size_t i=0; i<Resources::ShadowLayers; ++i) {
    shadow   [i] = camera.viewShadow(ldir,i);
    shadowLwc[i] = camera.viewShadowLwc(ldir,i);
    }

  sGlobal.setViewProject(camera.view(),camera.projective(),camera.zNear(),camera.zFar(),shadow);
  sGlobal.setViewLwc(camera.viewLwc(),camera.projective(),shadowLwc);
  sGlobal.setViewVsm(camera.viewShadowVsm(ldir), camera.viewShadowVsmLwc(ldir));
  sGlobal.originLwc = camera.originLwc();
  sGlobal.setUnderWater(camera.isInWater());
  sGlobal.setSky(gSky);
  sGlobal.setWorld(*this);

  pfxGroup.setViewerPos(camera.originLwc());
  pfxGroup.tick(tickCount);
  gLights.tick(tickCount);
  sGlobal.setTime(tickCount);
  if(auto* world = Gothic::inst().world()) {
    auto& w = world->globalFx()->weatherState();
    sGlobal.setWeatherCover(w.cover, w.wet);
    if(auto* pl = Gothic::inst().player()) {
      const float snowfall = w.kind==GlobalEffects::Precipitation::Snow ? w.intensity : 0.f;
      const bool grounded = !pl->isInAir() && !pl->isJump() && !pl->isSwim();
      snowTrail.tick(pl->position(), grounded, w.cover, snowfall, tickCount, fId);
      }
    }
  sGlobal.setWeatherTrail(snowTrail.buffer(fId), snowTrail.box(), snowTrail.baseY());
  sGlobal.commitUbo(fId);

  pfxGroup.preFrameUpdate(fId);
  visuals .preFrameUpdate();
  }

void WorldView::prepareGlobals(Tempest::Encoder<Tempest::CommandBuffer>& cmd, uint8_t fId) {
  sGlobal.prepareGlobals(cmd, fId);
  gLights.prepareGlobals(cmd, fId);
  visuals.prepareGlobals(cmd, fId);
  }

void WorldView::setGbuffer(const Texture2d& diffuse, const Texture2d& norm) {
  sGlobal.gbufDiffuse = &diffuse;
  sGlobal.gbufNormals = &norm;
  sGlobal.setResolution(uint32_t(diffuse.w()),uint32_t(diffuse.h()));
  }

void WorldView::setShadowMaps(const Tempest::Texture2d* sh[]) {
  const Texture2d* shadow[Resources::ShadowLayers] = {};
  for(size_t i=0; i<Resources::ShadowLayers; ++i)
    if(sh[i]==nullptr || sh[i]->isEmpty())
      shadow[i] = &Resources::fallbackBlack(); else
      shadow[i] = sh[i];
  sGlobal.setShadowMap(shadow);
  }

void WorldView::setVirtualShadowMap(bool enabled,
                                    const Tempest::ZBuffer&       pageData,
                                    const Tempest::StorageImage&  pageTbl,
                                    const Tempest::StorageImage&  pageHiZ,
                                    const Tempest::StorageBuffer& pageList)  {
  sGlobal.setVirtualShadowMap(enabled, pageData, pageTbl, pageHiZ, pageList);
  }

void WorldView::setHiZ(const Tempest::Texture2d& hiZ) {
  sGlobal.setHiZ(hiZ);
  }

void WorldView::setSceneImages(const Tempest::Texture2d& clr, const Tempest::Texture2d& depthAux, const Tempest::ZBuffer& depthNative) {
  sGlobal.sceneColor = &clr;
  sGlobal.sceneDepth = &depthAux;
  sGlobal.zbuffer    = &textureCast<const Texture2d&>(depthNative);
  }

void WorldView::setWindEnabled(bool enabled, uint64_t period) {
  sGlobal.zWindEnabled = enabled && period>0;
  sGlobal.windPeriod   = period;
  }

void WorldView::dbgLights(DbgPainter& p) const {
  gLights.dbgLights(p);
  }

void WorldView::updateFrustrum(const Frustrum fr[]) {
  for(uint8_t i=0; i<SceneGlobals::V_Count; ++i)
    sGlobal.frustrum[i] = fr[i];
  }

void WorldView::visibilityPass(Tempest::Encoder<Tempest::CommandBuffer>& cmd, int pass) {
  cmd.setDebugMarker("Visibility");
  visuals.visibilityPass(cmd, pass);
  }

void WorldView::visibilityVsm(Tempest::Encoder<Tempest::CommandBuffer>& cmd) {
  visuals.visibilityVsm(cmd);
  }

void WorldView::drawHiZ(Tempest::Encoder<Tempest::CommandBuffer>& cmd) {
  visuals.drawHiZ(cmd);
  }

void WorldView::drawShadow(Tempest::Encoder<CommandBuffer>& cmd, uint8_t fId, uint8_t layer) {
  visuals.drawShadow(cmd,layer);
  pfxGroup.drawShadow(cmd,fId,layer);
  }

void WorldView::drawVsm(Tempest::Encoder<Tempest::CommandBuffer>& cmd) {
  visuals.drawVsm(cmd);
  }

void WorldView::drawGBuffer(Tempest::Encoder<CommandBuffer>& cmd, uint8_t fId) {
  visuals.drawGBuffer(cmd);
  pfxGroup.drawGBuffer(cmd, fId);
  }

void WorldView::drawWater(Tempest::Encoder<Tempest::CommandBuffer>& cmd) {
  visuals.drawWater(cmd);
  }

void WorldView::drawTranslucent(Tempest::Encoder<CommandBuffer>& cmd, uint8_t fId) {
  visuals.drawTranslucent(cmd);
  pfxGroup.drawTranslucent(cmd, fId);
  }

MeshObjects::Mesh WorldView::addView(std::string_view visual, int32_t headTex, int32_t teethTex, int32_t bodyColor) {
  if(auto mesh=Resources::loadMesh(visual))
    return MeshObjects::Mesh(objGroup,*mesh,headTex,teethTex,bodyColor,false);
  return MeshObjects::Mesh();
  }

MeshObjects::Mesh WorldView::addView(const ProtoMesh* mesh) {
  if(mesh!=nullptr) {
    bool staticDraw = false;
    return MeshObjects::Mesh(objGroup,*mesh,0,0,0,staticDraw);
    }
  return MeshObjects::Mesh();
  }

MeshObjects::Mesh WorldView::addItmView(std::string_view visual, int32_t material) {
  if(auto mesh=Resources::loadMesh(visual))
    return MeshObjects::Mesh(objGroup,*mesh,material,0,0,true);
  return MeshObjects::Mesh();
  }

MeshObjects::Mesh WorldView::addAtachView(const ProtoMesh::Attach& visual, const int32_t version) {
  return MeshObjects::Mesh(objGroup,visual,version,false);
  }

MeshObjects::Mesh WorldView::addStaticView(const ProtoMesh* mesh, bool staticDraw) {
  if(mesh!=nullptr)
    return MeshObjects::Mesh(objGroup,*mesh,0,0,0,staticDraw);
  return MeshObjects::Mesh();
  }

MeshObjects::Mesh WorldView::addStaticView(std::string_view visual) {
  if(auto mesh=Resources::loadMesh(visual))
    return MeshObjects::Mesh(objGroup,*mesh,0,0,0,true);
  return MeshObjects::Mesh();
  }

MeshObjects::Mesh WorldView::addDecalView(const zenkit::VisualDecal& vob) {
  if(auto mesh=Resources::decalMesh(vob))
    return MeshObjects::Mesh(objGroup,*mesh,0,0,0,true);
  return MeshObjects::Mesh();
  }

LightGroup::Light WorldView::addLight(const zenkit::VLight& vob, const uint64_t timeOffset) {
  auto l = gLights.add(vob);
  l.setTimeOffset(timeOffset);
  return l;
  }

LightGroup::Light WorldView::addLight(std::string_view preset, const uint64_t timeOffset) {
  auto l = gLights.add(preset);
  l.setTimeOffset(timeOffset);
  return l;
  }

void WorldView::dbgClusters(Tempest::Painter& p, Vec2 wsz) {
  visuals.dbgClusters(p, wsz);
  }

const DrawClusters& WorldView::clusters() const {
  return visuals.clusters();
  }

const DrawCommands& WorldView::drawCommands() const {
  return visuals.drawCommands();
  }

const DrawBuckets& WorldView::drawBuckets() const {
  return visuals.drawBuckets();
  }

const Tempest::StorageBuffer& WorldView::instanceSsbo() const {
  return visuals.instanceSsbo();
  }

bool WorldView::updateLights(const gtime gameTime) {
  gSky.updateLight(gameTime);
  if(!gLights.updateLights())
    return false;
  sGlobal.lights = &gLights.lightsSsbo();
  return true;
  }

bool WorldView::updateRtScene() {
  if(!Shaders::options().doRtScene)
    return false;
  if(!visuals.updateRtScene(sGlobal.rtScene))
    return false;
  return true;
  }

void WorldView::postFrameupdate() {
  visuals.postFrameupdate();
  }

void WorldView::buildWeatherHeight(const PackedMesh& wmesh) {
  // One float per cell: the highest static surface's height, rasterised from above once per world. Water does not
  // shelter anything. Cells are a metre wide, coarser for a very large world.
  auto [lo, hi] = wmesh.bbox();
  const float width = std::max(hi.x-lo.x, 1.f), depth = std::max(hi.z-lo.z, 1.f);
  const float cell  = std::max(100.f, std::max(width, depth)/2048.f);
  const int   w     = std::max(1, int(std::ceil(width/cell)));
  const int   h     = std::max(1, int(std::ceil(depth/cell)));
  std::vector<float> top(size_t(w*h), -1.0e9f);

  for(auto& sub:wmesh.subMeshes) {
    if(sub.material.group==zenkit::MaterialGroup::WATER)
      continue;
    for(size_t i=sub.iboOffset; i+2<sub.iboOffset+sub.iboLength && i+2<wmesh.indices.size(); i+=3) {
      const auto& a = wmesh.vertices[wmesh.indices[i+0]].pos;
      const auto& b = wmesh.vertices[wmesh.indices[i+1]].pos;
      const auto& c = wmesh.vertices[wmesh.indices[i+2]].pos;
      const float area = (b[0]-a[0])*(c[2]-a[2]) - (c[0]-a[0])*(b[2]-a[2]);
      if(std::abs(area)<1e-3f)
        continue;   // degenerate, or a wall seen edge-on from above
      const int x0 = std::clamp(int((std::min({a[0],b[0],c[0]})-lo.x)/cell), 0, w-1);
      const int x1 = std::clamp(int((std::max({a[0],b[0],c[0]})-lo.x)/cell), 0, w-1);
      const int z0 = std::clamp(int((std::min({a[2],b[2],c[2]})-lo.z)/cell), 0, h-1);
      const int z1 = std::clamp(int((std::max({a[2],b[2],c[2]})-lo.z)/cell), 0, h-1);
      for(int z=z0; z<=z1; ++z)
        for(int x=x0; x<=x1; ++x) {
          const float px = lo.x + (float(x)+0.5f)*cell, pz = lo.z + (float(z)+0.5f)*cell;
          const float u  = ((b[0]-px)*(c[2]-pz) - (c[0]-px)*(b[2]-pz))/area;
          const float v  = ((c[0]-px)*(a[2]-pz) - (a[0]-px)*(c[2]-pz))/area;
          const float t  = 1.f-u-v;
          if(u<-0.01f || v<-0.01f || t<-0.01f)
            continue;
          const float y = u*a[1] + v*b[1] + t*c[1];
          auto& dst = top[size_t(z*w+x)];
          dst = std::max(dst, y);
          }
      }
    }

  // Cells nothing was drawn into take a neighbour's height, so a filtered sample never blends a roof with "nothing"
  // (which would read as far below ground and switch shelter off at its edge); what stays empty sits at the floor.
  const float empty = -1.0e9f;
  for(int pass=0; pass<8; ++pass) {
    bool changed = false;
    std::vector<float> next = top;
    for(int z=0; z<h; ++z)
      for(int x=0; x<w; ++x) {
        if(top[size_t(z*w+x)]>empty)
          continue;
        float best = empty;
        if(x>0)   best = std::max(best, top[size_t(z*w+x-1)]);
        if(x<w-1) best = std::max(best, top[size_t(z*w+x+1)]);
        if(z>0)   best = std::max(best, top[size_t((z-1)*w+x)]);
        if(z<h-1) best = std::max(best, top[size_t((z+1)*w+x)]);
        if(best>empty) {
          next[size_t(z*w+x)] = best;
          changed = true;
          }
        }
    top = std::move(next);
    if(!changed)
      break;
    }
  for(auto& v:top)
    if(v<=empty)
      v = lo.y;

  Tempest::Pixmap pm(uint32_t(w), uint32_t(h), Tempest::TextureFormat::R32F);
  std::memcpy(pm.data(), top.data(), top.size()*sizeof(float));
  weatherHeightMap = Resources::device().texture(pm, false);
  weatherHeightBox = Tempest::Vec4(lo.x, lo.z, 1.f/(float(w)*cell), 1.f/(float(h)*cell));
  }
