#pragma once

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

  private:
    PythonVM();
    ~PythonVM();
    PythonVM(const PythonVM&) = delete;
    PythonVM& operator=(const PythonVM&) = delete;

    struct Impl;
    std::unique_ptr<Impl> impl;
  };
