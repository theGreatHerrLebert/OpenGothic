#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

class PythonVM final {
  public:
    struct EvalResult {
      bool        ok    = false;
      std::string output;
      std::string error;
      };

    static PythonVM& inst();

    void                     init();
    void                     shutdown();
    EvalResult               eval(std::string_view source);
    std::vector<std::string> complete(std::string_view fragment);

    // Invoked by World::tick(dt). Dispatches to any callbacks registered
    // from Python via gothic.on_tick(fn). No-op if the interpreter hasn't
    // been initialized yet.
    void                     tick(uint64_t dt);

  private:
    PythonVM();
    ~PythonVM();
    PythonVM(const PythonVM&) = delete;
    PythonVM& operator=(const PythonVM&) = delete;

    struct Impl;
    std::unique_ptr<Impl> impl;
  };
