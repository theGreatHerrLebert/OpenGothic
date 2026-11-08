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

    void                     onWorldLoading() { ++worldGen; }

    // Calls the Python callbacks in gothic.<listName> with `arg`.
    void                     notify(const char* listName, std::string_view arg);
    uint64_t                 worldGeneration() const { return worldGen; }

  private:
    uint64_t worldGen = 0;
    PythonVM();
    ~PythonVM();
    PythonVM(const PythonVM&) = delete;
    PythonVM& operator=(const PythonVM&) = delete;

    struct Impl;
    std::unique_ptr<Impl> impl;
  };
