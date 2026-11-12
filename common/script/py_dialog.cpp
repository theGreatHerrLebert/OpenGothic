#include "pybindings_common.h"

#include <algorithm>
#include <utility>

#include "ui/dialogmenu.h"

namespace py = pybind11;

namespace PyBindings {

namespace {

DialogMenu& requireDialog() {
  auto* d = Gothic::inst().dialogMenu();
  if(d==nullptr)
    throw std::runtime_error("dialogue UI is not available");
  return *d;
  }

} // anonymous namespace

void bindDialog(py::module_& m) {
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
  }

} // namespace PyBindings
