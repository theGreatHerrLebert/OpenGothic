#include "resources.h"

#include <fstream>
#include <filesystem>

#include <Tempest/MemReader>
#include <Tempest/Pixmap>
#include <Tempest/Device>
#include <Tempest/Dir>
#include <Tempest/Application>
#include <Tempest/Sound>
#include <Tempest/SoundEffect>
#include <Tempest/TextCodec>
#include <Tempest/Log>
#include <Tempest/Color>

#include <zenkit/MultiResolutionMesh.hh>
#include <zenkit/ModelHierarchy.hh>
#include <zenkit/Model.hh>
#include <zenkit/ModelScript.hh>
#include <zenkit/Material.hh>
#include <zenkit/Texture.hh>
#include <zenkit/addon/texcvt.hh>
#include <zenkit/Texture.hh>

#include "graphics/mesh/submesh/pfxemittermesh.h"
#include "graphics/mesh/submesh/packedmesh.h"
#include "graphics/mesh/skeleton.h"
#include "graphics/mesh/protomesh.h"
#include "graphics/mesh/objmesh.h"
#include "graphics/mesh/animation.h"
#include "graphics/mesh/attachbinder.h"
#include "graphics/material.h"
#include "dmusic/directmusic.h"
#include "utils/fileext.h"
#include "utils/gthfont.h"

#include "gothic.h"
#include "utils/string_frm.h"

#include <dmusic.h>

using namespace Tempest;

Resources* Resources::inst=nullptr;

static void emplaceTag(char* buf, char tag){
  for(size_t i=1;buf[i];++i){
    if(buf[i]==tag && buf[i-1]=='_' && buf[i+1]=='0'){
      buf[i  ]='%';
      buf[i+1]='s';
      ++i;
      return;
      }
    }
  }

static std::string upperName(std::string_view s);

Resources::Resources(Tempest::Device &device)
  : dev(device) {
  inst=this;

  static const uint16_t index[] = {
      0, 1, 2, 0, 2, 3,
      4, 6, 5, 4, 7, 6,
      1, 5, 2, 2, 5, 6,
      4, 0, 7, 7, 0, 3,
      3, 2, 7, 7, 2, 6,
      4, 5, 0, 0, 5, 1
    };
  cube = device.ibo(index, sizeof(index)/sizeof(index[0]));

  dxMusic.reset(new Dx8::DirectMusic());
  // G2
  dxMusic->addPath(Gothic::nestedPath({u"_work",u"Data",u"Music",u"newworld"},  Dir::FT_Dir));
  dxMusic->addPath(Gothic::nestedPath({u"_work",u"Data",u"Music",u"AddonWorld"},Dir::FT_Dir));
  // G1
  dxMusic->addPath(Gothic::nestedPath({u"_work",u"Data",u"Music",u"dungeon"},  Dir::FT_Dir));
  dxMusic->addPath(Gothic::nestedPath({u"_work",u"Data",u"Music",u"menu_men"}, Dir::FT_Dir));
  dxMusic->addPath(Gothic::nestedPath({u"_work",u"Data",u"Music",u"orchestra"},Dir::FT_Dir));
  // switch-build
  dxMusic->addPath(Gothic::nestedPath({u"_work",u"Data",u"Music"},Dir::FT_Dir));

  fBuff .reserve(8*1024*1024);
  ddsBuf.reserve(8*1024*1024);

  {
  Pixmap pm(1,1,TextureFormat::RGBA8);
  uint8_t* pix = reinterpret_cast<uint8_t*>(pm.data());
  pix[0]=255;
  pix[3]=255;
  fallback = device.texture(pm);
  }

  {
  Pixmap pm(1,1,TextureFormat::RGBA8);
  fbZero = device.texture(pm);
  }

  fbImg = device.image2d(TextureFormat::R32U,1,1);

  // Set up the DirectMusic loader
  DmResult rv = DmLoader_create(&dmLoader, DmLoader_DOWNLOAD);
  if(rv != DmResult_SUCCESS) {
    Log::e("Failed to created DmLoader object. Out of memory?");
    }

  DmLoader_addResolver(dmLoader, [](void* ctx, char const* name, size_t* len) -> void* {
      auto* slf = reinterpret_cast<Resources*>(ctx);
      auto* node = slf->gothicAssets.find(name);

      if (node == nullptr) {
        return nullptr;
      }

      auto reader = node->open_read();

      reader->seek(0, zenkit::Whence::END);
      *len = reader->tell();

      reader->seek(0, zenkit::Whence::BEG);
      auto* bytes = static_cast<uint8_t *>(malloc(*len));
      reader->read(bytes, *len);

      return bytes;
      }, this);
  }

void Resources::mountVdfs(const std::vector<std::u16string>& vdfs) {
  std::vector<Archive> archives;
  for(auto& file:vdfs) {
    Archive ar;
    ar.name  = file;
    ar.time  = vdfTimestamp(ar.name);
    ar.ord   = uint16_t(archives.size());
    ar.isMod = FileExt::hasExt(file, u"mod");

    if(std::filesystem::file_size(ar.name)>0)
      archives.emplace_back(std::move(ar));
    }

  // addon archives first!
  std::stable_sort(archives.begin(),archives.end(),[](const Archive& a,const Archive& b){
    int aIsMod = a.isMod ? 1 : -1;
    int bIsMod = b.isMod ? 1 : -1;
    return std::make_tuple(aIsMod,a.time,int(a.ord)) >
           std::make_tuple(bIsMod,b.time,int(b.ord));
    });

  for(auto& i:archives) {
    try {
#ifdef __IOS__
      // causes OOM on iPhone7
      if(i.name.find(u"Speech")!=std::string::npos)
        continue;
#endif
      inst->gothicAssets.mount_disk(i.name, zenkit::VfsOverwriteBehavior::OLDER);
      }
    catch(const zenkit::VfsBrokenDiskError& err) {
      Log::e("unable to load archive: \"", TextCodec::toUtf8(i.name), "\", reason: ", err.what());
      }
    catch(const std::exception& err) {
      Log::e("unable to load archive: \"", TextCodec::toUtf8(i.name), "\", reason: ", err.what());
      }
    }
  }

void Resources::mountWork(const std::filesystem::path& path) {
  inst->gothicAssets.mkdir("/_work");
  inst->gothicAssets.mount_host(path, "/_work", zenkit::VfsOverwriteBehavior::NONE);
  }

void Resources::unloadAll() {
  device().waitIdle();

  std::lock_guard<std::recursive_mutex> g(inst->sync);
  inst->gothicAssets = zenkit::Vfs();
  inst->texCache.clear();
  inst->pixCache.clear();
  inst->aniMeshCache.clear();
  inst->decalMeshCache.clear();
  inst->skeletonCache.clear();
  inst->animCache.clear();
  inst->bindCache.clear();
  inst->emiMeshCache.clear();
  inst->zenCache.clear();

  std::lock_guard<std::recursive_mutex> gf(inst->syncFont);
  inst->gothicFnt.clear();
  }

Resources::~Resources() {
  DmLoader_release(dmLoader);
  inst=nullptr;
  }

bool Resources::hasFile(std::string_view name) {
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  return inst->gothicAssets.find(name) != nullptr;
  }

bool Resources::getFileData(std::string_view name, std::vector<uint8_t> &dat) {
  dat.clear();

  const auto* entry = Resources::vdfsIndex().find(name);
  if(entry==nullptr)
    return false;

  // TODO: This should return a buffer!
  auto reader = entry->open_read();

  reader->seek(0, zenkit::Whence::END);
  dat.resize(reader->tell());
  reader->seek(0, zenkit::Whence::BEG);
  reader->read(dat.data(), dat.size());

  return true;
  }

std::vector<uint8_t> Resources::getFileData(std::string_view name) {
  std::vector<uint8_t> data;
  getFileData(name,data);
  return data;
  }

std::unique_ptr<zenkit::Read> Resources::getFileBuffer(std::string_view name) {
  const auto* entry = Resources::vdfsIndex().find(name);
  if (entry == nullptr)
    throw std::runtime_error("failed to open resource: " + std::string{name});
  return entry->open_read();
  }

std::unique_ptr<zenkit::ReadArchive> Resources::openReader(std::string_view name, std::unique_ptr<zenkit::Read>& read) {
  const auto* entry = Resources::vdfsIndex().find(name);
  if(entry == nullptr)
    throw std::runtime_error("failed to open resource: " + std::string{name});
  auto buf = entry->open_read();
  if(buf == nullptr)
    throw std::runtime_error("failed to open resource: " + std::string{name});
  auto zen = zenkit::ReadArchive::from(buf.get());
  if(zen == nullptr)
    throw std::runtime_error("failed to open resource: " + std::string{name});
  read = std::move(buf);
  return zen;
  }

const char* Resources::renderer() {
  return inst->dev.properties().name;
  }

static Sampler implShadowSampler() {
  Tempest::Sampler smp;
  smp.setFiltration(Tempest::Filter::Nearest);
  smp.setClamping(Tempest::ClampMode::ClampToEdge);
  smp.anisotropic = false;
  return smp;
  }

const Sampler& Resources::shadowSampler() {
  static Tempest::Sampler smp = implShadowSampler();
  return smp;
  }

void Resources::detectVdf(std::vector<Archive>& ret, const std::u16string &root) {
  Dir::scan(root,[this,&root,&ret](const std::u16string& vdf, Dir::FileType t){
    if(t==Dir::FT_File) {
      auto file = root + vdf;
      Archive ar;
      ar.name  = root+vdf;
      ar.time  = vdfTimestamp(ar.name);
      ar.ord   = uint16_t(ret.size());
      ar.isMod = vdf.rfind(u".mod")==vdf.size()-4;

      if(std::filesystem::file_size(ar.name)>0)
        ret.emplace_back(std::move(ar));
      return;
      }

    // switch uses NX extension for language dependant stuff
    if(vdf.find(u".NX.")!=std::string::npos)
      return;

    if(t==Dir::FT_Dir && vdf!=u".." && vdf!=u".") {
      auto dir = root + vdf + u"/";
      detectVdf(ret,dir);
      }
    });
  }

const GthFont& Resources::dialogFont(const float scale) {
  return font("font_old_10_white.tga",FontType::Normal,scale);
  }

const GthFont& Resources::font(const float scale) {
  return font("font_old_10_white.tga",FontType::Normal,scale);
  }

const GthFont& Resources::font(Resources::FontType type, const float scale) {
  return font("font_old_10_white.tga",type,scale);
  }

const GthFont& Resources::font(std::string_view fname, FontType type, const float scale) {
  if(fname.empty())
    return font(scale);
  return inst->implLoadFont(fname, type, scale);
  }

const Texture2d& Resources::fallbackTexture() {
  return inst->fallback;
  }

const Texture2d &Resources::fallbackBlack() {
  return inst->fbZero;
  }

const Tempest::StorageImage& Resources::fallbackImage() {
  return inst->fbImg;
  }

const zenkit::Vfs& Resources::vdfsIndex() {
  return inst->gothicAssets;
  }

const Tempest::IndexBuffer<uint16_t>& Resources::cubeIbo() {
  return inst->cube;
  }

int64_t Resources::vdfTimestamp(const std::u16string& name) {
  enum {
    VDF_COMMENT_LENGTH   = 256,
    VDF_SIGNATURE_LENGTH = 16,
    };
  uint32_t count=0, timestamp=0;
  char sign[VDF_SIGNATURE_LENGTH]={};

  try {
    RFile fin(name);
    fin.seek(VDF_COMMENT_LENGTH);
    fin.read(sign,VDF_SIGNATURE_LENGTH);
    fin.read(&count,sizeof(count));
    fin.seek(4);
    fin.read(&timestamp,sizeof(timestamp));

    return int64_t(timestamp);
    }
  catch(...) {
    return -1;
    }
  }

Tempest::Texture2d* Resources::implLoadTexture(std::string_view cname, bool forceMips) {
  if(cname.empty())
    return nullptr;

  //TODO: __cpp_lib_generic_unordered_lookup
  std::string name = std::string(cname);
  auto it=texCache.find(name);
  if(it!=texCache.end())
    return it->second.get();

  auto tex = implLoadTextureUncached(cname, forceMips);
  if(!tex.isEmpty()) {
    std::unique_ptr<Texture2d> t{new Texture2d(std::move(tex))};
    Texture2d* ret=t.get();
    texCache[std::move(name)] = std::move(t);
    return ret;
    }
  texCache[std::move(name)] = nullptr;
  return nullptr;
  }

Texture2d Resources::implLoadTextureUncached(std::string_view name, bool forceMips) {
  if(name.empty())
    return Texture2d();

  if(auto own = customTextures.find(upperName(name)); own!=customTextures.end()) {
    try {
      Pixmap pm(own->second);
      return dev.texture(pm, true);
      }
    catch(...) {
      Log::e("unable to load texture \"", own->second, "\"");
      return Texture2d();
      }
    }

  if(FileExt::hasExt(name,"TGA")) {
    auto nameAlt = std::string(name);
    nameAlt.resize(nameAlt.size() + 2);
    std::memcpy(&nameAlt[0]+nameAlt.size()-6, "-C.TEX", 6);

    if(const auto* entry = Resources::vdfsIndex().find(nameAlt)) {
      zenkit::Texture tex;

      auto reader = entry->open_read();
      tex.load(reader.get());

      if(tex.format() == zenkit::TextureFormat::DXT1 ||
         tex.format() == zenkit::TextureFormat::DXT2 ||
         tex.format() == zenkit::TextureFormat::DXT3 ||
         tex.format() == zenkit::TextureFormat::DXT4 ||
         tex.format() == zenkit::TextureFormat::DXT5) {
        auto dds = zenkit::to_dds(tex);
        auto ddsRead = zenkit::Read::from(dds);

        return implLoadTextureUncached(name, *ddsRead, forceMips);
        } else {
        auto rgba = tex.as_rgba8(0);

        try {
          Tempest::Pixmap    pm(tex.width(), tex.height(), TextureFormat::RGBA8);
          std::memcpy(pm.data(), rgba.data(), rgba.size());
          return dev.texture(pm);
          }
        catch (...) {
          }
        }
      }
    }

  if(auto* entry = Resources::vdfsIndex().find(name)) {
    auto reader = entry->open_read();
    return implLoadTextureUncached(name, *reader, forceMips);
    }
  return Texture2d();
  }

Texture2d Resources::implLoadTextureUncached(std::string_view name, zenkit::Read& data, bool forceMips) {
  try {
    std::vector<uint8_t> raw;
    data.seek(0, zenkit::Whence::END);
    raw.resize(data.tell());
    data.seek(0, zenkit::Whence::BEG);
    data.read(raw.data(), raw.size());

    Tempest::MemReader rd((uint8_t*)raw.data(), raw.size());
    Tempest::Pixmap    pm(rd);

    const bool useMipmap = forceMips || (pm.mipCount()>1); // do not generate mips, if original texture has has none
    return dev.texture(pm, useMipmap);
    }
  catch(...){
    return Texture2d();
    }
  }

ProtoMesh* Resources::implLoadMesh(std::string_view name) {
  if(name.size()==0)
    return nullptr;

  auto cname = std::string(name);
  auto it    = aniMeshCache.find(cname);
  if(it!=aniMeshCache.end())
    return it->second.get();

  auto  t   = implLoadMeshMain(cname);
  auto  ret = t.get();
  if(ret==nullptr && upperName(cname).rfind("DM_",0)==0)
    return nullptr;   // a story's own mesh not registered yet (a cold load): ask again once it is
  aniMeshCache[cname] = std::move(t);
  if(ret==nullptr)
    Log::e("unable to load mesh \"",cname,"\"");
  return ret;
  }

std::unique_ptr<ProtoMesh> Resources::implLoadMeshMain(std::string name) {
  if(auto f = meshFiles.find(upperName(name)); f!=meshFiles.end()) {
    // A story's own mesh, read from its OBJ file when registered.
    PackedMesh packed(*f->second.mesh,PackedMesh::PK_Visual);
    return std::unique_ptr<ProtoMesh>{new ProtoMesh(std::move(packed),name)};
    }

  if(auto v = meshVariants.find(upperName(name)); v!=meshVariants.end()) {
    // A game mesh with some of its textures swapped for a story's own.
    std::string base = v->second.base;
    FileExt::exchangeExt(base,"3DS","MRM");
    const auto* entry = Resources::vdfsIndex().find(base);
    if(entry==nullptr)
      return nullptr;
    zenkit::MultiResolutionMesh zmsh;
    auto reader = entry->open_read();
    zmsh.load(reader.get());
    if(zmsh.sub_meshes.empty())
      return nullptr;
    for(auto& sub:zmsh.sub_meshes)
      if(auto t = v->second.textures.find(upperName(sub.mat.texture)); t!=v->second.textures.end())
        sub.mat.texture = t->second;
    PackedMesh packed(zmsh,PackedMesh::PK_Visual);
    return std::unique_ptr<ProtoMesh>{new ProtoMesh(std::move(packed),name)};
    }

  if(FileExt::hasExt(name,"3DS")) {
    FileExt::exchangeExt(name,"3DS","MRM");

    const auto* entry = Resources::vdfsIndex().find(name);
    if(entry == nullptr)
      return nullptr;

    zenkit::MultiResolutionMesh zmsh;

    auto reader = entry->open_read();
    zmsh.load(reader.get());

    if(zmsh.sub_meshes.empty())
      return nullptr;

    PackedMesh packed(zmsh,PackedMesh::PK_Visual);
    return std::unique_ptr<ProtoMesh>{new ProtoMesh(std::move(packed),name)};
    }

  if(FileExt::hasExt(name,"MMS") || FileExt::hasExt(name,"MMB")) {
    FileExt::exchangeExt(name,"MMS","MMB");

    const auto* entry = Resources::vdfsIndex().find(name);
    if(entry == nullptr)
      throw std::runtime_error("failed to open resource: " + name);

    zenkit::MorphMesh zmm;
    auto reader = entry->open_read();
    zmm.load(reader.get());

    if(zmm.mesh.sub_meshes.empty())
      return nullptr;

    PackedMesh packed(zmm.mesh,PackedMesh::PK_VisualMorph);
    return std::unique_ptr<ProtoMesh>{new ProtoMesh(std::move(packed),zmm.animations,name)};
    }

  if(FileExt::hasExt(name,"MDS")) {
    auto anim = Resources::loadAnimation(name);
    if(anim==nullptr)
      return nullptr;

    auto mesh   = std::string(anim->defaultMesh());

    FileExt::exchangeExt(mesh,nullptr,"MDM") ||
    FileExt::exchangeExt(mesh,"ASC",  "MDM");

    auto mdhName = std::string(anim->defaultMesh());
    if(mdhName.empty())
      mdhName = name;
    FileExt::assignExt(mdhName,"MDH");

    if(const auto* entryMdh = Resources::vdfsIndex().find(mdhName)) {
      // Find a MDH hirarchy file and separate mesh
      zenkit::ModelHierarchy mdh;
      auto reader = entryMdh->open_read();
      mdh.load(reader.get());

      std::unique_ptr<Skeleton> sk{new Skeleton(mdh,anim,name)};
      std::unique_ptr<ProtoMesh> t;

      if(const auto* entry = Resources::vdfsIndex().find(mesh)) {
        auto reader = entry->open_read();

        zenkit::ModelMesh mdm {};
        mdm.load(reader.get());
        t.reset(new ProtoMesh(mdm,std::move(sk),name));
        }
      else
        t.reset(new ProtoMesh(mdh,std::move(sk),name));

      return t;
      }

    // MDL files contain both the hirarchy and mesh, try to find one as a fallback
    FileExt::exchangeExt(mdhName,"MDH","MDL");
    if(const auto* entryMdl = Resources::vdfsIndex().find(mdhName)) {
      if(entryMdl==nullptr)
        throw std::runtime_error("failed to open resource: " + mdhName);

      zenkit::Model mdm;
      auto reader = entryMdl->open_read();
      mdm.load(reader.get());

      std::unique_ptr<Skeleton> sk{new Skeleton(mdm.hierarchy,anim,name)};
      std::unique_ptr<ProtoMesh> t{new ProtoMesh(mdm,std::move(sk),name)};
      return t;
      }
    }

  if(FileExt::hasExt(name,"MDM") || FileExt::hasExt(name,"ASC")) {
    FileExt::exchangeExt(name,"ASC","MDM");

    if(!hasFile(name))
      return nullptr;

    const auto* entry = Resources::vdfsIndex().find(name);
    if(entry == nullptr)
      return nullptr;

    zenkit::ModelMesh mdm;
    auto reader = entry->open_read();
    mdm.load(reader.get());

    std::unique_ptr<ProtoMesh> t{new ProtoMesh(std::move(mdm),nullptr,name)};
    return t;
    }

  if(FileExt::hasExt(name,"MDL")) {
    if(!hasFile(name))
      return nullptr;

    const auto* entry = Resources::vdfsIndex().find(name);
    if(entry == nullptr)
      throw std::runtime_error("failed to open resource: " + name);
    zenkit::Model mdm;
    auto reader = entry->open_read();
    mdm.load(reader.get());

    std::unique_ptr<Skeleton> sk{new Skeleton(mdm.hierarchy,nullptr,name)};
    std::unique_ptr<ProtoMesh> t{new ProtoMesh(mdm,std::move(sk),name)};
    return t;
    }

  if(FileExt::hasExt(name,"TGA")) {
    Log::e("decals should be loaded by Resources::implDecalMesh instead");
    }

  return nullptr;
  }

PfxEmitterMesh* Resources::implLoadEmiterMesh(std::string_view name) {
  // TODO: reuse code from Resources::implLoadMeshMain
  auto cname = std::string(name);
  auto it    = emiMeshCache.find(cname);
  if(it!=emiMeshCache.end())
    return it->second.get();

  auto& ret = emiMeshCache[cname];

  if(FileExt::hasExt(cname,"3DS")) {
    FileExt::exchangeExt(cname,"3DS","MRM");

    const auto* entry = Resources::vdfsIndex().find(cname);
    if (entry == nullptr) return nullptr;
    zenkit::MultiResolutionMesh zmsh;
    auto reader = entry->open_read();
    zmsh.load(reader.get());

    if(zmsh.sub_meshes.empty())
      return nullptr;

    PackedMesh packed(zmsh,PackedMesh::PK_Visual);
    ret = std::unique_ptr<PfxEmitterMesh>(new PfxEmitterMesh(packed));
    return ret.get();
    }

  if(FileExt::hasExt(name,"MDM")) {
    if(!hasFile(name))
      return nullptr;

    const auto* entry = Resources::vdfsIndex().find(cname);
    if(entry == nullptr)
      throw std::runtime_error("failed to open resource: " + cname);
    zenkit::ModelMesh mdm;
    auto reader = entry->open_read();
    mdm.load(reader.get());

    ret = std::unique_ptr<PfxEmitterMesh>(new PfxEmitterMesh(std::move(mdm)));
    return ret.get();
    }

  return nullptr;
  }

ProtoMesh* Resources::implDecalMesh(const zenkit::VisualDecal& decal) {
  DecalK key;
  key.mat         = Material(decal);
  key.sX          = decal.dimension.x;
  key.sY          = decal.dimension.y;
  key.decal2Sided = decal.two_sided;

  if(key.mat.tex==nullptr)
    return nullptr;

  auto it = decalMeshCache.find(key);
  if(it!=decalMeshCache.end())
    return it->second.get();

  Resources::Vertex vbo[8] = {
    {{-1.f, -1.f, 0.f},{0,0,-1},{0,1}, 0xFFFFFFFF},
    {{ 1.f, -1.f, 0.f},{0,0,-1},{1,1}, 0xFFFFFFFF},
    {{ 1.f,  1.f, 0.f},{0,0,-1},{1,0}, 0xFFFFFFFF},
    {{-1.f,  1.f, 0.f},{0,0,-1},{0,0}, 0xFFFFFFFF},

    {{-1.f, -1.f, 0.f},{0,0, 1},{0,1}, 0xFFFFFFFF},
    {{ 1.f, -1.f, 0.f},{0,0, 1},{1,1}, 0xFFFFFFFF},
    {{ 1.f,  1.f, 0.f},{0,0, 1},{1,0}, 0xFFFFFFFF},
    {{-1.f,  1.f, 0.f},{0,0, 1},{0,0}, 0xFFFFFFFF},
    };
  for(auto& i:vbo) {
    i.pos[0]*=key.sX;
    i.pos[1]*=key.sY;
    }

  std::vector<Resources::Vertex> cvbo(vbo,vbo+8);
  std::vector<uint32_t>          cibo;
  if(key.decal2Sided)
    cibo = { 0,1,2, 0,2,3, 4,6,5, 4,7,6 }; else
    cibo = { 0,1,2, 0,2,3 };

  std::unique_ptr<ProtoMesh> t{new ProtoMesh(key.mat, std::move(cvbo), std::move(cibo))};

  auto ret = t.get();
  decalMeshCache[key] = std::move(t);
  return ret;
  }

std::unique_ptr<Animation> Resources::implLoadAnimation(std::string name) {
  if(name.size()<4)
    return nullptr;

  if(Gothic::inst().version().game==2)
    FileExt::exchangeExt(name,"MDS","MSB");

  const auto* entry = Resources::vdfsIndex().find(name);
  if(entry == nullptr)
    return nullptr;

  if(FileExt::hasExt(name,"MSB") || FileExt::hasExt(name,"MDS")) {
    zenkit::ModelScript mds;
    auto reader = entry->open_read();
    mds.load(reader.get());
    return std::unique_ptr<Animation>{new Animation(mds,name.substr(0,name.size()-4),false)};
    }

  return nullptr;
  }

Dx8::PatternList Resources::implLoadDxMusic(std::string_view name) {
  auto u = Tempest::TextCodec::toUtf16(name);
  return dxMusic->load(u.c_str());
  }

DmSegment* Resources::implLoadMusicSegment(char const* name) {
  DmSegment* sgt = nullptr;
  DmResult rv = DmLoader_getSegment(dmLoader, name, &sgt);
  if(rv != DmResult_SUCCESS) {
    Log::e("Music segment not found: ", name);
    return nullptr;
    }
  return sgt;
  }

Tempest::Sound Resources::implLoadSoundBuffer(std::string_view name) {
  if(name.empty())
    return Tempest::Sound();

  if(!getFileData(name,fBuff))
    return Tempest::Sound();
  try {
    Tempest::MemReader rd(fBuff.data(),fBuff.size());
    return Tempest::Sound(rd);
    }
  catch(...) {
    auto cname = std::string (name);
    Log::e("unable to load sound \"",cname,"\"");
    return Tempest::Sound();
    }
  }

GthFont &Resources::implLoadFont(std::string_view name, FontType type, const float scale) {
  std::lock_guard<std::recursive_mutex> g(inst->syncFont);

  auto key   = FontK(std::string(name), type, scale);
  auto it    = gothicFnt.find(key);
  if(it!=gothicFnt.end())
    return *(*it).second;

  std::string_view file = name;
  for(size_t i=0; i<name.size();++i) {
    if(name[i]=='.') {
      file = name.substr(0, i);
      break;
      }
    }

  string_frm tex, fnt;
  switch(type) {
    case FontType::Normal:
    case FontType::Disabled:
    case FontType::Yellow:
    case FontType::Red:
      tex = string_frm(file,".tga");
      fnt = string_frm(file,".fnt");
      break;
    case FontType::Hi:
      tex = string_frm(file,"_hi.tga");
      fnt = string_frm(file,"_hi.fnt");
      break;
    }

  auto color = Tempest::Color(1.f);
  switch(type) {
    case FontType::Normal:
    case FontType::Hi:
      color = Tempest::Color(1.f);
      break;
    case FontType::Disabled:
      color = Tempest::Color(1.f,1.f,1.f,0.6f);
      break;
    case FontType::Yellow:
      color = Tempest::Color(1.f,1.f,0.1f,1.f);
      //color = Tempest::Color(0.81f,0.78f,0.01f,1.f);
      break;
    case FontType::Red:
      color = Tempest::Color(1.f,0.f,0.f,1.f);
      break;
    }

  const auto* entry = Resources::vdfsIndex().find(fnt);
  if(entry == nullptr) {
    Log::e("failed to open resource: ", fnt);
    // throw std::runtime_error("failed to open resource: " + std::string{fnt});
    auto ptr   = std::make_unique<GthFont>();
    GthFont* f = ptr.get();
    gothicFnt[key] = std::move(ptr);
    return *f;
    }

  auto ptr   = std::make_unique<GthFont>(*entry->open_read(),tex,color);
  GthFont* f = ptr.get();
  f->setScale(scale);
  gothicFnt[key] = std::move(ptr);
  return *f;
  }

Texture2d Resources::loadTextureUncached(std::string_view name, bool forceMips) {
  return inst->implLoadTextureUncached(name, forceMips);
  }

const Texture2d* Resources::loadTexture(std::string_view name, bool forceMips) {
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  return inst->implLoadTexture(name,forceMips);
  }

const Texture2d* Resources::loadTexture(Tempest::Color color) {
  if(color==Color())
    return nullptr;
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  auto& cache = inst->pixCache;
  auto it = cache.find(color);
  if(it!=cache.end())
    return it->second.get();

  uint8_t iv[4] = { uint8_t(255.f*color.r()), uint8_t(255.f*color.g()), uint8_t(255.f*color.b()), uint8_t(255.f*color.a()) };
  Pixmap p2(1,1,TextureFormat::RGBA8);
  std::memcpy(p2.data(),iv,4);

  auto t       = std::make_unique<Texture2d>(inst->dev.texture(p2));
  auto ret     = t.get();
  cache[color] = std::move(t);
  return ret;
  }

const Texture2d *Resources::loadTexture(std::string_view name, int32_t iv, int32_t ic) {
  if(name.size()>=128)
    return loadTexture(name);

  char v[16]={};
  char c[16]={};
  char buf1[128]={};
  char buf2[128]={};

  std::snprintf(v,sizeof(v),"V%d",iv);
  std::snprintf(c,sizeof(c),"C%d",ic);
  std::snprintf(buf1,sizeof(buf1),"%.*s",int(name.size()),name.data());

  emplaceTag(buf1,'V');
  std::snprintf(buf2,sizeof(buf2),buf1,v);

  emplaceTag(buf2,'C');
  std::snprintf(buf1,sizeof(buf1),buf2,c);

  return loadTexture(buf1);
  }

std::vector<const Texture2d*> Resources::loadTextureAnim(std::string_view name) {
  std::vector<const Texture2d*> ret;
  if(name.find("_A0")==std::string::npos &&
     name.find("_a0")==std::string::npos)
    return ret;

  for(int id=0; ; ++id) {
    size_t at = 0;
    char   buf[128]={};
    for(size_t i=0;i<name.size();++i) {
      if(i+2<name.size() && name[i]=='_' && (name[i+1]=='A' || name[i+1]=='a') && name[i+2]=='0'){
        at += size_t(std::snprintf(buf+at,sizeof(buf)-at,"_A%d",id));
        i+=2;
        } else {
        buf[at] = name[i];
        if('a'<=buf[at] && buf[at]<='z')
          buf[at] = char(buf[at]+'A'-'a');
        at++;
        }
      if(at>sizeof(buf))
        return ret;
      }
   auto t = loadTexture(buf);
    if(t==nullptr) {
      string_frm buf2(buf,".TGA");
      t = loadTexture(buf2);
      if(t==nullptr)
        return ret;
      }
    ret.push_back(t);
    }
  }

Texture2d Resources::loadTexturePm(const Pixmap &pm) {
  if(pm.isEmpty()) {
    Pixmap p2(1,1,TextureFormat::R8);
    std::memset(p2.data(),0,1);
    return inst->dev.texture(p2);
    }
  return inst->dev.texture(pm);
  }

Material Resources::loadMaterial(const zenkit::Material& src, bool enableAlphaTest) {
  return Material(src,enableAlphaTest);
  }

const ProtoMesh* Resources::loadMesh(std::string_view name) {
  if(name.size()==0)
    return nullptr;
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  return inst->implLoadMesh(name);
  }

const PfxEmitterMesh* Resources::loadEmiterMesh(std::string_view name) {
  if(name.empty())
    return nullptr;
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  return inst->implLoadEmiterMesh(name);
  }

const Skeleton* Resources::loadSkeleton(std::string_view name) {
  auto s = Resources::loadMesh(name);
  if(s==nullptr)
    return nullptr;
  return s->skeleton.get();
  }

const Animation* Resources::loadAnimation(std::string_view name) {
  auto cname = std::string(name);

  std::lock_guard<std::recursive_mutex> g(inst->sync);
  auto& cache = inst->animCache;
  auto it=cache.find(cname);
  if(it!=cache.end())
    return it->second.get();
  auto t       = inst->implLoadAnimation(cname);
  auto ret     = t.get();
  cache[cname] = std::move(t);
  return ret;
  }

Tempest::Sound Resources::loadSoundBuffer(std::string_view name) {
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  return inst->implLoadSoundBuffer(name);
  }

Dx8::PatternList Resources::loadDxMusic(std::string_view name) {
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  return inst->implLoadDxMusic(name);
  }

DmSegment* Resources::loadMusicSegment(char const* name) {
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  return inst->implLoadMusicSegment(name);
  }

const ProtoMesh* Resources::decalMesh(const zenkit::VisualDecal& decal) {
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  return inst->implDecalMesh(decal);
  }

const Resources::VobTree* Resources::loadVobBundle(std::string_view name) {
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  return inst->implLoadVobBundle(name);
  }

void Resources::resetRecycled(uint8_t fId) {
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  inst->recycledId = fId;
  inst->recycled[fId].ssbo.clear();
  inst->recycled[fId].img.clear();
  inst->recycled[fId].att.clear();
  inst->recycled[fId].zb.clear();
  inst->recycled[fId].tx.clear();
  inst->recycled[fId].arr.clear();
  inst->recycled[fId].rtas.clear();
  }

void Resources::recycle(Tempest::DescriptorArray &&arr) {
  if(arr.isEmpty())
    return;
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  inst->recycled[inst->recycledId].arr.emplace_back(std::move(arr));
  }

void Resources::recycle(Tempest::StorageBuffer&& ssbo) {
  if(ssbo.isEmpty())
    return;
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  inst->recycled[inst->recycledId].ssbo.emplace_back(std::move(ssbo));
  }

void Resources::recycle(Tempest::StorageImage&& img) {
  if(img.isEmpty())
    return;
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  inst->recycled[inst->recycledId].img.emplace_back(std::move(img));
  }

void Resources::recycle(Tempest::Attachment&& img) {
  if(img.isEmpty())
    return;
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  inst->recycled[inst->recycledId].att.emplace_back(std::move(img));
  }

void Resources::recycle(Tempest::ZBuffer&& img) {
  if(img.isEmpty())
    return;
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  inst->recycled[inst->recycledId].zb.emplace_back(std::move(img));
  }

void Resources::recycle(Tempest::Texture2d&& img) {
  if(img.isEmpty())
    return;
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  inst->recycled[inst->recycledId].tx.emplace_back(std::move(img));
  }

void Resources::recycle(Tempest::AccelerationStructure&& rtas) {
  if(rtas.isEmpty())
    return;
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  inst->recycled[inst->recycledId].rtas.emplace_back(std::move(rtas));
  }

const Resources::VobTree* Resources::implLoadVobBundle(std::string_view filename) {
  auto cname = std::string(filename);
  auto i     = zenCache.find(cname);
  if(i!=zenCache.end())
    return i->second.get();

  std::vector<std::shared_ptr<zenkit::VirtualObject>> bundle;
  try {
    const auto* entry = Resources::vdfsIndex().find(cname);
    if(entry == nullptr)
      throw std::runtime_error("failed to open resource: " + cname);

    zenkit::World wrld;

    auto reader = entry->open_read();
    wrld.load(reader.get(), Gothic::inst().version().game==1 ? zenkit::GameVersion::GOTHIC_1
                                                             : zenkit::GameVersion::GOTHIC_2);

    bundle = std::move(wrld.world_vobs);
    }
  catch(...) {
    Log::e("unable to load Zen-file: \"",cname,"\"");
    }

  auto ret = zenCache.insert(std::make_pair(filename,std::make_unique<VobTree>(std::move(bundle))));
  return ret.first->second.get();
  }

const AttachBinder *Resources::bindMesh(const ProtoMesh &anim, const Skeleton &s) {
  std::lock_guard<std::recursive_mutex> g(inst->sync);

  if(anim.submeshId.size()==0){
    static AttachBinder empty;
    return &empty;
    }
  BindK k = BindK(&s,&anim);

  auto it = inst->bindCache.find(k);
  if(it!=inst->bindCache.end())
    return it->second.get();

  std::unique_ptr<AttachBinder> ret(new AttachBinder(s,anim));
  auto p = ret.get();
  inst->bindCache[k] = std::move(ret);
  return p;
  }

Tempest::VertexBuffer<Resources::Vertex> Resources::sphere(int passCount, float R){
  std::vector<Resources::Vertex> r;
  r.reserve( size_t(4*pow(3, passCount+1)) );

  static const double pi = 3.141592654;

  Resources::Vertex v1 = {
    {1, 0, -0.5},
    {0,0,0},{0,0},0
    };
  Resources::Vertex v2 = {
    {float(cos(2*pi/3)), float(sin(2*pi/3)), -0.5},
    {0,0,0},{0,0},0
    };
  Resources::Vertex v3 = {
    {float(cos(2*pi/3)), -float(sin(2*pi/3)), -0.5},
    {0,0,0},{0,0},0
    };

  Resources::Vertex v4 = {
    {0, 0, 0.5},
    {0,0,0},{0,0},0
    };

  r.push_back(v1);
  r.push_back(v3);
  r.push_back(v2);

  r.push_back(v1);
  r.push_back(v2);
  r.push_back(v4);

  r.push_back(v2);
  r.push_back(v3);
  r.push_back(v4);

  r.push_back(v1);
  r.push_back(v4);
  r.push_back(v3);

  for(size_t i=0; i<r.size(); ++i){
    Resources::Vertex& v = r[i];
    float l = std::sqrt(v.pos[0]*v.pos[0] + v.pos[1]*v.pos[1] + v.pos[2]*v.pos[2]);

    v.pos[0] /= l;
    v.pos[1] /= l;
    v.pos[2] /= l;
    }

  for(int c=0; c<passCount; ++c){
    size_t maxI = r.size();
    for( size_t i=0; i<maxI; i+=3 ){
      Resources::Vertex x = {
        {
          0.5f*(r[i].pos[0]+r[i+1].pos[0]),
          0.5f*(r[i].pos[1]+r[i+1].pos[1]),
          0.5f*(r[i].pos[2]+r[i+1].pos[2])
        },
        {0,0,0},{0,0},0
      };
      Resources::Vertex y = {
        {
          0.5f*(r[i+2].pos[0]+r[i+1].pos[0]),
          0.5f*(r[i+2].pos[1]+r[i+1].pos[1]),
          0.5f*(r[i+2].pos[2]+r[i+1].pos[2])
        },
        {0,0,0},{0,0},0
      };
      Resources::Vertex z = {
        {
          0.5f*(r[i].pos[0]+r[i+2].pos[0]),
          0.5f*(r[i].pos[1]+r[i+2].pos[1]),
          0.5f*(r[i].pos[2]+r[i+2].pos[2])
        },
        {0,0,0},{0,0},0
      };

      r.push_back( r[i] );
      r.push_back( x );
      r.push_back( z );

      r.push_back( x );
      r.push_back( r[i+1] );
      r.push_back( y );

      r.push_back( y );
      r.push_back( r[i+2] );
      r.push_back( z );

      r[i]   = x;
      r[i+1] = y;
      r[i+2] = z;
      }

    for(size_t i=0; i<r.size(); ++i){
      Resources::Vertex & v = r[i];
      float l = std::sqrt(v.pos[0]*v.pos[0] + v.pos[1]*v.pos[1] + v.pos[2]*v.pos[2]);

      v.pos[0] /= l;
      v.pos[1] /= l;
      v.pos[2] /= l;
      }
    }

  for(size_t i=0; i<r.size(); ++i){
    Resources::Vertex & v = r[i];
    v.norm[0] = v.pos[0];
    v.norm[1] = v.pos[1];
    v.norm[2] = v.pos[2];

    v.pos[0] *= R;
    v.pos[1] *= R;
    v.pos[2] *= R;
    }

  return dev.vbo(r);
  }

static std::string upperName(std::string_view s) {
  std::string r(s);
  for(auto& c:r)
    c = char(std::toupper(static_cast<unsigned char>(c)));
  return r;
  }

void Resources::registerTexture(std::string_view name, std::string_view path) {
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  inst->customTextures[upperName(name)] = std::string(path);
  // A lookup before registration (a creature drawn during a load) cached a miss: forget the miss, so the next lookup
  // finds the story's texture. A texture that loaded stays: meshes on screen draw with it, and freeing it under them
  // ends the frame (stories register their items' textures again after every load).
  for(const std::string& key:{upperName(name), std::string(name)})
    if(auto it = inst->texCache.find(key); it!=inst->texCache.end() && it->second==nullptr)
      inst->texCache.erase(it);
  }

bool Resources::registerMeshVariant(std::string_view alias, std::string_view base,
                                    const std::map<std::string,std::string>& textures) {
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  std::string mrm(base);
  FileExt::exchangeExt(mrm,"3DS","MRM");
  if(Resources::vdfsIndex().find(mrm)==nullptr)
    return false;
  MeshVariant v;
  v.base = std::string(base);
  for(auto& [from,to]:textures)
    v.textures[upperName(from)] = to;
  if(auto prev = inst->meshVariants.find(upperName(alias));
     prev!=inst->meshVariants.end() && prev->second.base==v.base && prev->second.textures==v.textures)
    return true;   // the same again (a story defining its items after a load): the mesh in use stays
  inst->meshVariants[upperName(alias)] = std::move(v);
  inst->aniMeshCache.erase(std::string(alias));
  return true;
  }

bool Resources::registerMeshFile(std::string_view alias, std::string_view objPath, std::string_view texture,
                                 float scale) {
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  const std::string key = upperName(alias);
  if(auto prev = inst->meshFiles.find(key); prev!=inst->meshFiles.end() && prev->second.path==objPath &&
     prev->second.texture==texture && prev->second.scale==scale)
    return true;   // the same again: the mesh in use stays

  if(!(scale>0.f)) {
    Log::e("unable to load mesh file \"", objPath, "\": scale must be above zero");
    return false;
    }
  auto mesh = std::make_shared<zenkit::MultiResolutionMesh>();
  std::vector<ObjMesh::SubInfo> info;
  std::string err;
  if(!ObjMesh::load(std::string(objPath), scale, *mesh, info, err)) {
    Log::e("unable to load mesh file \"", objPath, "\": ", err);
    return false;
    }

  // Images named in its MTL file are registered under names of the alias's own: DM_X.3DS -> DM_X_0.TGA, ...
  std::string stem = key;
  if(auto dot = stem.rfind('.'); dot!=std::string::npos)
    stem.resize(dot);
  for(size_t i=0; i<mesh->sub_meshes.size(); ++i) {
    auto& mat = mesh->sub_meshes[i].mat;
    if(!texture.empty()) {
      mat.texture = std::string(texture);
      }
    else if(!info[i].texFile.empty()) {
      mat.texture = stem + "_" + std::to_string(i) + ".TGA";
      inst->customTextures[mat.texture] = info[i].texFile;
      }
    }

  MeshFile f;
  f.path    = std::string(objPath);
  f.texture = std::string(texture);
  f.scale   = scale;
  f.mesh    = std::move(mesh);
  inst->meshFiles[key] = std::move(f);
  inst->aniMeshCache.erase(std::string(alias));
  inst->aniMeshCache.erase(key);
  return true;
  }

std::vector<std::string> Resources::meshTextures(std::string_view mesh) {
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  if(FileExt::hasExt(mesh,"ASC") || FileExt::hasExt(mesh,"MDM")) {
    // A creature's or a body's skinned mesh.
    std::string mdm(mesh);
    FileExt::exchangeExt(mdm,"ASC","MDM");
    std::vector<std::string> out;
    const auto* entry = Resources::vdfsIndex().find(mdm);
    if(entry==nullptr)
      return out;
    zenkit::ModelMesh zmdm;
    auto reader = entry->open_read();
    zmdm.load(reader.get());
    for(auto& skin:zmdm.meshes)
      for(auto& sub:skin.mesh.sub_meshes)
        out.push_back(sub.mat.texture);
    for(auto& [_,att]:zmdm.attachments)
      for(auto& sub:att.sub_meshes)
        out.push_back(sub.mat.texture);
    return out;
    }
  std::string mrm(mesh);
  FileExt::exchangeExt(mrm,"3DS","MRM");
  std::vector<std::string> out;
  const auto* entry = Resources::vdfsIndex().find(mrm);
  if(entry==nullptr)
    return out;
  zenkit::MultiResolutionMesh zmsh;
  auto reader = entry->open_read();
  zmsh.load(reader.get());
  for(auto& sub:zmsh.sub_meshes)
    out.push_back(sub.mat.texture);
  return out;
  }

bool Resources::exportTexture(std::string_view name, std::string_view path, const float tint[3], float strength,
                              float brighten) {
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  auto alt = std::string(name);
  if(FileExt::hasExt(alt,"TGA")) {
    alt.resize(alt.size()+2);
    std::memcpy(&alt[0]+alt.size()-6, "-C.TEX", 6);
    }
  const auto* entry = Resources::vdfsIndex().find(alt);
  if(entry==nullptr)
    return false;
  try {
    zenkit::Texture tex;
    auto reader = entry->open_read();
    tex.load(reader.get());
    auto rgba = tex.as_rgba8(0);
    if(tint!=nullptr && strength>0.f) {
      // Towards the tint by each pixel's own lightness: shapes, shading and transparency stay.
      for(size_t i=0; i+3<rgba.size(); i+=4) {
        float r = rgba[i], g = rgba[i+1], b = rgba[i+2];
        float lum = (0.299f*r + 0.587f*g + 0.114f*b)*brighten;
        float c[3] = {r, g, b};
        for(int k=0; k<3; ++k) {
          float to = std::min(255.f, lum*tint[k]);
          rgba[i+size_t(k)] = uint8_t(std::clamp(c[k]*(1.f-strength) + to*strength, 0.f, 255.f));
          }
        }
      }
    Pixmap pm(tex.width(), tex.height(), TextureFormat::RGBA8);
    std::memcpy(pm.data(), rgba.data(), rgba.size());
    pm.save(std::string(path).c_str(), "png");
    return true;
    }
  catch(...) {
    return false;
    }
  }

bool Resources::exportMeshObj(std::string_view mesh, std::string_view objPath, const float tint[3], float strength,
                              float brighten) {
  std::lock_guard<std::recursive_mutex> g(inst->sync);
  std::string mrm(mesh);
  FileExt::exchangeExt(mrm,"3DS","MRM");
  const auto* entry = Resources::vdfsIndex().find(mrm);
  if(entry==nullptr)
    return false;
  zenkit::MultiResolutionMesh zmsh;
  try {
    auto reader = entry->open_read();
    zmsh.load(reader.get());
    }
  catch(...) {
    return false;
    }
  if(zmsh.sub_meshes.empty())
    return false;

  const std::filesystem::path obj(std::string{objPath});
  const auto dir  = obj.parent_path();
  const auto stem = obj.stem().string();
  std::ofstream out(obj);
  std::ofstream mtl(dir / (stem + ".mtl"));
  if(!out || !mtl)
    return false;
  out << "# " << std::string(mesh) << ", written out by OpenGothic (y up, 1 unit = 1 cm)\n";
  out << "mtllib " << stem << ".mtl\n";
  // Positions and normals into the file's right-handed space (z negated), uvs with v flipped back: ObjMesh::load
  // undoes exactly this.
  for(auto& p:zmsh.positions)
    out << "v " << p.x << " " << p.y << " " << -p.z << "\n";
  size_t vt = 0, vn = 0;
  for(size_t s=0; s<zmsh.sub_meshes.size(); ++s) {
    auto& sm = zmsh.sub_meshes[s];
    for(auto& w:sm.wedges) {
      out << "vt " << w.texture.x << " " << 1.f-w.texture.y << "\n";
      out << "vn " << w.normal.x << " " << w.normal.y << " " << -w.normal.z << "\n";
      }
    std::string matName = "m" + std::to_string(s);
    std::string texName = sm.mat.texture;
    mtl << "newmtl " << matName << "\n";
    if(!texName.empty()) {
      std::string png = stem + "_" + std::to_string(s) + ".png";
      if(exportTexture(texName, (dir / png).string(), tint, strength, brighten))
        mtl << "map_Kd " << png << "\n";
      }
    out << "usemtl " << matName << "\n";
    for(auto& t:sm.triangles) {
      out << "f";
      for(int k=0; k<3; ++k) {
        auto& w = sm.wedges[t.wedges[k]];
        const size_t i = size_t(t.wedges[k]);
        out << " " << (w.index+1) << "/" << (vt+i+1) << "/" << (vn+i+1);
        }
      out << "\n";
      }
    vt += sm.wedges.size();
    vn += sm.wedges.size();
    }
  return bool(out);
  }
