#include "pybindings_common.h"

namespace py = pybind11;

namespace PyBindings {

void bindDaedalus(py::module_& m) {
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
      [](const std::string& name, py::args args, py::kwargs kwargs) -> py::object {
        auto& vm  = requireWorld()->script().getVm();
        auto* sym = vm.find_symbol_by_name(name);
        if(sym == nullptr)
          throw std::runtime_error("Daedalus symbol not found: " + name);

        // self= and other= set the script globals for this one call, as a dialogue or perception would: functions
        // such as B_Attack start AI states that read them. Both are put back afterwards.
        auto instanceOf = [](py::handle v) -> std::shared_ptr<zenkit::DaedalusInstance> {
          if(py::isinstance<PyPlayer>(v)) {
            auto* p = Gothic::inst().player();
            if(p == nullptr)
              throw std::runtime_error("no active player to pass as Daedalus instance");
            return std::static_pointer_cast<zenkit::DaedalusInstance>(p->handlePtr());
            }
          auto pyn = py::cast<PyNpc>(v);
          Npc* n   = pyn.locate() ? pyn.ptr : nullptr;
          if(n == nullptr)
            throw std::runtime_error("npc no longer exists");
          return std::static_pointer_cast<zenkit::DaedalusInstance>(n->handlePtr());
          };
        struct Restore {
          zenkit::DaedalusSymbol*                   sym = nullptr;
          std::shared_ptr<zenkit::DaedalusInstance> prev;
          ~Restore() { if(sym != nullptr) sym->set_instance(prev); }
          } restoreSelf, restoreOther;
        if(kwargs.contains("self")) {
          auto inst = instanceOf(kwargs["self"]);
          restoreSelf.sym = vm.global_self(); restoreSelf.prev = restoreSelf.sym->get_instance();
          restoreSelf.sym->set_instance(inst);
          }
        if(kwargs.contains("other")) {
          auto inst = instanceOf(kwargs["other"]);
          restoreOther.sym = vm.global_other(); restoreOther.prev = restoreOther.sym->get_instance();
          restoreOther.sym->set_instance(inst);
          }

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
      "Call a Daedalus function by name. Args must be int, float, bool, str, "
      "gothic.Player or gothic.Npc; self= and other= set those globals for the "
      "call. Return value (if any) comes back as the matching Python type.");

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

} // namespace PyBindings
