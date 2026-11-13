#include "snowtrail.h"

#include <algorithm>
#include <cmath>
#include <cstring>

using namespace Tempest;

void SnowTrail::init() {
  for(auto& buf:ssbo)
    buf = Resources::device().ssbo(BufferHeap::Upload, cells.data(), cells.size()*sizeof(cells[0]));
  }

Vec4 SnowTrail::box() const {
  return Vec4(origin.x, origin.y, 1.f/Cell, empty ? 0.f : float(Size));
  }

void SnowTrail::tick(const Vec3& hero, bool onGround, float cover, float snowfall, uint64_t tickCount, uint8_t fId,
                     const std::vector<Walker>& others) {
  if(cover<0.02f) {
    if(!empty) {
      std::fill(cells.begin(), cells.end(), uint16_t(0));
      empty = true;
      dirty = 0xFF;
      }
    placed = false;
    }
  else {
    recentre(hero);
    // A step every 65 cm along the path, left and right of it, while one walks on the ground: the hero, and everyone
    // inside the square with him.
    if(!placed)
      walkers.clear();
    placed = true;
    step(Walker{0, hero, onGround, 1.f}, tickCount);
    const float half = float(Size)*Cell*0.5f;
    for(auto& w:others)
      if(std::abs(w.pos.x-origin.x-half)<half && std::abs(w.pos.z-origin.y-half)<half)
        step(w, tickCount);
    // forget who has gone: the next time they come they start a fresh trail
    for(auto i=walkers.begin(); i!=walkers.end();)
      i = i->second.seen==tickCount ? std::next(i) : walkers.erase(i);
    // Fresh snow fills the prints: in a full blizzard within about a minute and a half.
    if(lastFill==0)
      lastFill = tickCount;
    if(tickCount-lastFill>=250) {
      fillDebt += snowfall*255.f*float(tickCount-lastFill)/90000.f;
      lastFill  = tickCount;
      if(fillDebt>=1.f) {
        fill(uint8_t(std::min(fillDebt, 255.f)));
        fillDebt -= std::floor(fillDebt);
        }
      }
    }

  if((dirty>>fId)&1) {
    auto& buf = ssbo[fId];
    const size_t bytes = cells.size()*sizeof(cells[0]);
    if(buf.byteSize()<bytes) {
      Resources::recycle(std::move(buf));
      buf = Resources::device().ssbo(BufferHeap::Upload, Uninitialized, bytes);
      }
    buf.update(cells.data(), 0, bytes);
    dirty = uint8_t(dirty & ~(1u<<fId));
    }
  }

void SnowTrail::step(const Walker& w, uint64_t tickCount) {
  auto [it, fresh] = walkers.try_emplace(w.key);
  auto& st = it->second;
  st.seen = tickCount;
  if(fresh) {
    st.last = w.pos;
    return;
    }
  const float dx = w.pos.x-st.last.x, dz = w.pos.z-st.last.z;
  const float d  = std::sqrt(dx*dx + dz*dz);
  const float stride = 65.f*std::max(w.size, 0.4f);
  if(d>stride && d<400.f && w.onGround) {
    const Vec2  dir  = Vec2(dx/d, dz/d);
    const float side = (st.left ? -11.f : 11.f)*w.size;
    stamp(w.pos.x - dir.y*side, w.pos.y, w.pos.z + dir.x*side, dir, w.size);
    st.left = !st.left;
    st.last = w.pos;
    }
  else if(d>=400.f) {
    st.last = w.pos;   // a teleport or a fall: no trail across the gap
    }
  }

void SnowTrail::recentre(const Vec3& hero) {
  const float half = float(Size)*Cell*0.5f;
  const float cx = origin.x+half, cz = origin.y+half;
  if(empty)
    base = hero.y;
  if(!empty && std::abs(hero.x-cx)<half*0.5f && std::abs(hero.z-cz)<half*0.5f && std::abs(hero.y-base)<2500.f)
    return;
  if(!empty && std::abs(hero.y-base)>=2500.f) {
    // far up or down from where the prints were made: start a fresh square there
    std::fill(cells.begin(), cells.end(), uint16_t(0));
    empty = true;
    base  = hero.y;
    dirty = 0xFF;
    }
  // Move the square so he stands in its middle again, keeping the prints that are still inside.
  const int sx = empty ? 0 : int(std::round((hero.x-cx)/Cell));
  const int sz = empty ? 0 : int(std::round((hero.z-cz)/Cell));
  if(!empty && (sx!=0 || sz!=0)) {
    std::vector<uint16_t> moved(cells.size(), 0);
    for(int z=0; z<Size; ++z)
      for(int x=0; x<Size; ++x) {
        const int ox = x+sx, oz = z+sz;
        if(ox>=0 && oz>=0 && ox<Size && oz<Size)
          moved[size_t(z*Size+x)] = cells[size_t(oz*Size+ox)];
        }
    cells = std::move(moved);
    dirty = 0xFF;
    }
  origin = Vec2(hero.x-half, hero.z-half);
  if(!empty)
    origin = Vec2(cx-half+float(sx)*Cell, cz-half+float(sz)*Cell);
  }

void SnowTrail::stamp(float x, float y, float z, Vec2 dir, float size) {
  const int step = std::clamp(int(std::round((y-base)/25.f))+128, 0, 255);
  // An oval 28 cm long along the walk and 12 cm wide, for a person; an animal's smaller and rounder.
  const float halfLen = 14.f*size, halfWid = 6.f*std::sqrt(size);
  const int   r  = int(std::ceil(halfLen/Cell))+1;
  const int   cx = int((x-origin.x)/Cell), cz = int((z-origin.y)/Cell);
  for(int j=-r; j<=r; ++j)
    for(int i=-r; i<=r; ++i) {
      const int px = cx+i, pz = cz+j;
      if(px<0 || pz<0 || px>=Size || pz>=Size)
        continue;
      const float wx = origin.x+(float(px)+0.5f)*Cell-x, wz = origin.y+(float(pz)+0.5f)*Cell-z;
      const float along  = (wx*dir.x + wz*dir.y)/halfLen;
      const float across = (-wx*dir.y + wz*dir.x)/halfWid;
      const float e = along*along + across*across;
      if(e>1.f)
        continue;
      auto&         c     = cells[size_t(pz*Size+px)];
      const uint8_t depth = uint8_t(255.f*(1.f-e*0.4f));
      const int     was   = int(c>>8);
      // A print on another level (a bridge over the path, the path under a ledge) is replaced, not deepened.
      if(depth>=uint8_t(c & 0xFF) || std::abs(was-step)>2)
        c = uint16_t((step<<8) | depth);
      }
  empty = false;
  dirty = 0xFF;
  }

void SnowTrail::fill(uint8_t amount) {
  if(empty)
    return;
  bool any = false;
  for(auto& c:cells) {
    const uint8_t depth = uint8_t(c & 0xFF);
    c   = depth>amount ? uint16_t((c & 0xFF00) | (depth-amount)) : uint16_t(0);
    any = any || c!=0;
    }
  empty = !any;
  dirty = 0xFF;
  }
