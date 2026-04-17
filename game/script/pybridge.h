#pragma once

#include <filesystem>
#include <string>

// Filesystem REPL bridge for OpenGothic's embedded Python.
//
// When the env var OPENGOTHIC_PY_BRIDGE=1 is set at launch, the engine
// polls a per-user directory under /tmp each tick. Files placed in
// <root>/in/<id>.py are executed against the live PythonVM on the main
// thread, and the result (captured stdout + repr OR traceback) is written
// to <root>/out/<id>.out. This lets external tooling drive the running
// game as if it were a remote REPL — same semantics as typing into Marvin,
// just without having to touch the keyboard.
//
// THREADING: poll() is called from PythonVM::tick(), which runs from
// World::tick() on the main thread. All eval() invocations therefore
// happen on the main thread, same as Marvin `py ...`.
class PyBridge final {
  public:
    static PyBridge& inst();

    // Reads OPENGOTHIC_PY_BRIDGE; if set, creates the directory layout
    // under /tmp/opengothic-$USER-bridge/{in,processing,out} and logs
    // a loud warning that arbitrary Python will run.
    void init();

    // Walks <root>/in/*.py, atomically relocates each to processing/,
    // execs via PythonVM, and writes the response to out/. No-op when
    // the bridge is disabled. Intended to be called from
    // PythonVM::tick().
    void poll();

    bool enabled() const { return enabledFlag; }

  private:
    PyBridge() = default;

    void processOne(const std::filesystem::path& incoming);

    bool                  enabledFlag = false;
    std::filesystem::path root;
  };
