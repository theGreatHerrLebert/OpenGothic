#include "pybindings_common.h"

namespace py = pybind11;

namespace PyBindings {

const char16_t kCp1252High[32] = {
  0x20AC,0x0081,0x201A,0x0192,0x201E,0x2026,0x2020,0x2021,0x02C6,0x2030,0x0160,0x2039,0x0152,0x008D,0x017D,0x008F,
  0x0090,0x2018,0x2019,0x201C,0x201D,0x2022,0x2013,0x2014,0x02DC,0x2122,0x0161,0x203A,0x0153,0x009D,0x017E,0x0178,
  };

std::string toPy(std::string_view in) {
  std::string out;
  out.reserve(in.size());
  for(char ch:in) {
    const uint8_t b = uint8_t(ch);
    const uint32_t cp = (b>=0x80 && b<0xA0) ? kCp1252High[b-0x80] : b;
    if(cp<0x80) {
      out.push_back(char(cp));
      } else if(cp<0x800) {
      out.push_back(char(0xC0 | (cp>>6)));
      out.push_back(char(0x80 | (cp&0x3F)));
      } else {
      out.push_back(char(0xE0 | (cp>>12)));
      out.push_back(char(0x80 | ((cp>>6)&0x3F)));
      out.push_back(char(0x80 | (cp&0x3F)));
      }
    }
  return out;
  }

std::string toEngine(std::string_view in) {
  std::string out;
  out.reserve(in.size());
  for(size_t i=0; i<in.size();) {
    const uint8_t b = uint8_t(in[i]);
    uint32_t cp  = b;
    size_t   len = 1;
    if(b>=0xF0)      { len=4; cp=b&0x07u; }
    else if(b>=0xE0) { len=3; cp=b&0x0Fu; }
    else if(b>=0xC0) { len=2; cp=b&0x1Fu; }
    for(size_t r=1; r<len && i+r<in.size(); ++r)
      cp = (cp<<6) | (uint8_t(in[i+r])&0x3Fu);
    i += len;

    char mapped = '?';
    if(cp<0x80 || (cp>=0xA0 && cp<=0xFF)) {
      mapped = char(cp);
      } else {
      for(uint32_t h=0; h<32; ++h)
        if(kCp1252High[h]==cp)
          mapped = char(0x80+h);
      }
    out.push_back(mapped);
    }
  return out;
  }

World* requireWorld() {
  auto* w = Gothic::inst().world();
  if(w == nullptr)
    throw std::runtime_error("no active world");
  return w;
  }

Npc* requirePlayer() {
  auto* p = Gothic::inst().player();
  if(p == nullptr)
    throw std::runtime_error("no active player");
  return p;
  }

std::string instanceClass(World& w, const std::string& name, size_t& id) {
  auto& sc = w.script();
  id = sc.findSymbolIndex(name);
  auto* sym = id==size_t(-1) ? nullptr : sc.findSymbol(id);
  if(sym==nullptr || sym->parent()==uint32_t(-1) ||
     sym->type()!=zenkit::DaedalusDataType::INSTANCE || sym->address()==0)
    return "";
  const auto* cls = sym;
  while(cls!=nullptr && cls->parent()!=uint32_t(-1))
    cls = sc.findSymbol(cls->parent());
  return cls!=nullptr ? std::string(cls->name()) : std::string();
  }

std::string upper(std::string s) {
  for(auto& c:s)
    c = char(std::toupper(uint8_t(c)));
  return s;
  }

} // namespace PyBindings

using namespace PyBindings;

PYBIND11_EMBEDDED_MODULE(gothic, m) {
  m.doc() = "OpenGothic runtime bindings (PoC). Access live engine state "
            "from Python. Mutations are safe only from the main thread.";

  bindPlayer(m);
  bindNpc(m);
  bindWorld(m);
  bindOverlay(m);
  bindTrip(m);
  bindResources(m);
  bindSky(m);
  bindMusic(m);
  bindDialog(m);
  bindRuntime(m);
  bindDaedalus(m);
  }

void pybindingsLinkAnchor() {}
