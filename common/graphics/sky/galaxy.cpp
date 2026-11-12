#include "galaxy.h"

#include <Tempest/Pixmap>
#include <Tempest/Log>

#include "resources.h"

using namespace Tempest;

Galaxy& Galaxy::inst() {
  static Galaxy g;
  return g;
  }

bool Galaxy::load(size_t slot, std::string_view path) {
  if(slot>=Slots)
    return false;
  Pixmap pm;
  try {
    pm = Pixmap(path);
    }
  catch(...) {
    Log::e("galaxy: cannot read \"", std::string(path), "\"");
    return false;
    }
  if(pm.isEmpty())
    return false;
  auto next = Resources::device().texture(pm, true);
  Resources::recycle(std::move(tex[slot]));   // a frame in flight may still sample the old one
  tex[slot] = std::move(next);
  return true;
  }

void Galaxy::clear(size_t slot) {
  if(slot<Slots)
    Resources::recycle(std::move(tex[slot]));
  }

const Texture2d& Galaxy::texture(size_t slot) const {
  if(slot<Slots && !tex[slot].isEmpty())
    return tex[slot];
  return Resources::fallbackBlack();
  }
