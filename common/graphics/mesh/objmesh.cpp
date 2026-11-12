#include "objmesh.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <limits>
#include <locale>
#include <map>
#include <sstream>
#include <tuple>

namespace {

struct V3 {
  float x = 0, y = 0, z = 0;
  };

V3 sub(const V3& a, const V3& b) { return {a.x-b.x, a.y-b.y, a.z-b.z}; }
V3 cross(const V3& a, const V3& b) { return {a.y*b.z-a.z*b.y, a.z*b.x-a.x*b.z, a.x*b.y-a.y*b.x}; }

V3 normalized(const V3& v) {
  float l = std::sqrt(v.x*v.x + v.y*v.y + v.z*v.z);
  if(l<=std::numeric_limits<float>::min())
    return {0, 1, 0};
  return {v.x/l, v.y/l, v.z/l};
  }

struct Corner {
  long p = -1, t = -1, n = -1;   // 0-based, -1: none
  };

struct Group {
  std::string         material;
  std::vector<Corner> corners;   // three per triangle, in the file's (counter-clockwise) order
  };

struct MtlEntry {
  std::string texFile;
  float       kd[3] = {1, 1, 1};
  };

std::string trim(std::string s) {
  auto b = s.find_first_not_of(" \t\r\n");
  if(b==std::string::npos)
    return "";
  auto e = s.find_last_not_of(" \t\r\n");
  return s.substr(b, e-b+1);
  }

std::string restOfLine(std::istringstream& ln) {
  std::string rest;
  std::getline(ln, rest);
  return trim(rest);
  }

// One index of a face corner: 1-based, negative counts back from the last one so far.
bool resolve(const std::string& s, size_t count, long& out) {
  if(s.empty()) {
    out = -1;
    return true;
    }
  char* end = nullptr;
  long  v   = std::strtol(s.c_str(), &end, 10);
  if(end==s.c_str() || *end!='\0' || v==0)
    return false;
  long i = v>0 ? v-1 : long(count)+v;
  if(i<0 || i>=long(count))
    return false;
  out = i;
  return true;
  }

void loadMtl(const std::filesystem::path& file, std::map<std::string,MtlEntry>& mtl) {
  std::ifstream in(file);
  if(!in)
    return;
  std::string line;
  MtlEntry*   cur = nullptr;
  while(std::getline(in, line)) {
    std::istringstream ln(line);
    ln.imbue(std::locale::classic());
    std::string key;
    ln >> key;
    if(key=="newmtl") {
      cur = &mtl[restOfLine(ln)];
      }
    else if(cur!=nullptr && key=="Kd") {
      ln >> cur->kd[0] >> cur->kd[1] >> cur->kd[2];
      }
    else if(cur!=nullptr && key=="map_Kd") {
      // Options (-bm 1 ...) may come first; the file name is the last word.
      std::string rest = restOfLine(ln), name;
      std::istringstream words(rest);
      for(std::string w; words >> w;)
        name = w;
      if(!name.empty())
        cur->texFile = (file.parent_path() / name).string();
      }
    }
  }

}

bool ObjMesh::load(const std::string& path, float scale, zenkit::MultiResolutionMesh& out, std::vector<SubInfo>& info,
                   std::string& error) {
  std::ifstream in(path);
  if(!in) {
    error = "cannot open " + path;
    return false;
    }

  std::vector<V3>                 pos, nrm;
  std::vector<zenkit::Vec2>       uv;
  std::vector<Group>              groups;
  std::map<std::string,MtlEntry>  mtl;
  size_t                          current = 0;
  groups.push_back(Group{});

  std::string line;
  size_t      lineNo = 0;
  while(std::getline(in, line)) {
    ++lineNo;
    if(auto hash = line.find('#'); hash!=std::string::npos)
      line.resize(hash);
    std::istringstream ln(line);
    ln.imbue(std::locale::classic());   // a decimal point, whatever the process locale
    std::string key;
    if(!(ln >> key))
      continue;
    if(key=="v") {
      V3 v;
      if(!(ln >> v.x >> v.y >> v.z)) {
        error = "bad vertex at line " + std::to_string(lineNo);
        return false;
        }
      pos.push_back(v);
      }
    else if(key=="vt") {
      zenkit::Vec2 t;
      if(!(ln >> t.x)) {
        error = "bad texture coordinate at line " + std::to_string(lineNo);
        return false;
        }
      if(!(ln >> t.y))
        t.y = 0;
      uv.push_back(t);
      }
    else if(key=="vn") {
      V3 n;
      if(!(ln >> n.x >> n.y >> n.z)) {
        error = "bad normal at line " + std::to_string(lineNo);
        return false;
        }
      nrm.push_back(normalized(n));
      }
    else if(key=="f") {
      std::vector<Corner> poly;
      for(std::string w; ln >> w;) {
        std::string part[3];
        size_t      at = 0;
        for(char c:w) {
          if(c=='/') {
            if(++at>2)
              break;
            continue;
            }
          part[at] += c;
          }
        Corner c;
        if(part[0].empty() || at>2 || !resolve(part[0], pos.size(), c.p) || !resolve(part[1], uv.size(), c.t) ||
           !resolve(part[2], nrm.size(), c.n)) {
          error = "bad face at line " + std::to_string(lineNo);
          return false;
          }
        poly.push_back(c);
        }
      if(poly.size()<3) {
        error = "face with fewer than three corners at line " + std::to_string(lineNo);
        return false;
        }
      auto& g = groups[current];
      for(size_t i=1; i+1<poly.size(); ++i) {
        g.corners.push_back(poly[0]);
        g.corners.push_back(poly[i]);
        g.corners.push_back(poly[i+1]);
        }
      }
    else if(key=="usemtl") {
      std::string name = restOfLine(ln);
      auto it = std::find_if(groups.begin(), groups.end(), [&](const Group& g) { return g.material==name; });
      if(it==groups.end()) {
        groups.push_back(Group{name, {}});
        current = groups.size()-1;
        } else {
        current = size_t(std::distance(groups.begin(), it));
        }
      }
    else if(key=="mtllib") {
      loadMtl(std::filesystem::path(path).parent_path() / restOfLine(ln), mtl);
      }
    // o, g, s, l and the rest: nothing to draw
    }

  groups.erase(std::remove_if(groups.begin(), groups.end(), [](const Group& g) { return g.corners.empty(); }),
               groups.end());
  if(groups.empty()) {
    error = "no faces in " + path;
    return false;
    }
  if(pos.size()>std::numeric_limits<uint16_t>::max()) {
    error = "too many vertices (at most 65535)";
    return false;
    }

  // Smooth normals for corners that bring none: the area-weighted sum of the faces around each position.
  std::vector<V3> smooth(pos.size());
  for(auto& g:groups)
    for(size_t i=0; i+2<g.corners.size(); i+=3) {
      auto& a = pos[size_t(g.corners[i  ].p)];
      auto& b = pos[size_t(g.corners[i+1].p)];
      auto& c = pos[size_t(g.corners[i+2].p)];
      V3 fn = cross(sub(b,a), sub(c,a));
      for(size_t k=0; k<3; ++k) {
        auto& s = smooth[size_t(g.corners[i+k].p)];
        s = {s.x+fn.x, s.y+fn.y, s.z+fn.z};
        }
      }

  // Into Gothic's space: centimetres, z mirrored (left-handed).
  out = zenkit::MultiResolutionMesh();
  out.positions.reserve(pos.size());
  for(auto& p:pos)
    out.positions.emplace_back(p.x*scale, p.y*scale, -p.z*scale);
  out.normals.reserve(pos.size());
  for(auto& s:smooth) {
    V3 n = normalized(s);
    out.normals.emplace_back(n.x, n.y, -n.z);
    }

  zenkit::Vec3 lo( std::numeric_limits<float>::max());
  zenkit::Vec3 hi(-std::numeric_limits<float>::max());
  for(auto& g:groups)
    for(auto& c:g.corners) {
      auto& p = out.positions[size_t(c.p)];
      lo = zenkit::Vec3(std::min(lo.x,p.x), std::min(lo.y,p.y), std::min(lo.z,p.z));
      hi = zenkit::Vec3(std::max(hi.x,p.x), std::max(hi.y,p.y), std::max(hi.z,p.z));
      }
  out.bbox.min = lo;
  out.bbox.max = hi;

  info.clear();
  for(auto& g:groups) {
    zenkit::SubMesh sm;
    sm.mat.name  = g.material.empty() ? "DM_OBJ" : g.material;
    sm.mat.color = zenkit::Color(255, 255, 255, 255);
    SubInfo si;
    if(auto m = mtl.find(g.material); m!=mtl.end()) {
      si.texFile = m->second.texFile;
      auto ch = [](float v) { return static_cast<unsigned char>(std::clamp(v, 0.f, 1.f)*255.f + 0.5f); };
      sm.mat.color = zenkit::Color(ch(m->second.kd[0]), ch(m->second.kd[1]), ch(m->second.kd[2]), 255);
      }

    std::map<std::tuple<long,long,long>,uint16_t> wedgeOf;
    auto wedge = [&](const Corner& c) -> long {
      auto key = std::make_tuple(c.p, c.t, c.n);
      if(auto it = wedgeOf.find(key); it!=wedgeOf.end())
        return it->second;
      if(sm.wedges.size()>=std::numeric_limits<uint16_t>::max())
        return -1;
      zenkit::MeshWedge w;
      w.index   = uint16_t(c.p);
      w.normal  = c.n>=0 ? zenkit::Vec3(nrm[size_t(c.n)].x, nrm[size_t(c.n)].y, -nrm[size_t(c.n)].z)
                         : out.normals[size_t(c.p)];
      w.texture = c.t>=0 ? zenkit::Vec2(uv[size_t(c.t)].x, 1.f-uv[size_t(c.t)].y) : zenkit::Vec2(0.f, 0.f);
      auto id = uint16_t(sm.wedges.size());
      sm.wedges.push_back(w);
      wedgeOf[key] = id;
      return id;
      };

    for(size_t i=0; i+2<g.corners.size(); i+=3) {
      long a = wedge(g.corners[i]), b = wedge(g.corners[i+1]), c = wedge(g.corners[i+2]);
      if(a<0 || b<0 || c<0) {
        error = "too many distinct corners in one material (at most 65535)";
        return false;
        }
      // The order stays: mirrored, the file's counter-clockwise front turns the way the game's meshes wind (checked
      // against the game's MRMs: cross(b-a,c-a) points away from their normals, as it does here).
      zenkit::MeshTriangle t;
      t.wedges[0] = uint16_t(a);
      t.wedges[1] = uint16_t(b);
      t.wedges[2] = uint16_t(c);
      sm.triangles.push_back(t);
      }
    out.sub_meshes.push_back(std::move(sm));
    info.push_back(std::move(si));
    }
  return true;
  }
