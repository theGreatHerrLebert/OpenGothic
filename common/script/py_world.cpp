#include "pybindings_common.h"

#include <algorithm>
#include <cmath>

#include "script/pythonvm.h"
#include "world/aiqueue.h"
#include "graphics/effect.h"
#include "graphics/visualfx.h"
#include "world/objects/interactive.h"

namespace py = pybind11;

namespace PyBindings {

namespace {

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

} // anonymous namespace

void bindWorld(py::module_& m) {
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
               d["target_name"] = r.targetName;
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
      .def("shelter_points",
           [](const PyWorld&, float x, float y, float z, float radius, std::vector<std::string> taken) {
             // Covered waypoints near a point, nearest first: a roof over them (the roof map, as for snow), not
             // locked, nobody standing on them, not taken by someone else seeking shelter. Bounded to radius.
             auto* w    = requireWorld();
             auto* view = w->view();
             py::list out;
             if(view==nullptr)
               return out;
             const Tempest::Vec3 at(x, y, z);
             std::vector<Tempest::Vec3> people;
             for(uint32_t i=0; i<w->npcCount(); ++i)
               if(auto* o = w->npcById(i); o!=nullptr && (o->position()-at).length()<radius+300.f)
                 people.push_back(o->position());
             std::vector<std::pair<float, const WayPoint*>> found;
             w->findWayPoint(at, [&](const WayPoint& wp) {
               const auto p = wp.position();
               const float d = (p-at).length();
               if(d>radius || wp.isLocked())
                 return false;
               if(view->weatherRoofAt(p.x, p.z) < p.y + 250.f)
                 return false;
               for(auto& o:people) {
                 const float ox = o.x-p.x, oz = o.z-p.z;
                 if(ox*ox + oz*oz < 120.f*120.f)
                   return false;
                 }
               if(std::find(taken.begin(), taken.end(), wp.name)!=taken.end())
                 return false;
               found.emplace_back(d, &wp);
               return false;   // keep looking: collect them all within the radius
               });
             std::sort(found.begin(), found.end(), [](auto& a, auto& b) { return a.first<b.first; });
             for(size_t i=0; i<found.size() && i<8; ++i) {
               auto p = found[i].second->position();
               out.append(py::make_tuple(found[i].second->name, p.x, p.y, p.z));
               }
             return out;
             },
           py::arg("x"), py::arg("y"), py::arg("z"), py::arg("radius") = 2000.f,
           py::arg("taken") = std::vector<std::string>{},
           "Up to 8 covered, free waypoints within radius of a point, nearest first: (name, x, y, z).")
      .def("play_effect",
           [](const PyWorld&, const std::string& name, float x, float y, float z, float seconds) {
             // as Wld_PlayEffect, at a point: the game's own spell effects carry their light and sound
             auto* w   = requireWorld();
             auto* vfx = Gothic::inst().loadVisualFx(name);
             if(vfx==nullptr)
               return false;
             Effect e(*vfx, *w, Tempest::Vec3(x, y, z));
             e.setPhysicsDisable();   // only its light, look and sound: a spell's collision would deal damage and
             e.setActive(true);       // blame someone (docs/plan-weather.md, Fire rain round 2)
             w->runEffect(std::move(e), uint64_t(std::clamp(seconds, 0.f, 600.f)*1000.f));
             return true;
             },
           py::arg("name"), py::arg("x"), py::arg("y"), py::arg("z"), py::arg("seconds") = 0.f,
           "Play one of the game's visual effects (a VFX instance such as SPELLFX_FIRESTORM_COLLIDE) at a point (cm). "
           "seconds bounds how long it runs (0: as long as the effect lasts by itself); it is not saved. "
           "False if there is no such effect.")
      .def("stop_effect",
           [](const PyWorld&, const std::string& name) {
             auto* vfx = Gothic::inst().loadVisualFx(name);
             if(vfx!=nullptr)
               requireWorld()->stopEffect(*vfx);
             },
           py::arg("name"), "Stop every running instance of a visual effect, as Wld_StopEffect.")
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
  }

} // namespace PyBindings
