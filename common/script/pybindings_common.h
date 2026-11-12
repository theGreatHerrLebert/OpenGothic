// Shared between the translation units that make up the embedded `gothic` Python module.
#pragma once

#include <pybind11/embed.h>
#include <pybind11/stl.h>

#include <string>
#include <string_view>
#include <vector>

#include "gothic.h"
#include "game/constants.h"
#include "world/waypoint.h"
#include "world/world.h"
#include "world/objects/item.h"
#include "world/objects/npc.h"

namespace PyBindings {

namespace py = pybind11;

// The engine and its fonts use Windows-1252 bytes; Python strings are Unicode.
// Every string crossing this boundary goes through one of these two functions.
std::string toPy(std::string_view in);
std::string toEngine(std::string_view in);

World* requireWorld();
Npc*   requirePlayer();

// Returns the root Daedalus class of an instance symbol, or "".
std::string instanceClass(World& w, const std::string& name, size_t& id);
std::string upper(std::string s);

// ---------- PyPlayer ----------
struct PyPlayer {
  py::tuple position() const {
    auto* p = requirePlayer();
    auto  v = p->position();
    return py::make_tuple(v.x, v.y, v.z);
    }
  float rotation() const    { return requirePlayer()->rotation(); }
  int   hp() const          { return requirePlayer()->attribute(ATR_HITPOINTS); }
  int   hpMax() const       { return requirePlayer()->attribute(ATR_HITPOINTSMAX); }
  bool  alive() const       {
    auto* p = requirePlayer();
    return !p->isDead() && !p->isUnconscious();
    }
  std::string name() const  { return toPy(requirePlayer()->displayName()); }

  std::string waypoint() const {
    auto* wp = requireWorld()->findWayPoint(requirePlayer()->position());
    return wp!=nullptr ? wp->name : std::string();
    }

  std::string room() const {
    return std::string(requireWorld()->roomAt(requirePlayer()->position()));
    }

  py::list items() const {
    auto*    p  = requirePlayer();
    py::list out;
    auto     it = p->inventory().iterator(Inventory::T_Inventory);
    while(it.isValid()) {
      py::dict d;
      d["name"]     = toPy(it->displayName());
      auto* sym = requireWorld()->script().findSymbol(it->clsId());
      d["instance"] = sym!=nullptr ? std::string(sym->name()) : std::string();
      d["count"]    = it.count();
      d["equipped"] = it.isEquipped();
      out.append(d);
      ++it;
      }
    return out;
    }

  std::string repr() const  {
    auto* p = requirePlayer();
    auto  v = p->position();
    char  buf[160];
    std::snprintf(buf, sizeof(buf),
                  "<gothic.Player name=%.64s hp=%d/%d pos=(%.1f, %.1f, %.1f)>",
                  toPy(p->displayName()).c_str(),
                  p->attribute(ATR_HITPOINTS),
                  p->attribute(ATR_HITPOINTSMAX),
                  v.x, v.y, v.z);
    return buf;
    }
  };

// ---------- PyNpc ----------
// Holds the Npc object itself. A World's npc index shifts when NPCs are added
// or removed, so the index is only a lookup hint and is never trusted alone.
struct PyNpc {
  Npc*     ptr   = nullptr;
  World*   world = nullptr;
  uint32_t hint  = 0;
  uint32_t sym   = 0;

  static PyNpc wrap(World& w, Npc& n, uint32_t index) {
    PyNpc r;
    r.ptr   = &n;
    r.world = &w;
    r.hint  = index;
    r.sym   = n.instanceSymbol();
    return r;
    }

  static PyNpc wrap(World& w, Npc& n) {
    const uint32_t cnt = w.npcCount();
    for(uint32_t i=0; i<cnt; ++i)
      if(w.npcById(i)==&n)
        return wrap(w,n,i);
    throw std::runtime_error("npc is not in the active world");
    }

  bool locate() const {
    auto* w = requireWorld();
    if(w!=world)
      return false;
    const uint32_t cnt = w->npcCount();
    if(hint<cnt && w->npcById(hint)==ptr)
      return ptr->instanceSymbol()==sym;
    for(uint32_t i=0; i<cnt; ++i)
      if(w->npcById(i)==ptr) {
        const_cast<PyNpc*>(this)->hint = i;
        return ptr->instanceSymbol()==sym;
        }
    return false;
    }

  Npc* fetch() const {
    if(!locate())
      throw std::runtime_error("npc no longer exists");
    return ptr;
    }

  uint32_t index() const {
    fetch();
    return hint;
    }

  std::string instance() const {
    auto* s = requireWorld()->script().findSymbol(size_t(fetch()->instanceSymbol()));
    return s!=nullptr ? std::string(s->name()) : std::string();
    }

  void setName(const std::string& v) { fetch()->handle().name[0] = toEngine(v); }

  static Attribute attributeOf(const std::string& name) {
    static const std::pair<const char*,Attribute> names[] = {
      {"hp",ATR_HITPOINTS},{"hp_max",ATR_HITPOINTSMAX},{"mana",ATR_MANA},{"mana_max",ATR_MANAMAX},
      {"strength",ATR_STRENGTH},{"dexterity",ATR_DEXTERITY}};
    for(auto& [n,a]:names)
      if(name==n)
        return a;
    throw std::invalid_argument("unknown attribute: " + name + " (hp, hp_max, mana, mana_max, strength, dexterity)");
    }

  int32_t attribute(const std::string& name) const { return fetch()->attribute(attributeOf(name)); }

  std::string bodyMesh() const { return fetch()->bodyMesh(); }

  void addItem(const std::string& instance, int32_t count) {
    auto*  n  = fetch();
    auto*  w  = requireWorld();
    size_t id = 0;
    if(count<1 || count>100000)
      throw std::invalid_argument("count out of range");
    if(instanceClass(*w, upper(instance), id)!="C_ITEM")
      throw std::invalid_argument("not an item instance: " + instance);
    n->addItem(id, size_t(count));
    }

  int32_t itemCount(const std::string& instance) const {
    auto*  n  = fetch();
    auto*  w  = requireWorld();
    size_t id = 0;
    if(instanceClass(*w, upper(instance), id)!="C_ITEM")
      throw std::invalid_argument("not an item instance: " + instance);
    return int32_t(n->inventory().itemCount(id));
    }

  void removeItem(const std::string& instance, int32_t count) {
    auto*  n  = fetch();
    auto*  w  = requireWorld();
    size_t id = 0;
    if(count<1 || count>100000)
      throw std::invalid_argument("count out of range");
    if(instanceClass(*w, upper(instance), id)!="C_ITEM")
      throw std::invalid_argument("not an item instance: " + instance);
    n->delItem(id, uint32_t(count));
    }

  void setAttribute(const std::string& name, int32_t value) {
    if(value<0 || value>100000)
      throw std::invalid_argument("attribute value out of range");
    fetch()->handle().attribute[attributeOf(name)] = value;
    }

  int32_t level() const { return fetch()->handle().level; }
  void    setLevel(int32_t v) {
    if(v<0 || v>1000)
      throw std::invalid_argument("level out of range");
    fetch()->handle().level = v;
    }

  // A body texture variant: the game's _V0 texture of the body mesh becomes _V<n>, which a story can register as
  // its own texture (resources.register_texture), so one creature looks different from all others of its kind.
  void setBodyTexture(int32_t variant) {
    if(variant<0 || variant>99)
      throw std::invalid_argument("body texture variant must be 0..99");
    fetch()->setBodyTexture(variant);
    }

  void setScale(float x, float y, float z) {
    if(y<=0) y = x;
    if(z<=0) z = x;
    if(!(x>0.05f && x<20.f && y>0.05f && y<20.f && z>0.05f && z<20.f))
      throw std::invalid_argument("scale out of range");
    fetch()->setScale(x,y,z);
    }

  // Keeps the routine and perception intact: removing them makes an NPC
  // untalkable.
  // Replaces the daily routine with standing at the nearest waypoint.
  void standHere() {
    auto* n  = fetch();
    auto* w  = requireWorld();
    auto* wp = w->findWayPoint(n->position());
    const size_t fn = w->script().findSymbolIndex("ZS_STAND_ARMSCROSSED");
    if(wp==nullptr || fn==size_t(-1))
      throw std::runtime_error("cannot give this NPC a standing routine");
    n->standAtRoutine(uint32_t(fn), wp->name);
    }

  // Gives the NPC this armour and puts it on, replacing what they wear.
  void wear(const std::string& instance) {
    auto*  n  = fetch();
    auto*  w  = requireWorld();
    size_t id = 0;
    if(instanceClass(*w, upper(instance), id)!="C_ITEM")
      throw std::invalid_argument("not an item instance: " + instance);
    n->addItem(id, 1);
    n->useItem(id, Item::NSLOT, true);
    }

  // Uses the engine's perception: range, line of sight and view angle.
  bool canSeePlayer() const {
    auto* n = fetch();
    return (uint32_t(n->canSenseNpc(*requirePlayer(), false)) & uint32_t(SensesBit::SENSE_SEE))!=0;
    }

  // Gives the NPC a routine at a waypoint, so they walk there through the world.
  void sendTo(const std::string& waypoint) {
    auto* n = fetch();
    auto* w = requireWorld();
    const size_t fn = w->script().findSymbolIndex("ZS_STAND_ARMSCROSSED");
    if(w->findPoint(waypoint,false)==nullptr || fn==size_t(-1))
      throw std::invalid_argument("cannot send NPC to: " + waypoint);
    n->standAtRoutine(uint32_t(fn), waypoint);
    }

  void stop() {
    auto* n = fetch();
    n->clearAiQueue();
    n->stopWalking();
    }

  py::tuple position() const {
    auto  v = fetch()->position();
    return py::make_tuple(v.x, v.y, v.z);
    }
  std::string name() const { return toPy(fetch()->displayName()); }
  int  hp() const          { return fetch()->attribute(ATR_HITPOINTS); }
  int  hpMax() const       { return fetch()->attribute(ATR_HITPOINTSMAX); }
  bool alive() const {
    auto* n = fetch();
    return !n->isDead() && !n->isUnconscious();
    }
  bool dead() const { return fetch()->isDead(); }
  bool inState(const std::string& state) const {
    auto id = requireWorld()->script().findSymbolIndex(upper(state));
    if(id==size_t(-1))
      throw std::invalid_argument("no such state: " + state);
    return fetch()->isInState(ScriptFn(id));
    }
  std::string repr() const {
    try {
      auto* n = fetch();
      char buf[160];
      std::snprintf(buf, sizeof(buf), "<gothic.Npc id=%u name=%.64s>",
                    hint, toPy(n->displayName()).c_str());
      return buf;
      }
    catch(const std::exception&) {
      return "<gothic.Npc stale>";
      }
    }
  };

// Only valid until the world changes; used to undo a placement within a plan.
struct PyItem {
  Item* ptr = nullptr;
  void makeQuest(const std::string& description, const std::vector<std::string>& lines) {
    std::vector<std::string> converted;
    for(auto& l:lines)
      converted.push_back(toEngine(l));
    ptr->makeQuestItem(toEngine(description), converted);
    }

  void remove() {
    if(ptr!=nullptr)
      requireWorld()->removeItem(*ptr);
    ptr = nullptr;
    }
  };

// One per module part, called from PYBIND11_EMBEDDED_MODULE(gothic) in this order.
void bindPlayer   (py::module_& m);
void bindNpc      (py::module_& m);
void bindWorld    (py::module_& m);
void bindOverlay  (py::module_& m);
void bindTrip     (py::module_& m);
void bindResources(py::module_& m);
void bindSky      (py::module_& m);
void bindMusic    (py::module_& m);
void bindDialog   (py::module_& m);
void bindRuntime  (py::module_& m);
void bindDaedalus (py::module_& m);

} // namespace PyBindings
