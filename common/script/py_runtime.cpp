#include "pybindings_common.h"

#include "resources.h"

namespace py = pybind11;

namespace PyBindings {

void bindRuntime(py::module_& m) {
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
  }

} // namespace PyBindings
