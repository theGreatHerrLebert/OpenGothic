#pragma once

#include <vector>

#include <Tempest/Point>
#include <cstdint>

class Npc;

class PerceptionMsg final {
  public:
    std::vector<Npc*> seenBy;
    int32_t       what=0;
    Tempest::Vec3 pos;
    Npc*          self  =nullptr;
    Npc*          other =nullptr;
    Npc*          victim=nullptr;
    size_t        item  =size_t(-1);
  };
