#include <pybind11/embed.h>
#include <pybind11/stl.h>

#include "gothic.h"
#include "game/constants.h"
#include "game/gamesession.h"
#include "game/gametime.h"
#include "world/world.h"
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
struct PyNpc {
  uint32_t id = 0;

  Npc* fetch() const {
    auto* w = requireWorld();
    auto* n = w->npcById(id);
    if(n == nullptr)
      throw std::runtime_error("npc no longer exists");
    return n;
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
                    id, std::string(n->displayName()).c_str());
      return buf;
      }
    catch(const std::exception&) {
      char buf[64];
      std::snprintf(buf, sizeof(buf), "<gothic.Npc id=%u stale>", id);
      return buf;
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
      if(w->npcById(i) != nullptr) {
        PyNpc item;
        item.id = i;
        out.append(item);
        }
      }
    return out;
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
      .def("__repr__", &PyPlayer::repr);

  py::class_<PyNpc>(m, "Npc")
      .def_readonly("id",                 &PyNpc::id)
      .def_property_readonly("position",  &PyNpc::position)
      .def_property_readonly("name",      &PyNpc::name)
      .def_property_readonly("hp",        &PyNpc::hp)
      .def_property_readonly("hp_max",    &PyNpc::hpMax)
      .def_property_readonly("alive",     &PyNpc::alive)
      .def("__repr__", &PyNpc::repr);

  py::class_<PyWorld>(m, "World")
      .def_property_readonly("time",       &PyWorld::time)
      .def_property_readonly("day",        &PyWorld::day)
      .def_property_readonly("tick_count", &PyWorld::tickCount)
      .def_property_readonly("npc_count",  &PyWorld::npcCount)
      .def_property_readonly("npcs",       &PyWorld::npcs)
      .def("set_time", &PyWorld::setTime, py::arg("hour"), py::arg("minute"))
      .def("__repr__", &PyWorld::repr);

  m.attr("player") = PyPlayer{};
  m.attr("world")  = PyWorld{};

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
  }
