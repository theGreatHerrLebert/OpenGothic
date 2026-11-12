#include <pybind11/embed.h>
#include <pybind11/stl.h>

#include "gothic.h"
#include "world/aiqueue.h"
#include "world/objects/interactive.h"
#include "gamemusic.h"
#include "graphics/sky/galaxy.h"
#include "game/globaleffects.h"
#include <algorithm>
#include "game/constants.h"
#include "game/gamesession.h"
#include "game/gametime.h"
#include "resources.h"
#include "script/pythonvm.h"
#include "ui/dialogmenu.h"
#include "world/waypoint.h"
#include "world/world.h"
#include "world/objects/item.h"
#include "world/objects/npc.h"

namespace py = pybind11;

namespace {

// The engine and its fonts use Windows-1252 bytes; Python strings are Unicode.
// Every string crossing this boundary goes through one of these two functions.
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

std::string instanceClass(World& w, const std::string& name, size_t& id);
std::string upper(std::string s);

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

// Returns the root Daedalus class of an instance symbol, or "".
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

// ---------- PyWorld ----------
struct PyWorld {
  py::tuple time() const {
    auto t = requireWorld()->time();
    return py::make_tuple(static_cast<int>(t.hour()), static_cast<int>(t.minute()));
    }
  int64_t tickCount() const { return static_cast<int64_t>(requireWorld()->tickCount()); }
  int64_t day() const       { return requireWorld()->time().day(); }
  uint32_t npcCount() const { return requireWorld()->npcCount(); }

  void setTime(int h, int m) {
    if(h < 0 || h >= 24 || m < 0 || m >= 60)
      throw std::invalid_argument("hour must be 0..23 and minute 0..59");
    requireWorld()->setDayTime(h, m);
    }

  py::list npcs() const {
    auto*    w  = requireWorld();
    uint32_t n  = w->npcCount();
    py::list out;
    for(uint32_t i = 0; i < n; ++i) {
      if(auto* n = w->npcById(i))
        out.append(PyNpc::wrap(*w, *n, i));
      }
    return out;
    }

  // Spawns next to the player unless a waypoint is given.
  PyNpc spawn(const std::string& instance, const std::string& waypoint) {
    auto*        w = requireWorld();
    size_t       id = 0;
    if(instanceClass(*w, upper(instance), id)!="C_NPC")
      throw std::invalid_argument("not an NPC instance: " + instance);

    Npc* n = nullptr;
    if(!waypoint.empty()) {
      // addNpc(at) parks an NPC with no routine in dead storage, so use the position
      auto* wp = w->findPoint(waypoint,false);
      if(wp==nullptr)
        throw std::invalid_argument("no such waypoint: " + waypoint);
      n = w->addNpc(id, wp->position());
      } else {
      auto* pl  = requirePlayer();
      auto  pos = pl->position();
      const float a = pl->rotationRad();
      pos.x += -std::sin(a)*150.f;
      pos.z +=  std::cos(a)*150.f;
      n = w->addNpc(id, pos);
      }
    if(n==nullptr)
      throw std::runtime_error("spawn failed: " + instance);
    return PyNpc::wrap(*w, *n);
    }

  py::object instanceKind(const std::string& instance) {
    size_t id = 0;
    const auto cls = instanceClass(*requireWorld(), upper(instance), id);
    if(cls=="C_NPC")
      return py::str("npc");
    if(cls=="C_ITEM")
      return py::str("item");
    return py::none();
    }

  bool hasWaypoint(const std::string& name) const {
    return requireWorld()->findPoint(name,false)!=nullptr;
    }

  // Places an item on the ground at a waypoint, or at an exact spot if one is given.
  PyItem placeItem(const std::string& instance, const std::string& waypoint, int count, py::object position) {
    auto*  w  = requireWorld();
    size_t id = 0;
    if(instanceClass(*w, upper(instance), id)!="C_ITEM")
      throw std::invalid_argument("not an item instance: " + instance);
    Tempest::Vec3 at;
    if(position.is_none()) {
      auto* wp = w->findPoint(waypoint,false);
      if(wp==nullptr)
        throw std::invalid_argument("no such waypoint: " + waypoint);
      at = wp->position();
      } else {
      auto p = position.cast<py::sequence>();
      at = Tempest::Vec3(p[0].cast<float>(), p[1].cast<float>(), p[2].cast<float>());
      }
    const auto ground = w->physic()->landRay(at + Tempest::Vec3(0,100,0), 1000);
    if(ground.hasCol)
      at.y = ground.v.y + 10;
    auto* it = w->addItem(id, at);
    if(it==nullptr)
      throw std::runtime_error("could not place item: " + instance);
    if(count>1)
      it->setCount(size_t(count));
    it->setStoryItem(true);
    PyItem r;
    r.ptr = it;
    return r;
    }

  void removeNpc(const PyNpc& npc) {
    Npc* n = npc.fetch();
    if(n->isPlayer())
      throw std::invalid_argument("cannot remove the player");
    requireWorld()->removeNpc(*n);
    }

  py::list npcsNear(float radius) {
    auto*    w  = requireWorld();
    auto*    pl = requirePlayer();
    py::list out;
    w->detectNpc(pl->position(), radius, [&](Npc& n) {
      if(!n.isPlayer())
        out.append(PyNpc::wrap(*w, n));
      });
    return out;
    }

  uint64_t generation() const { return PythonVM::inst().worldGeneration(); }

  py::object findNpc(const std::string& instance, size_t nth) {
    auto*       w    = requireWorld();
    std::string name = instance;
    for(auto& c:name)
      c = char(std::toupper(uint8_t(c)));
    const size_t id = w->script().findSymbolIndex(name);
    if(id==size_t(-1))
      return py::none();
    auto* n = w->findNpcByInstance(id, nth);
    if(n==nullptr)
      return py::none();
    return py::cast(PyNpc::wrap(*w, *n));
    }

  std::string repr() const {
    try {
      auto* w = requireWorld();
      auto  t = w->time();
      char  buf[96];
      std::snprintf(buf, sizeof(buf), "<gothic.World time=%02d:%02d npcs=%u>",
                    static_cast<int>(t.hour()), static_cast<int>(t.minute()),
                    w->npcCount());
      return buf;
      }
    catch(const std::exception&) {
      return "<gothic.World inactive>";
      }
    }
  };

DialogMenu& requireDialog() {
  auto* d = Gothic::inst().dialogMenu();
  if(d==nullptr)
    throw std::runtime_error("dialogue UI is not available");
  return *d;
  }

} // anonymous namespace

PYBIND11_EMBEDDED_MODULE(gothic, m) {
  m.doc() = "OpenGothic runtime bindings (PoC). Access live engine state "
            "from Python. Mutations are safe only from the main thread.";

  py::class_<PyPlayer>(m, "Player")
      .def_property_readonly("position", &PyPlayer::position)
      .def_property_readonly("rotation", &PyPlayer::rotation)
      .def_property_readonly("hp",       &PyPlayer::hp)
      .def_property_readonly("hp_max",   &PyPlayer::hpMax)
      .def_property_readonly("alive",    &PyPlayer::alive)
      .def_property_readonly("name",     &PyPlayer::name)
      .def_property_readonly("guild",
           [](const PyPlayer&) { return int(requirePlayer()->guild()); },
           "Guild id, comparable with Daedalus constants such as GIL_KDF.")
      .def_property_readonly("weapon",
           [](const PyPlayer&) {
             switch(requirePlayer()->weaponState()) {
               case WeaponState::NoWeapon: return "none";
               case WeaponState::Fist:     return "fist";
               case WeaponState::W1H:
               case WeaponState::W2H:      return "melee";
               case WeaponState::Bow:
               case WeaponState::CBow:     return "ranged";
               case WeaponState::Mage:     return "magic";
               }
             return "none";
             },
           "What the hero has readied: none, fist, melee, ranged or magic.")
      .def_property_readonly("armor",
           [](const PyPlayer&) -> py::object {
             auto* it  = requirePlayer()->currentArmor();
             auto* sym = it==nullptr ? nullptr : requireWorld()->script().findSymbol(it->clsId());
             return sym==nullptr ? py::object(py::none()) : py::object(py::str(std::string(sym->name())));
             },
           "Instance name of the equipped armour, or None.")
      .def_property_readonly("level",
           [](const PyPlayer&) { return int(requirePlayer()->level()); })
      .def_property_readonly("busy",
           [](const PyPlayer&) { return requirePlayer()->interactive()!=nullptr; },
           "True while using a bed, chest or other interactive object.")
      .def_property_readonly("waypoint", &PyPlayer::waypoint,
                             "Name of the nearest waypoint.")
      .def_property_readonly("room",     &PyPlayer::room,
                             "Portal room name, empty when outdoors.")
      .def_property_readonly("items",    &PyPlayer::items,
                             "List of dicts {name, count, equipped} for "
                             "every item in the player's inventory.")
      .def("use_object",
           [](const PyPlayer&, const std::string& scheme, int state, bool quiet) {
             auto* pl = requirePlayer();
             if(state<0) {
               pl->aiPush(AiQueue::aiUseMob(upper(scheme), state));
               return true;
               }
             auto* inter = requireWorld()->availableMob(*pl, upper(scheme));
             if(inter==nullptr)
               return false;
             // The hero does not walk to it on his own, as an NPC's AI_UseMob would: put him on its spot and attach
             // him there, which is what AI_UseMob does once it has arrived.
             Gothic::inst().dmQuietUse = quiet;
             auto at = inter->nearestPoint(*pl);
             pl->setPosition(at.x, at.y, at.z);
             pl->updateTransform();
             pl->setInteraction(inter);
             if(pl->interactive()!=inter) {
               Gothic::inst().dmQuietUse = false;
               return false;
               }
             return true;
             },
           py::arg("scheme"), py::arg("state") = 1, py::arg("quiet") = false,
           "Use the nearest free object of this scheme at once, placed on its spot (state 1 to use, -1 to leave). "
           "quiet skips the object's script routine, such as a bed's sleep menu, until the hero leaves it. True only "
           "if he is really using it.")
      .def("mark_heard",
           [](const PyPlayer&, const std::string& info) {
             auto* w = requireWorld();
             size_t id = 0;
             if(instanceClass(*w, upper(info), id)!="C_INFO")
               throw std::invalid_argument("not a dialogue topic: " + info);
             return w->script().markInfoKnown(requirePlayer()->handle(), upper(info));
             },
           py::arg("info"),
           "Count a topic of the game's own as heard, as if it had been told: its NPC will not open with it again.")
      .def("heard",
           [](const PyPlayer&, const std::string& info) {
             auto* w = requireWorld();
             size_t id = 0;
             if(instanceClass(*w, upper(info), id)!="C_INFO")
               throw std::invalid_argument("not a dialogue topic: " + info);
             return w->script().knowsInfo(requirePlayer()->handle(), upper(info));
             },
           py::arg("info"),
           "Whether the hero has heard this dialogue topic (a C_INFO instance such as DIA_ABUYIN_DU).")
      .def("give_item",
           [](const PyPlayer&, const std::string& instance, int count) {
             auto*  w  = requireWorld();
             size_t id = 0;
             if(instanceClass(*w, upper(instance), id)!="C_ITEM" || count<=0)
               throw std::invalid_argument("cannot give: " + instance);
             requirePlayer()->addItem(id, size_t(count));
             },
           py::arg("instance"), py::arg("count") = 1)
      .def("remove_item",
           [](const PyPlayer&, const std::string& instance, int count) {
             auto*  w  = requireWorld();
             size_t id = 0;
             if(instanceClass(*w, upper(instance), id)!="C_ITEM" || count<=0)
               throw std::invalid_argument("cannot remove: " + instance);
             requirePlayer()->delItem(id, uint32_t(count));
             },
           py::arg("instance"), py::arg("count") = 1)
      .def("quest_item",
           [](const PyPlayer&, const std::string& instance, const std::string& description,
              const std::vector<std::string>& lines) {
             auto* w  = requireWorld();
             auto* p  = requirePlayer();
             size_t id = w->script().findSymbolIndex(upper(instance));
             auto* it = id==size_t(-1) ? nullptr : p->getItem(id);
             if(it==nullptr)
               throw std::invalid_argument("player does not have: " + instance);
             PyItem wrapped;
             wrapped.ptr = it;
             wrapped.makeQuest(description, lines);
             },
           py::arg("instance"), py::arg("description"), py::arg("lines"),
           "Turn an item in the player's inventory into a quest item.")
      .def("set_position",
           [](const PyPlayer&, float x, float y, float z) {
             auto* p = requirePlayer();
             p->setPosition(x, y, z);
             p->updateTransform();
             },
           py::arg("x"), py::arg("y"), py::arg("z"),
           "Teleport the player to (x, y, z). Main-thread only.")
      .def("heal",
           [](const PyPlayer&) {
             auto* p = requirePlayer();
             p->changeAttribute(ATR_HITPOINTS, p->attribute(ATR_HITPOINTSMAX),
                                false);
             },
           "Restore HP to maximum.")
      .def("set_hp",
           [](const PyPlayer&, int hp) {
             auto* p   = requirePlayer();
             int   cur = p->attribute(ATR_HITPOINTS);
             p->changeAttribute(ATR_HITPOINTS, hp - cur, false);
             },
           py::arg("hp"),
           "Set HP directly (clamped by the engine).")
      .def("__repr__", &PyPlayer::repr);

  py::class_<PyNpc>(m, "Npc")
      .def_property_readonly("id",        &PyNpc::index,
                             "Current world index. Changes over time; keep the "
                             "Npc object or `instance` instead.")
      .def_property_readonly("instance",  &PyNpc::instance,
                             "Daedalus instance name, stable across saves.")
      .def_property("display_name", &PyNpc::name, &PyNpc::setName)
      .def("start_dialog",
           [](const PyNpc& self) { self.fetch()->startDialog(*requirePlayer()); },
           "Start a conversation with the player through normal perception.")
      .def("wear", &PyNpc::wear, py::arg("instance"),
           "Give the NPC an armour item and put it on.")
      .def("can_see_player", &PyNpc::canSeePlayer)
      .def("send_to", &PyNpc::sendTo, py::arg("waypoint"),
           "Make the NPC walk to a waypoint and stay there.")
      .def("stand_here", &PyNpc::standHere,
           "Replace the daily routine with standing at the nearest waypoint.")
      .def("stop", &PyNpc::stop,
           "Clear queued AI actions and stop walking. Keeps the NPC talkable.")
      .def_property_readonly("position",  &PyNpc::position)
      .def_property_readonly("name",      &PyNpc::name)
      .def_property_readonly("hp",        &PyNpc::hp)
      .def_property_readonly("hp_max",    &PyNpc::hpMax)
      .def_property_readonly("alive",     &PyNpc::alive)
      .def_property_readonly("dead",      &PyNpc::dead)
      .def_property_readonly("guild", [](const PyNpc& self) { return int32_t(self.fetch()->guild()); },
                             "The NPC's guild number, as the script's GIL_ constants count it.")
      .def_property_readonly("voice", [](const PyNpc& self) { return self.fetch()->handle().voice; },
                             "The NPC's voice number, as its SVMs and dialogue keys use it (5 for _05_).")
      .def("in_state", &PyNpc::inState, py::arg("state"),
           "True while the NPC runs this ZS_ state, for example ZS_MAGICBURN.")
      .def("set_position",
           [](const PyNpc& self, float x, float y, float z) {
             Npc* n = self.fetch();
             n->setPosition(x, y, z);
             n->updateTransform();
             },
           py::arg("x"), py::arg("y"), py::arg("z"))
      .def("heal",
           [](const PyNpc& self) {
             Npc* n = self.fetch();
             n->changeAttribute(ATR_HITPOINTS,
                                n->attribute(ATR_HITPOINTSMAX), false);
             })
      .def("__repr__", &PyNpc::repr);

  py::class_<PyItem>(m, "Item")
      .def("make_quest", &PyItem::makeQuest, py::arg("description"), py::arg("lines"),
           "Make this a quest item: no equipping, no sale value, with story text.")
      .def("remove", &PyItem::remove);

  py::class_<PyWorld>(m, "World")
      .def_property_readonly("time",       &PyWorld::time)
      .def_property_readonly("day",        &PyWorld::day)
      .def_property_readonly("tick_count", &PyWorld::tickCount)
      .def_property_readonly("npc_count",  &PyWorld::npcCount)
      .def_property_readonly("npcs",       &PyWorld::npcs)
      .def("take_perceptions",
           [](const PyWorld&) {
             py::list out;
             for(auto& r:requireWorld()->takePerceptions()) {
               py::dict d;
               d["kind"]    = r.kind;
               d["actor"]   = r.actor;
               d["target"]  = r.target;
               d["item"]    = r.item;
               d["spell"]   = r.spell;
               d["seen_by"] = r.seenBy;
               d["object"]  = r.object;
               d["position"] = r.hasPosition ? py::cast(std::make_tuple(r.position.x, r.position.y, r.position.z))
                                             : py::none();
               out.append(d);
               }
             return out;
             },
           "Events involving the player since the last call, oldest first.")
      .def("set_time", &PyWorld::setTime, py::arg("hour"), py::arg("minute"))
      .def("spawn", &PyWorld::spawn, py::arg("instance"), py::arg("waypoint") = "",
           "Create an NPC by Daedalus instance name, near the player unless a "
           "waypoint is given. Main-thread only.")
      .def("npcs_near", &PyWorld::npcsNear, py::arg("radius"),
           "NPCs within radius of the player, excluding the player.")
      .def_property_readonly("generation", &PyWorld::generation,
                             "Changes every time a world starts loading.")
      .def("instance_kind", &PyWorld::instanceKind, py::arg("instance"),
           "'npc', 'item', or None for a Daedalus instance name.")
      .def("has_waypoint", &PyWorld::hasWaypoint, py::arg("name"))
      .def("waypoint_position",
           [](const PyWorld&, const std::string& name) -> py::object {
             auto* wp = requireWorld()->findPoint(name,false);
             if(wp==nullptr)
               return py::none();
             auto p = wp->position();
             return py::cast(std::make_tuple(p.x, p.y, p.z));
             },
           py::arg("name"), "Where a waypoint is, as (x, y, z), or None.")
      .def("objects_near",
           [](const PyWorld&, float radius) {
             auto* w  = requireWorld();
             auto* pl = requirePlayer();
             py::list out;
             for(auto* i:w->interactivesNear(pl->position(), radius)) {
               py::dict d;
               auto p = i->position();
               d["scheme"]    = std::string(i->schemeName());
               d["name"]      = std::string(i->tag());
               d["focus"]     = std::string(i->focusName());
               d["position"]  = std::make_tuple(p.x, p.y, p.z);
               d["available"] = i->isAvailable();
               out.append(d);
               }
             return out;
             },
           py::arg("radius"), "Usable objects (beds, benches, pipes, anvils ...) within radius of the hero.")
      .def("item_visual",
           [](const PyWorld&, const std::string& instance) -> std::string {
             auto* w   = requireWorld();
             auto& vm  = w->script().getVm();
             auto* sym = vm.find_symbol_by_name(upper(instance));
             if(sym==nullptr)
               return "";
             auto item = std::make_shared<zenkit::IItem>();
             vm.init_instance(item, sym);
             return item->visual;
             },
           py::arg("instance"), "The mesh an item instance is drawn with.")
      .def("define_item",
           [](const PyWorld&, const std::string& carrier, const std::string& like, const std::string& name,
              const std::string& description, std::vector<std::tuple<std::string,int32_t>> rows, int32_t value,
              const std::string& visual, int32_t damage) {
             auto* w = requireWorld();
             auto& vm = w->script().getVm();
             auto* c  = vm.find_symbol_by_name(upper(carrier));
             auto* b  = vm.find_symbol_by_name(upper(like));
             if(c==nullptr || b==nullptr)
               return false;
             GameScript::ItemDefinition def;
             def.base        = b->index();
             def.name        = toEngine(name);
             def.description = toEngine(description);
             for(size_t i=0; i<rows.size() && i+1<zenkit::IItem::text_count; ++i) {
               def.text[i+1]  = toEngine(std::get<0>(rows[i]));   // the first row sits under the title, kept blank
               def.count[i+1] = std::get<1>(rows[i]);
               }
             def.value  = value;
             def.visual = visual;
             def.damage = damage;
             w->script().defineItem(c->index(), std::move(def));
             return true;
             },
           py::arg("carrier"), py::arg("like"), py::arg("name"), py::arg("description") = "",
           py::arg("rows") = std::vector<std::tuple<std::string,int32_t>>{}, py::arg("value") = -1,
           py::arg("visual") = "", py::arg("damage") = 0,
           "Make every new item of the carrier instance like the item 'like', with its own name, description and "
           "inventory rows (label, number). The story defines it again after a load.")
      .def("reserve_object",
           [](const PyWorld&, const std::string& scheme, float x, float z, float radius, bool on) -> py::object {
             // The object of this scheme nearest (x, z) within radius, kept for the hero or given back. An NPC
             // already using it is told to get up the ordinary way; returns his instance name, "" if nobody was
             // there, None if there is no such object.
             auto* w = requireWorld();
             Interactive* best = nullptr;
             float bestD = radius*radius;
             // The spatial search is three-dimensional and the story gives no height: search tall enough for any
             // floor or hillside, then compare horizontally only.
             for(auto* i:w->interactivesNear(Tempest::Vec3(x, 0, z), std::max(radius, 1.f) + 20000.f)) {
               if(!i->checkMobName(scheme))
                 continue;
               auto  p = i->position();
               float d = (p.x-x)*(p.x-x) + (p.z-z)*(p.z-z);
               if(d<=bestD) {
                 bestD = d;
                 best  = i;
                 }
               }
             if(best==nullptr)
               return py::none();
             best->setReserved(on);
             if(!on) {
               if(best->evicted!=nullptr) {
                 best->evicted->releaseRoutine();   // his own routine back, exactly as it was
                 best->evicted = nullptr;
                 }
               return py::str("");
               }
             auto* user = best->currentUser();
             if(user!=nullptr && !user->isPlayer()) {
               user->aiPush(AiQueue::aiUseMob(scheme, -1));   // stands up, as at the end of his own smoke
               // ... and waits out the reservation on a bench nearby: his routine is held, not just interrupted,
               // or it sends him straight back to his spot. Without a free bench he stands a few steps away.
               auto  bp  = best->position();
               auto  up  = user->position();
               float dx  = up.x-bp.x, dz = up.z-bp.z;
               float len = std::max(std::sqrt(dx*dx + dz*dz), 1.f);
               auto  to  = Tempest::Vec3(up.x + dx/len*250.f, up.y, up.z + dz/len*250.f);
               std::vector<Tempest::Vec3> others;
               for(uint32_t n=0; n<w->npcCount(); ++n)
                 if(auto* o = w->npcById(n); o!=nullptr && o!=user)
                   others.push_back(o->position());
               auto clear = [bp,&others](const WayPoint& wp) {
                 auto  q  = wp.position();
                 float wx = q.x-bp.x, wz = q.z-bp.z;
                 if(wx*wx + wz*wz <= 150.f*150.f || wp.isLocked())
                   return false;
                 for(auto& o:others) {
                   float ox = q.x-o.x, oz = q.z-o.z;
                   if(ox*ox + oz*oz < 90.f*90.f)
                     return false;
                   }
                 return true;
                 };
               auto& script = w->script();
               const size_t sit   = script.findSymbolIndex("ZS_SIT_BENCH");
               const size_t stand = script.findSymbolIndex("ZS_STAND_ARMSCROSSED");
               const WayPoint* wp = nullptr;
               size_t          fn = stand;
               if(auto* bench = w->availableMob(*user, "BENCH"); bench!=nullptr && sit!=size_t(-1)) {
                 wp = w->findWayPoint(bench->position());
                 fn = sit;
                 }
               if(wp==nullptr)
                 wp = w->findWayPoint(to, clear);
               if(wp!=nullptr && fn!=size_t(-1)) {
                 user->holdRoutine(uint32_t(fn), wp->name);
                 best->evicted = user;
                 }
               if(auto* sym = w->script().getVm().find_symbol_by_index(uint32_t(user->handle().symbol_index())))
                 return py::str(sym->name());
               return py::str("?");
               }
             return py::str("");
             },
           py::arg("scheme"), py::arg("x"), py::arg("z"), py::arg("radius") = 150.f, py::arg("on") = true,
           "Keep a usable object for the hero (NPCs treat it as taken; one using it gets up), or give it back.")
      .def("place_item", &PyWorld::placeItem, py::arg("instance"), py::arg("waypoint") = "",
           py::arg("count") = 1, py::arg("position") = py::none())
      .def("remove_npc", &PyWorld::removeNpc, py::arg("npc"))
      .def("find_npc", &PyWorld::findNpc, py::arg("instance"), py::arg("nth") = 0,
           "Find a live NPC by Daedalus instance name, or None.")
      .def("__repr__", &PyWorld::repr);

  m.attr("player") = PyPlayer{};
  m.attr("world")  = PyWorld{};

  py::module_ overlay = m.def_submodule("overlay", "The small DM status panel in the corner of the screen.");
  overlay.def("set",
              [](const std::string& text, float progress, float strength) {
                Gothic::inst().dmStatus = {toEngine(text), progress, std::clamp(strength, 0.f, 1.f)};
                },
              py::arg("text"), py::arg("progress") = -1.f, py::arg("strength") = 1.f,
              "Show text, with progress from 0 to 1, or below zero if the length is unknown. strength (0 to 1) "
              "is how strongly the panel shows; it fades towards it.");
  overlay.def("clear", []() { Gothic::inst().dmStatus = {}; });
  overlay.def("menu",
              [](const std::string& text) { Gothic::inst().dmMenu = toEngine(text); },
              py::arg("text"),
              "Show a menu panel below the status, one line per row, even while the status is hidden. "
              "An empty text closes it.");

  m.def("print_screen",
        [](const std::string& text, int x, int y, const std::string& font, int seconds) {
          // What Gothic::printscreen (the PrintScreen extern) does, which is private.
          Gothic::inst().onPrintScreen(toEngine(text), x, y, seconds,
                                       Resources::font(font, Resources::FontType::Normal, 1));
          },
        py::arg("text"), py::arg("x") = -1, py::arg("y") = -1, py::arg("font") = "FONT_OLD_10_WHITE.TGA",
        py::arg("seconds") = 2,
        "Show a line on screen like the PrintScreen extern: x and y in percent of the screen, -1 centres.");

  m.def("take_keys",
        []() { return Gothic::inst().takeDmKeys(); },
        "DM hotkeys pressed since the last call, oldest first: 'feedback' for Alt+F, '1' to '5' for Alt+1 to Alt+5.");

  py::module_ trip = m.def_submodule("trip", "A trip set live every tick: the view breathes, colour washes over "
                                              "the screen, the world slows and the camera trembles.");
  trip.def("set",
           [](float fov, float speed, std::tuple<float,float,float,float> tint, float time, float shake,
              float post, float edges, float tracers, std::tuple<float,float,float> bands, float zoom, int look,
              float eye, float afterglow) {
             GlobalEffects::Trip t;
             t.eye     = std::clamp(eye,   0.f, 1.f);
             t.afterglow = std::clamp(afterglow, 0.f, 1.f);
             t.look    = std::clamp(look, 0, 2);   // 0 Mindcap, 1 Emberheart, 2 the Invocation
             t.zoom    = std::clamp(zoom, 0.f, 0.3f);
             t.post    = std::clamp(post, 0.f, 1.f);
             t.edges   = std::clamp(edges, 0.f, 1.f);
             t.tracers = std::clamp(tracers, 0.f, 1.f);
             t.bass    = std::max(std::get<0>(bands), 0.f);
             t.mid     = std::max(std::get<1>(bands), 0.f);
             t.treble  = std::max(std::get<2>(bands), 0.f);
             t.fov   = std::max(fov, 0.f);
             t.speed = std::max(speed, 0.05f);
             t.tint  = Tempest::Color(std::get<0>(tint), std::get<1>(tint), std::get<2>(tint),
                                      std::clamp(std::get<3>(tint), 0.f, 1.f));
             t.time  = std::clamp(time, 0.05f, 1.f);
             t.shake = std::max(shake, 0.f);
             requireWorld()->globalFx()->setTrip(t);
             },
           py::arg("fov") = 0.f, py::arg("speed") = 1.f, py::arg("tint") = std::make_tuple(0.f,0.f,0.f,0.f),
           py::arg("time") = 1.f, py::arg("shake") = 0.f, py::arg("post") = 0.f, py::arg("edges") = 1.f,
           py::arg("tracers") = 1.f, py::arg("bands") = std::make_tuple(0.f,0.f,0.f), py::arg("zoom") = 0.f,
           py::arg("look") = 0, py::arg("eye") = 0.f, py::arg("afterglow") = 0.f,
           "post (0..1) runs the trip shader over the finished frame: glowing edges, tracers, colour; "
           "bands are the music's bass, mid and treble, smoothed.");
  trip.def("clear", []() { requireWorld()->globalFx()->setTrip(GlobalEffects::Trip()); });
  trip.def("take_escapes", []() { auto n = Gothic::inst().dmEscapeRefused; Gothic::inst().dmEscapeRefused = 0; return n; },
           "How often Escape was held back since the last call (while saving is refused).");
  trip.def("block_save", [](bool on) { Gothic::inst().dmBlockSave = on; }, py::arg("on"),
           "While on, saving is refused as it is during a conversation, quick save included.");

  py::module_ weather = m.def_submodule("weather", "Weather the story lays over the world.");
  weather.def("snow", [](float density) { requireWorld()->globalFx()->setSnow(std::clamp(density, 0.f, 1.f)); },
              py::arg("density"), "Falling snow, 0 none .. 1 a blizzard.");

  py::module_ res = m.def_submodule("resources", "A story's own looks: textures from its files, variants of game meshes.");
  res.def("mesh_textures", [](const std::string& mesh) { return Resources::meshTextures(mesh); }, py::arg("mesh"),
          "The textures a game mesh (.3DS) is drawn with.");
  res.def("export_texture",
          [](const std::string& name, const std::string& path, std::tuple<float,float,float> tint, float strength,
             float brighten) {
            const float t[3] = {std::get<0>(tint), std::get<1>(tint), std::get<2>(tint)};
            return Resources::exportTexture(name, path, t, strength, brighten);
            }, py::arg("name"), py::arg("path"), py::arg("tint") = std::make_tuple(1.f,1.f,1.f),
          py::arg("strength") = 0.f, py::arg("brighten") = 1.f,
          "Write a game texture out as a PNG file, recoloured towards tint by strength (0 keeps it as it is).");
  res.def("export_mesh",
          [](const std::string& mesh, const std::string& path, std::tuple<float,float,float> tint, float strength,
             float brighten) {
            const float t[3] = {std::get<0>(tint), std::get<1>(tint), std::get<2>(tint)};
            return Resources::exportMeshObj(mesh, path, t, strength, brighten);
            }, py::arg("mesh"), py::arg("path"), py::arg("tint") = std::make_tuple(1.f,1.f,1.f),
          py::arg("strength") = 0.f, py::arg("brighten") = 1.f,
          "Write a game mesh (.3DS) out as OBJ with its MTL and PNG textures (recoloured if strength > 0), to be "
          "reshaped and read back as a story's own model.");
  res.def("register_texture", [](const std::string& name, const std::string& path) {
            Resources::registerTexture(name, path);
            }, py::arg("name"), py::arg("path"), "A texture name that loads from this image file.");
  res.def("register_mesh_variant",
          [](const std::string& alias, const std::string& base, const std::map<std::string,std::string>& textures) {
            if(!Resources::registerMeshVariant(alias, base, textures))
              return false;
            if(auto* w = Gothic::inst().world())
              w->refreshItemVisuals(alias);   // items loaded before it was registered are drawn now
            return true;
            }, py::arg("alias"), py::arg("base"), py::arg("textures"),
          "A mesh name that is the game mesh 'base' drawn with some textures swapped: {game texture: own name}.");
  res.def("register_mesh_file",
          [](const std::string& alias, const std::string& path, const std::string& texture, float scale) {
            if(!Resources::registerMeshFile(alias, path, texture, scale))
              return false;
            if(auto* w = Gothic::inst().world())
              w->refreshItemVisuals(alias);   // items loaded before it was registered are drawn now
            return true;
            }, py::arg("alias"), py::arg("path"), py::arg("texture") = "", py::arg("scale") = 1.f,
          "A mesh name (DM_....3DS) that is the Wavefront OBJ file 'path': y up, model facing -z, 1 unit = 'scale' cm, "
          "origin where it stands; drawn with the registered texture 'texture', or with its MTL file's images.");

  py::module_ sky = m.def_submodule("sky", "A galaxy in place of the sky: images loaded once, shown as strongly as set.");
  sky.def("load", [](int slot, const std::string& path) { return ::Galaxy::inst().load(size_t(std::max(slot, 0)), path); },
          py::arg("slot"), py::arg("path"),
          "Load an image: slot 0 a 360-degree panorama (equirectangular), 1 and 2 nebulae placed on the sky.");
  sky.def("galaxy",
          [](float amount, float gain, std::tuple<float,float,float> tint, float grade, float spin, float glow,
             std::vector<std::tuple<float,float,float,float>> nebulae, float aurora, float time, float moon) {
            GlobalEffects::Galaxy g;
            g.amount = std::clamp(amount, 0.f, 1.f);
            g.gain   = std::max(gain, 0.f);
            g.tint   = Tempest::Vec3(std::get<0>(tint), std::get<1>(tint), std::get<2>(tint));
            g.grade  = std::clamp(grade, 0.f, 1.f);
            g.spin   = spin;
            g.glow   = std::clamp(glow, 0.f, 1.f);
            for(size_t i=0; i<nebulae.size() && i<2; ++i) {
              auto& n = nebulae[i];
              g.nebula[i] = Tempest::Vec4(std::get<0>(n), std::get<1>(n), std::get<2>(n), std::get<3>(n));
              }
            g.aurora = std::clamp(aurora, 0.f, 1.f);
            g.time   = time;
            g.moon   = std::clamp(moon, 0.f, 1.f);
            requireWorld()->globalFx()->setGalaxy(g);
            },
          py::arg("amount"), py::arg("gain") = 1.f, py::arg("tint") = std::make_tuple(1.f,1.f,1.f),
          py::arg("grade") = 0.f, py::arg("spin") = 0.f, py::arg("glow") = 0.f,
          py::arg("nebulae") = std::vector<std::tuple<float,float,float,float>>{},
          py::arg("aurora") = 0.f, py::arg("time") = 0.f, py::arg("moon") = 0.f,
          "amount 0 is the game's sky, 1 the galaxy instead; nebulae are (yaw, pitch, size, strength) in radians; "
          "aurora (0..1) lays northern lights over it, drifting with time (seconds) and flaring with glow; "
          "moon (0..1) raises a blood-red moon.");
  sky.def("clear", []() { requireWorld()->globalFx()->setGalaxy(GlobalEffects::Galaxy()); });

  py::module_ music = m.def_submodule("music", "A story's own track beside the game's music; mix() crossfades.");
  music.def("play_track", [](const std::string& path) { return GameMusic::inst().playTrack(path); },
            py::arg("path"), "Start a WAV or OGG track at volume 0. Returns False if it cannot be loaded.");
  music.def("stop_track", []() { GameMusic::inst().stopTrack(); });
  music.def("mix", [](float track, float theme) { GameMusic::inst().mix(track, theme); },
            py::arg("track"), py::arg("theme"),
            "Track volume and the game's music volume, each 0 to 1, relative to the music volume setting.");
  music.def("track_playing", []() { return GameMusic::inst().isTrackPlaying(); });

  py::module_ dialog = m.def_submodule(
      "dialog", "Drive the native dialogue UI for one bound NPC from Python.");
  dialog.def("bind",
             [](const PyNpc& npc) { requireDialog().agentBind(npc.fetch()); },
             py::arg("npc"),
             "Talking to this NPC opens an empty Python-driven dialogue.");
  dialog.def("unbind",
             [](py::object npc) {
               requireDialog().agentUnbind(npc.is_none() ? nullptr : npc.cast<PyNpc>().fetch());
               },
             py::arg("npc") = py::none(),
             "Stop driving one NPC, or every NPC when none is given.");
  dialog.def("is_open", []() { return requireDialog().agentActive(); });
  dialog.def("just_opened", []() { return requireDialog().agentTakeOpened(); },
             "True once after the player starts the dialogue.");
  dialog.def("busy", []() { return requireDialog().agentBusy(); },
             "True while a line is still being shown.");
  dialog.def("say",
             [](const std::string& text, bool player, int ms, const std::string& wav) {
               if(ms<=0)
                 ms = std::max(2000, int(text.size())*70);
               return requireDialog().agentSay(toEngine(text), player, uint64_t(ms), wav);
               },
             py::arg("text"), py::arg("player") = false, py::arg("ms") = 0, py::arg("wav") = "",
             "Show a subtitle line. Returns False if the UI is busy; retry "
             "on a later tick.");
  dialog.def("narrate",
             [](const std::string& text, int ms, const std::string& wav) {
               if(ms<=0)
                 ms = std::max(2500, int(text.size())*70);
               return requireDialog().narrate(toEngine(text), uint64_t(ms), wav);
               },
             py::arg("text"), py::arg("ms") = 0, py::arg("wav") = "",
             "Play a line from off-screen with a subtitle near the top. Returns False while a "
             "conversation or another narrator line is running; retry later.");
  dialog.def("narrating", []() { return requireDialog().narrating(); });
  dialog.def("set_choices",
             [](const std::vector<std::string>& c) {
               std::vector<std::string> titles;
               for(auto& t:c)
                 titles.push_back(toEngine(t));
               requireDialog().agentSetChoices(titles);
               },
             py::arg("choices"));
  dialog.def("poll_selection",
             []() -> py::object {
               const int s = requireDialog().agentTakeSelection();
               return s<0 ? py::none() : py::cast(s);
               },
             "Index of the choice just picked, or None. Reports once.");
  dialog.def("partner",
             []() -> py::object {
               auto* n = requireDialog().partner();
               auto* w = requireWorld();
               return n==nullptr ? py::none() : py::cast(PyNpc::wrap(*w, *n));
               },
             "NPC the player is talking to in any dialogue, or None.");
  dialog.def("close", []() { requireDialog().agentClose(); });
  dialog.def("set_topics",
             [](const PyNpc& npc, const std::vector<std::pair<std::string,std::string>>& topics) {
               std::vector<std::pair<std::string,std::string>> t;
               for(auto& [key,title]:topics)
                 t.emplace_back(key, toEngine(title));
               requireDialog().agentSetTopics(npc.fetch(), std::move(t));
               },
             py::arg("npc"), py::arg("topics"),
             "A story's topics in this NPC's own menu, as (key, title); an empty list removes them.");
  dialog.def("take_topic",
             []() -> py::object {
               auto key = requireDialog().agentTakeTopic();
               return key.empty() ? py::none() : py::cast(key);
               },
             "The key of a story topic the player just chose in an NPC's own menu, once; or None.");
  dialog.def("end_topic", []() { return requireDialog().agentEndTopic(); },
             "Hand the conversation back to the NPC's own menu after a story topic.");
  dialog.def("trip_talk", [](bool on) { Gothic::inst().dmTripTalk = on; }, py::arg("on"),
             "While on, every conversation except a guard's opens as a story-driven one, for the trip dialogue.");
  dialog.def("block", [](bool on) { Gothic::inst().dmBlockTalk = on; }, py::arg("on"),
             "While on, the hero cannot start a conversation; attempts are counted.");
  dialog.def("take_refused",
             []() { return std::exchange(Gothic::inst().dmTalkRefused, 0u); },
             "Conversations the hero tried to start while blocked, since the last call.");

  // Per-tick callback registry — consumed by PythonVM::tick() which is
  // invoked from World::tick().
  m.attr("_tick_callbacks") = py::list();

  // Called with the save slot file name, or the world name for a new game.
  m.attr("_save_callbacks")     = py::list();
  m.attr("_load_callbacks")     = py::list();
  m.attr("_new_game_callbacks") = py::list();

  m.def("on_tick",
        [](py::object fn) {
          py::module_ g   = py::module_::import("gothic");
          py::list    cbs = g.attr("_tick_callbacks").cast<py::list>();
          cbs.append(fn);
          return py::int_(py::len(cbs) - 1);
          },
        py::arg("fn"),
        "Register a function to be called every simulation tick with dt "
        "(ms) as its argument. Returns the callback's index. Callbacks that "
        "raise are logged but do not tear down the game.");

  m.def("clear_tick_callbacks",
        []() {
          py::module_ g   = py::module_::import("gothic");
          py::list    cbs = g.attr("_tick_callbacks").cast<py::list>();
          cbs.attr("clear")();
          },
        "Remove all registered tick callbacks.");

  m.def("journal",
        [](const std::string& topic, const std::string& entry, int status) {
          requireWorld()->script().addJournalEntry(toEngine(topic), toEngine(entry), status);
          },
        py::arg("topic"), py::arg("entry") = "", py::arg("status") = 0,
        "Add an entry to the player's journal. Status: 0 unchanged, 1 running, "
        "2 success, 3 failed, 4 obsolete.");

  m.def("journal_entries",
        []() {
          py::dict out;
          auto* log = Gothic::inst().questLog();
          if(log==nullptr)
            return out;
          for(size_t i=0; i<log->questCount(); ++i) {
            auto& q = log->quest(i);
            py::list entries;
            for(auto& e:q.entry)
              entries.append(toPy(e));
            out[py::str(toPy(q.name))] = entries;
            }
          return out;
          },
        "All journal topics and their entries.");

  m.def("announce",
        [](const std::string& text, float duration, int x, int y) {
          auto& font = Resources::font(1.0f);
          Gothic::inst().onPrintScreen(toEngine(text),
                                       x, y,
                                       static_cast<int>(duration),
                                       font);
          },
        py::arg("text"),
        py::arg("duration") = 3.0f,
        py::arg("x")        = 2,
        py::arg("y")        = 4,
        "Show a transient on-screen message for `duration` seconds. "
        "Default position is top-left. Great for tick callbacks that "
        "want to surface something to the player.");

  m.def("reload",
        [](const std::string& name) {
          py::module_ sys        = py::module_::import("sys");
          py::dict    modules    = sys.attr("modules");
          if(!modules.contains(py::str(name)))
            throw std::runtime_error("module not loaded: " + name);
          py::module_ importlib  = py::module_::import("importlib");
          return importlib.attr("reload")(modules[py::str(name)]);
          },
        py::arg("name"),
        "Reload a previously-imported module from disk "
        "(shorthand for importlib.reload).");

  // ---- gothic.daedalus: bridge to the live Daedalus VM ---------------------
  // Instead of re-implementing each Daedalus extern as a native binding, we
  // expose a single call/get/set gateway. Python gains immediate access to
  // *every* engine extern and every shipped game script function by name.
  py::module_ daedalus = m.def_submodule(
      "daedalus",
      "Bridge to the live Daedalus VM. Invoke script functions and read or "
      "write global symbols by name.");

  daedalus.def(
      "call",
      [](const std::string& name, py::args args) -> py::object {
        auto& vm  = requireWorld()->script().getVm();
        auto* sym = vm.find_symbol_by_name(name);
        if(sym == nullptr)
          throw std::runtime_error("Daedalus symbol not found: " + name);

        for(auto handle : args) {
          py::object v = py::reinterpret_borrow<py::object>(handle);
          // PyPlayer / PyNpc must be checked before bool/int/float because
          // pybind-bound classes can look like int-ish to duck-typed checks.
          if(py::isinstance<PyPlayer>(v)) {
            auto* p = Gothic::inst().player();
            if(p == nullptr)
              throw std::runtime_error(
                  "no active player to pass as Daedalus instance");
            vm.push_instance(
                std::static_pointer_cast<zenkit::DaedalusInstance>(
                    p->handlePtr()));
            }
          else if(py::isinstance<PyNpc>(v)) {
            auto pyn = py::cast<PyNpc>(v);
            Npc* n   = pyn.locate() ? pyn.ptr : nullptr;
            if(n == nullptr)
              throw std::runtime_error("npc no longer exists");
            vm.push_instance(
                std::static_pointer_cast<zenkit::DaedalusInstance>(
                    n->handlePtr()));
            }
          else if(py::isinstance<py::bool_>(v))
            vm.push_int(py::cast<bool>(v) ? 1 : 0);
          else if(py::isinstance<py::int_>(v))
            vm.push_int(py::cast<int32_t>(v));
          else if(py::isinstance<py::float_>(v))
            vm.push_float(py::cast<float>(v));
          else if(py::isinstance<py::str>(v))
            vm.push_string(toEngine(py::cast<std::string>(v)));
          else
            throw std::runtime_error(
                "unsupported Daedalus argument type; "
                "supported: int, float, bool, str, gothic.Player, gothic.Npc");
          }

        vm.unsafe_call(sym);

        if(!sym->has_return())
          return py::none();
        switch(sym->rtype()) {
          case zenkit::DaedalusDataType::INT:    return py::cast(vm.pop_int());
          case zenkit::DaedalusDataType::FLOAT:  return py::cast(vm.pop_float());
          case zenkit::DaedalusDataType::STRING: return py::cast(toPy(vm.pop_string()));
          default:                               return py::none();
          }
        },
      "Call a Daedalus function by name. Args must be int, float, bool or "
      "str. Return value (if any) comes back as the matching Python type.");

  daedalus.def(
      "get",
      [](const std::string& name, uint16_t index) -> py::object {
        auto& vm  = requireWorld()->script().getVm();
        auto* sym = vm.find_symbol_by_name(name);
        if(sym == nullptr)
          throw std::runtime_error("Daedalus symbol not found: " + name);
        switch(sym->type()) {
          case zenkit::DaedalusDataType::INT:
            return py::cast(sym->get_int(index));
          case zenkit::DaedalusDataType::FLOAT:
            return py::cast(sym->get_float(index));
          case zenkit::DaedalusDataType::STRING:
            return py::cast(toPy(sym->get_string(index)));
          case zenkit::DaedalusDataType::INSTANCE: {
            auto inst = sym->get_instance();
            return inst ? py::cast(static_cast<int>(inst->symbol_index()))
                        : py::none();
            }
          default:
            return py::none();
          }
        },
      py::arg("name"),
      py::arg("index") = uint16_t{0},
      "Read a Daedalus global or instance variable by name. Returns int, "
      "float or str; INSTANCE variables come back as the underlying symbol "
      "index, None if unset.");

  daedalus.def(
      "symbols",
      [](py::object pattern, py::object kind) -> py::list {
        auto&       vm  = requireWorld()->script().getVm();
        std::string pat;
        if(!pattern.is_none())
          pat = py::cast<std::string>(pattern);
        std::string k;
        if(!kind.is_none())
          k = py::cast<std::string>(kind);

        auto keep = [&](const zenkit::DaedalusSymbol& sym) -> bool {
          if(!pat.empty()) {
            // case-insensitive substring
            std::string n = sym.name();
            std::string P = pat;
            for(auto& c : n) c = char(std::tolower(uint8_t(c)));
            for(auto& c : P) c = char(std::tolower(uint8_t(c)));
            if(n.find(P) == std::string::npos)
              return false;
            }
          if(!k.empty()) {
            if(k == "extern"  && !sym.is_external())              return false;
            if(k == "func")
              return sym.type() == zenkit::DaedalusDataType::FUNCTION;
            if(k == "var") {
              auto t = sym.type();
              return t == zenkit::DaedalusDataType::INT   ||
                     t == zenkit::DaedalusDataType::FLOAT ||
                     t == zenkit::DaedalusDataType::STRING;
              }
            }
          return true;
          };

        py::list out;
        for(auto& sym : vm.symbols()) {
          if(!keep(sym))
            continue;
          py::dict d;
          d["name"]     = sym.name();
          d["type"]     = static_cast<int>(sym.type());
          d["rtype"]    = static_cast<int>(sym.rtype());
          d["count"]    = sym.count();
          d["external"] = sym.is_external();
          d["has_return"] = sym.has_return();
          out.append(d);
          }
        return out;
        },
      py::arg("pattern") = py::none(),
      py::arg("kind")    = py::none(),
      "Enumerate Daedalus symbols. Optional case-insensitive substring "
      "`pattern`; optional `kind` in {'extern', 'func', 'var'}.");

  daedalus.def(
      "set",
      [](const std::string& name, py::object value) {
        auto& vm  = requireWorld()->script().getVm();
        auto* sym = vm.find_symbol_by_name(name);
        if(sym == nullptr)
          throw std::runtime_error("Daedalus symbol not found: " + name);
        switch(sym->type()) {
          case zenkit::DaedalusDataType::INT:
            sym->set_int(py::cast<int32_t>(value));
            break;
          case zenkit::DaedalusDataType::FLOAT:
            sym->set_float(py::cast<float>(value));
            break;
          case zenkit::DaedalusDataType::STRING:
            sym->set_string(toEngine(py::cast<std::string>(value)));
            break;
          default:
            throw std::runtime_error(
                "Daedalus set(): only INT, FLOAT, STRING are writable");
          }
        },
      py::arg("name"),
      py::arg("value"),
      "Write a Daedalus global variable by name. Only INT, FLOAT and STRING "
      "variables are writable from here.");
  }

void pybindingsLinkAnchor() {}
