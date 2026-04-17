#include "pythonvm.h"

#include <pybind11/embed.h>
#include <pybind11/pybind11.h>

#include <Tempest/Log>

namespace py = pybind11;

struct PythonVM::Impl {
  std::unique_ptr<py::scoped_interpreter> interp;
  py::dict                                globals;
  py::object                              capture;  // io.StringIO bound to sys.stdout/stderr
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
    impl->capture = py::module_::import("sys").attr("stdout");

    // Persistent globals so `x = 1` in one `py` line is visible in the next.
    impl->globals = py::dict();
    impl->globals["__builtins__"] = py::module_::import("builtins");
    impl->globals["gothic"]       = py::module_::import("gothic");

    impl->ready = true;
    Tempest::Log::i("[python] interpreter initialized");
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
  impl->globals.release();
  impl->capture.release();
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
    py::object lines = tb.attr("format_exception")(
        py::reinterpret_steal<py::object>(et ? et : Py_None),
        py::reinterpret_steal<py::object>(ev ? ev : Py_None),
        py::reinterpret_steal<py::object>(etb ? etb : Py_None));
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
          PyEval_EvalCode(code.ptr(), impl->globals.ptr(), impl->globals.ptr()));
      if(!result)
        throw py::error_already_set();
      haveResult = true;
      }
    catch(py::error_already_set& e) {
      if(e.matches(PyExc_SyntaxError)) {
        // Fall back to statement mode for `import x`, assignments, loops...
        PyErr_Clear();
        py::object code = py::reinterpret_steal<py::object>(
            Py_CompileString(src.c_str(), "<marvin>", Py_file_input));
        if(!code)
          throw py::error_already_set();
        py::object r = py::reinterpret_steal<py::object>(
            PyEval_EvalCode(code.ptr(), impl->globals.ptr(), impl->globals.ptr()));
        if(!r)
          throw py::error_already_set();
        }
      else {
        throw;
        }
      }

    res.output = drainCapture(impl->capture);
    if(haveResult && !result.is_none()) {
      if(!res.output.empty() && res.output.back()!='\n')
        res.output += '\n';
      res.output += py::cast<std::string>(py::repr(result));
      }
    res.ok = true;
    }
  catch(py::error_already_set&) {
    res.error  = formatException();
    // Also include anything the failed code had already written to stdout.
    std::string partial = drainCapture(impl->capture);
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
