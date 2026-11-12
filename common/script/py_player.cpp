#include "pybindings_common.h"

#include "world/aiqueue.h"
#include "world/objects/interactive.h"

namespace py = pybind11;

namespace PyBindings {

void bindPlayer(py::module_& m) {
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
  }

} // namespace PyBindings
