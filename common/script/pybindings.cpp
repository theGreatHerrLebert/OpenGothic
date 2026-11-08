#include <pybind11/embed.h>
#include <pybind11/stl.h>

#include "gothic.h"
#include "game/constants.h"
#include "game/gamesession.h"
#include "game/gametime.h"
#include "resources.h"
#include "ui/dialogmenu.h"
#include "world/world.h"
#include "world/objects/item.h"
#include "world/objects/npc.h"

namespace py = pybind11;

namespace {

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
  std::string name() const  { return std::string(requirePlayer()->displayName()); }

  py::list items() const {
    auto*    p  = requirePlayer();
    py::list out;
    auto     it = p->inventory().iterator(Inventory::T_Inventory);
    while(it.isValid()) {
      py::dict d;
      d["name"]     = std::string(it->displayName());
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
                  std::string(p->displayName()).c_str(),
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

  void setName(const std::string& v) { fetch()->handle().name[0] = v; }

  // Keeps the routine and perception intact: removing them makes an NPC
  // untalkable.
  void stop() {
    auto* n = fetch();
    n->clearAiQueue();
    n->stopWalking();
    }

  py::tuple position() const {
    auto  v = fetch()->position();
    return py::make_tuple(v.x, v.y, v.z);
    }
  std::string name() const { return std::string(fetch()->displayName()); }
  int  hp() const          { return fetch()->attribute(ATR_HITPOINTS); }
  int  hpMax() const       { return fetch()->attribute(ATR_HITPOINTSMAX); }
  bool alive() const {
    auto* n = fetch();
    return !n->isDead() && !n->isUnconscious();
    }
  std::string repr() const {
    try {
      auto* n = fetch();
      char buf[160];
      std::snprintf(buf, sizeof(buf), "<gothic.Npc id=%u name=%.64s>",
                    hint, std::string(n->displayName()).c_str());
      return buf;
      }
    catch(const std::exception&) {
      return "<gothic.Npc stale>";
      }
    }
  };

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
    auto*       w    = requireWorld();
    auto&       sc   = w->script();
    std::string name = instance;
    for(auto& c:name)
      c = char(std::toupper(uint8_t(c)));

    const size_t id = sc.findSymbolIndex(name);
    auto*        sym = id==size_t(-1) ? nullptr : sc.findSymbol(id);
    if(sym==nullptr || sym->parent()==uint32_t(-1) ||
       sym->type()!=zenkit::DaedalusDataType::INSTANCE || sym->address()==0)
      throw std::invalid_argument("not an NPC instance: " + instance);
    const auto* cls = sym;
    while(cls!=nullptr && cls->parent()!=uint32_t(-1))
      cls = sc.findSymbol(cls->parent());
    if(cls==nullptr || cls->name()!="C_NPC")
      throw std::invalid_argument("not an NPC instance: " + instance);

    Npc* n = nullptr;
    if(!waypoint.empty()) {
      n = w->addNpc(id, std::string_view(waypoint));
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
      .def_property_readonly("items",    &PyPlayer::items,
                             "List of dicts {name, count, equipped} for "
                             "every item in the player's inventory.")
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
      .def("stop", &PyNpc::stop,
           "Clear queued AI actions and stop walking. Keeps the NPC talkable.")
      .def_property_readonly("position",  &PyNpc::position)
      .def_property_readonly("name",      &PyNpc::name)
      .def_property_readonly("hp",        &PyNpc::hp)
      .def_property_readonly("hp_max",    &PyNpc::hpMax)
      .def_property_readonly("alive",     &PyNpc::alive)
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

  py::class_<PyWorld>(m, "World")
      .def_property_readonly("time",       &PyWorld::time)
      .def_property_readonly("day",        &PyWorld::day)
      .def_property_readonly("tick_count", &PyWorld::tickCount)
      .def_property_readonly("npc_count",  &PyWorld::npcCount)
      .def_property_readonly("npcs",       &PyWorld::npcs)
      .def("set_time", &PyWorld::setTime, py::arg("hour"), py::arg("minute"))
      .def("spawn", &PyWorld::spawn, py::arg("instance"), py::arg("waypoint") = "",
           "Create an NPC by Daedalus instance name, near the player unless a "
           "waypoint is given. Main-thread only.")
      .def("find_npc", &PyWorld::findNpc, py::arg("instance"), py::arg("nth") = 0,
           "Find a live NPC by Daedalus instance name, or None.")
      .def("__repr__", &PyWorld::repr);

  m.attr("player") = PyPlayer{};
  m.attr("world")  = PyWorld{};

  py::module_ dialog = m.def_submodule(
      "dialog", "Drive the native dialogue UI for one bound NPC from Python.");
  dialog.def("bind",
             [](const PyNpc& npc) { requireDialog().agentBind(npc.fetch()); },
             py::arg("npc"),
             "Talking to this NPC opens an empty Python-driven dialogue.");
  dialog.def("unbind", []() { requireDialog().agentBind(nullptr); });
  dialog.def("is_open", []() { return requireDialog().agentActive(); });
  dialog.def("just_opened", []() { return requireDialog().agentTakeOpened(); },
             "True once after the player starts the dialogue.");
  dialog.def("busy", []() { return requireDialog().agentBusy(); },
             "True while a line is still being shown.");
  dialog.def("say",
             [](const std::string& text, bool player, int ms) {
               if(ms<=0)
                 ms = std::max(2000, int(text.size())*70);
               return requireDialog().agentSay(text, player, uint64_t(ms));
               },
             py::arg("text"), py::arg("player") = false, py::arg("ms") = 0,
             "Show a subtitle line. Returns False if the UI is busy; retry "
             "on a later tick.");
  dialog.def("set_choices",
             [](const std::vector<std::string>& c) { requireDialog().agentSetChoices(c); },
             py::arg("choices"));
  dialog.def("poll_selection",
             []() -> py::object {
               const int s = requireDialog().agentTakeSelection();
               return s<0 ? py::none() : py::cast(s);
               },
             "Index of the choice just picked, or None. Reports once.");
  dialog.def("close", []() { requireDialog().agentClose(); });

  // Per-tick callback registry — consumed by PythonVM::tick() which is
  // invoked from World::tick().
  m.attr("_tick_callbacks") = py::list();

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

  m.def("announce",
        [](const std::string& text, float duration, int x, int y) {
          auto& font = Resources::font(1.0f);
          Gothic::inst().onPrintScreen(text,
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
            vm.push_string(py::cast<std::string>(v));
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
          case zenkit::DaedalusDataType::STRING: return py::cast(vm.pop_string());
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
            return py::cast(std::string(sym->get_string(index)));
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
            sym->set_string(py::cast<std::string>(value));
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
