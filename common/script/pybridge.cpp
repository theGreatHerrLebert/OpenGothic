#include "pybridge.h"

#include "pythonvm.h"

#include <Tempest/Log>

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <system_error>

namespace fs = std::filesystem;

namespace {

std::string readAll(const fs::path& p) {
  std::ifstream f(p);
  if(!f)
    return {};
  std::stringstream ss;
  ss << f.rdbuf();
  return ss.str();
  }

// Atomic-on-POSIX write: write to <path>.tmp then rename to <path>.
bool writeAtomic(const fs::path& target, const std::string& contents) {
  fs::path tmp = target;
  tmp += ".tmp";
  {
    std::ofstream f(tmp, std::ios::binary | std::ios::trunc);
    if(!f)
      return false;
    f.write(contents.data(), static_cast<std::streamsize>(contents.size()));
    if(!f)
      return false;
    }
  std::error_code ec;
  fs::rename(tmp, target, ec);
  if(ec) {
    fs::remove(tmp, ec);
    return false;
    }
  return true;
  }

} // namespace

PyBridge& PyBridge::inst() {
  static PyBridge p;
  return p;
  }

void PyBridge::init() {
  const char* flag = std::getenv("OPENGOTHIC_PY_BRIDGE");
  if(flag == nullptr || flag[0]=='0' || flag[0]=='\0')
    return;

  // Honor OPENGOTHIC_PY_BRIDGE_DIR when set (matches scripts/pyeval), else
  // use /tmp/opengothic-$USER-bridge. Deliberately NOT std::filesystem::
  // temp_directory_path() — on macOS that resolves to a per-user sandbox
  // under /var/folders/... which is unpredictable to address from shell.
  const char* override_dir = std::getenv("OPENGOTHIC_PY_BRIDGE_DIR");
  if(override_dir != nullptr && override_dir[0] != '\0') {
    root = override_dir;
    }
  else {
    const char* user = std::getenv("USER");
    if(user == nullptr)
      user = "anon";
    root = fs::path("/tmp") / (std::string("opengothic-") + user + "-bridge");
    }

  std::error_code ec;
  fs::create_directories(root / "in",         ec);
  fs::create_directories(root / "processing", ec);
  fs::create_directories(root / "out",        ec);
  if(ec) {
    Tempest::Log::e("[pybridge] failed to create directory layout at ",
                    root.string().c_str(), ": ", ec.message().c_str());
    return;
    }

  enabledFlag = true;
  Tempest::Log::i("[pybridge] ENABLED — arbitrary Python will be executed from ",
                  root.string().c_str());
  Tempest::Log::i("[pybridge]   write to ", (root / "in").string().c_str(),
                  "/<id>.py, read reply from ",
                  (root / "out").string().c_str(), "/<id>.out");
  }

void PyBridge::poll() {
  if(!enabledFlag)
    return;

  std::error_code ec;
  auto in_dir = root / "in";
  if(!fs::exists(in_dir, ec))
    return;

  // Snapshot filenames first — moving entries during iteration is undefined.
  std::vector<fs::path> pending;
  for(auto& entry : fs::directory_iterator(in_dir, ec)) {
    if(ec)
      break;
    if(!entry.is_regular_file())
      continue;
    if(entry.path().extension() != ".py")
      continue;
    pending.push_back(entry.path());
    }

  for(auto& p : pending)
    processOne(p);
  }

void PyBridge::processOne(const fs::path& incoming) {
  const std::string stem = incoming.stem().string();
  fs::path working = root / "processing" / (stem + ".py");
  fs::path reply   = root / "out"        / (stem + ".out");

  std::error_code ec;
  fs::rename(incoming, working, ec);
  if(ec) {
    // Another tick might have grabbed it; skip.
    return;
    }

  std::string source = readAll(working);

  auto result = PythonVM::inst().eval(source);

  // Format: first line is status marker, rest is the payload. Keeps
  // shell-side parsing trivial while still reporting success/failure.
  std::string payload;
  if(result.ok) {
    payload  = "OK\n";
    payload += result.output;
    if(!payload.empty() && payload.back() != '\n')
      payload += '\n';
    }
  else {
    payload  = "ERR\n";
    if(!result.output.empty()) {
      payload += result.output;
      if(payload.back() != '\n')
        payload += '\n';
      }
    payload += result.error;
    if(!payload.empty() && payload.back() != '\n')
      payload += '\n';
    }

  if(!writeAtomic(reply, payload))
    Tempest::Log::e("[pybridge] failed to write reply ", reply.string().c_str());

  fs::remove(working, ec);
  }
