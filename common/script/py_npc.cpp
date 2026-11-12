#include "pybindings_common.h"

namespace py = pybind11;

namespace PyBindings {

void bindNpc(py::module_& m) {
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
      .def("attribute", &PyNpc::attribute, py::arg("name"),
           "hp, hp_max, mana, mana_max, strength or dexterity.")
      .def("set_attribute", &PyNpc::setAttribute, py::arg("name"), py::arg("value"))
      .def_property_readonly("body_mesh", &PyNpc::bodyMesh, "The body mesh the game set (Wol_Body for a wolf).")
      .def("add_item", &PyNpc::addItem, py::arg("instance"), py::arg("count") = 1,
           "Put items into the NPC's inventory, to be looted.")
      .def_property("level", &PyNpc::level, &PyNpc::setLevel,
                    "The NPC's level; the hero's experience for a kill follows it.")
      .def("set_body_texture", &PyNpc::setBodyTexture, py::arg("variant"),
           "Use body texture variant n (the mesh's _V0 texture becomes _V<n>).")
      .def("set_scale", &PyNpc::setScale, py::arg("x"), py::arg("y") = 0.f, py::arg("z") = 0.f,
           "Scale the NPC; one number scales evenly. Kept in saves.")
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
  }

} // namespace PyBindings
