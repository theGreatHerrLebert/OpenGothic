#include "pythonvm.h"
#include "pybridge.h"

#include <pybind11/embed.h>
#include <pybind11/pybind11.h>

#include <Tempest/Log>

#include <optional>

namespace py = pybind11;

// py::dict and py::object invoke the Python C API at construction (PyDict_New
// etc.), so they must not be default-constructed before Py_Initialize has run.
// std::optional keeps the members dormant until init() populates them.
struct PythonVM::Impl {
  std::unique_ptr<py::scoped_interpreter> interp;
  std::optional<py::dict>                 globals;
  std::optional<py::object>               capture;
  bool                                    ready = false;
  };

PythonVM& PythonVM::inst() {
  static PythonVM vm;
  return vm;
  }

PythonVM::PythonVM() : impl(std::make_unique<Impl>()) {}
PythonVM::~PythonVM() { shutdown(); }

void PythonVM::init() {
  if(impl->ready)
    return;
  try {
    impl->interp = std::make_unique<py::scoped_interpreter>();

    // Install a StringIO-backed sink for sys.stdout / sys.stderr so REPL output
    // can be captured and pushed back through Marvin's print signal.
    py::exec(R"(
import sys, io
_gothic_capture = io.StringIO()
sys.stdout = _gothic_capture
sys.stderr = _gothic_capture
)");
    impl->capture.emplace(py::module_::import("sys").attr("stdout"));

    // Persistent globals so `x = 1` in one `py` line is visible in the next.
    impl->globals.emplace();
    (*impl->globals)["__builtins__"] = py::module_::import("builtins");
    (*impl->globals)["gothic"]       = py::module_::import("gothic");

    // Add $CWD/python to sys.path so user modules (e.g. python/tools.py) are
    // importable from the REPL: `py import tools; tools.foo()`.
    py::exec(R"(
import sys, pathlib
_gothic_scripts = pathlib.Path.cwd() / "python"
if _gothic_scripts.is_dir():
    _p = str(_gothic_scripts)
    if _p not in sys.path:
        sys.path.insert(0, _p)
)");

    impl->ready = true;
    Tempest::Log::i("[python] interpreter initialized");

    // Activates the OPENGOTHIC_PY_BRIDGE filesystem REPL if the env var is
    // set. No-op otherwise — must come after the interpreter is live so any
    // bridge requests are eval-ready.
    PyBridge::inst().init();

    // If $CWD/python/init.py exists, run it in the persistent globals so any
    // helpers the user defined there are visible to F2 immediately. Errors
    // here must not tear down the interpreter — log and move on.
    try {
      py::exec(R"(
import pathlib
_gothic_init = pathlib.Path.cwd() / "python" / "init.py"
if _gothic_init.is_file():
    with open(_gothic_init, "r") as _f:
        _src = _f.read()
    exec(compile(_src, str(_gothic_init), "exec"), globals())
    print(f"[python] loaded {_gothic_init}")
)", *impl->globals);
      // Drain anything init.py printed so it doesn't leak into the next
      // Marvin `py ...` output.
      try {
        py::str s = impl->capture->attr("getvalue")();
        std::string msg(py::cast<std::string_view>(s));
        if(!msg.empty())
          Tempest::Log::i(msg);
        impl->capture->attr("seek")(0);
        impl->capture->attr("truncate")(0);
        }
      catch(...) {}
      }
    catch(const std::exception& e) {
      Tempest::Log::e("[python] init.py failed: ", e.what());
      try {
        impl->capture->attr("seek")(0);
        impl->capture->attr("truncate")(0);
        }
      catch(...) {}
      }
    }
  catch(const std::exception& e) {
    Tempest::Log::e("[python] init failed: ", e.what());
    impl->interp.reset();
    impl->ready = false;
    }
  }

void PythonVM::shutdown() {
  if(!impl->ready)
    return;
  impl->globals.reset();
  impl->capture.reset();
  impl->interp.reset();
  impl->ready = false;
  }

static std::string drainCapture(py::object& capture) {
  std::string out;
  try {
    py::str s = capture.attr("getvalue")();
    out = std::string(py::cast<std::string_view>(s));
    capture.attr("seek")(0);
    capture.attr("truncate")(0);
    }
  catch(...) {}
  return out;
  }

static std::string formatException() {
  try {
    py::object tb = py::module_::import("traceback");
    py::object exc_type, exc_value, exc_tb;
    PyObject *et = nullptr, *ev = nullptr, *etb = nullptr;
    PyErr_Fetch(&et, &ev, &etb);
    PyErr_NormalizeException(&et, &ev, &etb);
    if(etb != nullptr)
      PyException_SetTraceback(ev, etb);
    // Never steal a ref on Py_None — it's a global singleton; stealing would
    // eventually decref it to 0 and corrupt the interpreter. Use py::none()
    // for the missing components, steal only the real ones.
    py::object oet  = et  ? py::reinterpret_steal<py::object>(et)  : py::none();
    py::object oev  = ev  ? py::reinterpret_steal<py::object>(ev)  : py::none();
    py::object oetb = etb ? py::reinterpret_steal<py::object>(etb) : py::none();
    py::object lines = tb.attr("format_exception")(oet, oev, oetb);
    std::string out;
    for(auto line : lines)
      out += py::cast<std::string>(line);
    return out;
    }
  catch(...) {
    return "<unable to format python exception>";
    }
  }

PythonVM::EvalResult PythonVM::eval(std::string_view source) {
  EvalResult res;
  if(!impl->ready) {
    res.error = "python interpreter not initialized";
    return res;
    }

  std::string src(source);
  // Strip trailing whitespace/newlines — compile() is sensitive to them.
  while(!src.empty() && (src.back()=='\n' || src.back()=='\r' || src.back()==' '))
    src.pop_back();
  if(src.empty()) {
    res.ok = true;
    return res;
    }

  PyObject* globals = impl->globals->ptr();
  try {
    py::object result;
    bool       haveResult = false;
    try {
      // Try expression mode first so a bare `1+1` returns 2.
      py::object code = py::reinterpret_steal<py::object>(
          Py_CompileString(src.c_str(), "<marvin>", Py_eval_input));
      if(!code)
        throw py::error_already_set();
      result = py::reinterpret_steal<py::object>(
          PyEval_EvalCode(code.ptr(), globals, globals));
      if(!result)
        throw py::error_already_set();
      haveResult = true;
      }
    catch(py::error_already_set& e) {
      if(!e.matches(PyExc_SyntaxError))
        throw;
      PyErr_Clear();

      // Fallback tier 1: Py_single_input — one logical line or a compound
      // statement. Auto-prints bare expressions via sys.displayhook, so
      // `import sys; sys.version` prints the version.
      py::object code = py::reinterpret_steal<py::object>(
          Py_CompileString(src.c_str(), "<marvin>", Py_single_input));
      if(!code) {
        // Fallback tier 2: Py_file_input — full multi-statement script.
        // Bare expressions are intentionally silent in this mode; caller
        // uses explicit print(...) if they want output. This is what
        // unblocks multi-line scripts sent via the filesystem bridge.
        PyErr_Clear();
        code = py::reinterpret_steal<py::object>(
            Py_CompileString(src.c_str(), "<marvin>", Py_file_input));
        if(!code)
          throw py::error_already_set();
        }
      py::object r = py::reinterpret_steal<py::object>(
          PyEval_EvalCode(code.ptr(), globals, globals));
      if(!r)
        throw py::error_already_set();
      }

    res.output = drainCapture(*impl->capture);
    if(haveResult && !result.is_none()) {
      if(!res.output.empty() && res.output.back()!='\n')
        res.output += '\n';
      res.output += py::cast<std::string>(py::repr(result));
      }
    res.ok = true;
    }
  catch(py::error_already_set& e) {
    // Restore the error into Python's state so traceback.format_exception
    // can read it. pybind11's error_already_set ctor consumes the error on
    // construction, so without restore() formatException() would see nothing.
    e.restore();
    res.error = formatException();
    if(res.error.empty() || res.error.find("NoneType") != std::string::npos)
      res.error = e.what();  // fallback to pybind's own formatting
    // Also include anything the failed code had already written to stdout.
    std::string partial = drainCapture(*impl->capture);
    if(!partial.empty()) {
      if(!res.output.empty() && res.output.back()!='\n')
        res.output += '\n';
      res.output += partial;
      }
    res.ok = false;
    }
  catch(const std::exception& e) {
    res.error = std::string("C++ exception: ") + e.what();
    res.ok    = false;
    }
  return res;
  }

void PythonVM::tick(uint64_t dt) {
  if(!impl->ready)
    return;
  // Drain any external bridge requests first, so a file-queued command
  // processes on the same tick it arrived.
  PyBridge::inst().poll();
  try {
    py::module_ gothic = py::module_::import("gothic");
    py::object  cbs    = gothic.attr("_tick_callbacks");
    const size_t n     = py::len(cbs);
    if(n == 0)
      return;
    for(size_t i = 0; i < n; ++i) {
      try {
        cbs[py::int_(i)](dt);
        }
      catch(py::error_already_set&) {
        // A broken tick callback must not tear down the game. Log and move on.
        Tempest::Log::e("[python] tick callback raised: ", formatException().c_str());
        }
      }
    // Anything tick callbacks printed accumulates in our captured stdout.
    // Route it to log.txt — the Marvin console isn't open during ticks.
    std::string out = drainCapture(*impl->capture);
    if(!out.empty()) {
      while(!out.empty() && (out.back()=='\n' || out.back()=='\r'))
        out.pop_back();
      if(!out.empty())
        Tempest::Log::i("[python] ", out.c_str());
      }
    }
  catch(const std::exception&) {
    // gothic module missing, etc. — swallow silently.
    }
  }

std::vector<std::string> PythonVM::complete(std::string_view fragment) {
  std::vector<std::string> out;
  if(!impl->ready)
    return out;
  try {
    py::object rlc       = py::module_::import("rlcompleter");
    py::object completer = rlc.attr("Completer")(*impl->globals);
    std::string text(fragment);
    for(int state = 0; state < 64; ++state) {
      py::object r = completer.attr("complete")(text, state);
      if(r.is_none())
        break;
      out.push_back(py::cast<std::string>(r));
      }
    // Drain any noise rlcompleter wrote to the captured stdout.
    try {
      impl->capture->attr("seek")(0);
      impl->capture->attr("truncate")(0);
      }
    catch(...) {}
    }
  catch(const std::exception&) {
    // Autocomplete failure shouldn't disrupt typing — swallow silently.
    }
  return out;
  }
