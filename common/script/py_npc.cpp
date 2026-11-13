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
      .def("item_count", &PyNpc::itemCount, py::arg("instance"), "How many of this item the NPC carries.")
      .def("remove_item", &PyNpc::removeItem, py::arg("instance"), py::arg("count") = 1,
           "Take items out of the NPC's inventory.")
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
      .def_property_readonly("state",
           [](const PyNpc& self) -> py::object {
             auto fn = self.fetch()->stateFunction();
             if(!fn.isValid())
               return py::none();
             auto* sym = requireWorld()->script().getVm().find_symbol_by_index(uint32_t(fn.ptr));
             return sym==nullptr ? py::object(py::none()) : py::object(py::str(sym->name()));
             },
           "The ZS_ state the NPC is in now, or None.")
      .def_property_readonly("key",
           [](const PyNpc& self) { return uint64_t(reinterpret_cast<uintptr_t>(self.fetch())); },
           "Who he is while he lives in this world: stable, unlike id, which is his place in a list that is resorted.")
      .def_property_readonly("ai_queue", [](const PyNpc& self) { return self.fetch()->aiQueueSize(); },
           "How many actions are queued for the NPC: 0 while his state runs freely.")
      .def_property_readonly("routine_held", [](const PyNpc& self) { return self.fetch()->isRoutineHeld(); },
           "True while a story lends him a routine of its own.")
      .def("shelter_at",
           [](const PyNpc& self, const std::string& waypoint, float wait, bool run) {
             // Seeking shelter (docs/plan-weather.md): a few queued actions, never his routine. While they run his
             // state waits; a fight, a talk or any perception that starts a state clears them as it always does, and
             // when they are done his own routine walks him back.
             auto* n  = self.fetch();
             auto* wp = requireWorld()->findPoint(waypoint, false);
             if(wp==nullptr)
               return false;
             if(run)
               n->aiPush(AiQueue::aiSetWalkMode(WalkBit::WM_Run));
             n->aiPush(AiQueue::aiGoToPoint(*wp));
             n->aiPush(AiQueue::aiAlignToWp());
             n->aiPush(AiQueue::aiWait(uint64_t(std::clamp(wait, 1.f, 300.f)*1000.f)));
             return true;
             },
           py::arg("waypoint"), py::arg("wait") = 25.f, py::arg("run") = true,
           "Send him under cover: run to the waypoint, face its way and wait there wait seconds; then his own "
           "routine takes him back, unless more waiting is queued with wait_more.")
      .def("wait_more", [](const PyNpc& self, float wait) {
             self.fetch()->aiPush(AiQueue::aiWait(uint64_t(std::clamp(wait, 1.f, 300.f)*1000.f)));
             },
           py::arg("wait"), "Queue more waiting where he stands.")
      .def("can_reach",
           [](const PyNpc& self, const std::string& waypoint) {
             auto* w  = requireWorld();
             auto* wp = w->findPoint(waypoint, false);
             if(wp==nullptr)
               return false;
             auto* n = self.fetch();
             const auto d = n->position() - wp->position();
             return d.length()<300.f || w->wayTo(*n, *wp).first()!=nullptr;
             },
           py::arg("waypoint"), "True if the waynet leads him there (or he is nearly there).")
      .def("hurt",
           [](const PyNpc& self, int amount) {
             Npc* p = self.fetch();
             // a wound, never death: at least 1 hp stays; god mode, a cutscene and the immortal take none (the engine)
             const int32_t cur  = p->attribute(ATR_HITPOINTS);
             const int32_t loss = std::min(std::max(amount, 0), cur - 1);
             if(loss<=0 || p->isDead() || p->isUnconscious())
               return 0;
             p->changeAttribute(ATR_HITPOINTS, -loss, false);
             return cur - p->attribute(ATR_HITPOINTS);
             },
           py::arg("amount"),
           "Wound by up to amount hp, never below 1 (weather, not combat: nobody is blamed). Returns the hp taken.")
      .def("__repr__", &PyNpc::repr);

  py::class_<PyItem>(m, "Item")
      .def("make_quest", &PyItem::makeQuest, py::arg("description"), py::arg("lines"),
           "Make this a quest item: no equipping, no sale value, with story text.")
      .def("remove", &PyItem::remove);
  }

} // namespace PyBindings
