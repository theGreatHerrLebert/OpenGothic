#pragma once

#include <Tempest/StorageBuffer>
#include <Tempest/Vec>

#include <cstdint>
#include <vector>

#include "resources.h"

// Footprints in lying snow (docs/plan-weather.md): a square of ground around the hero, one byte per 12.5 cm cell, into
// which every step presses an oval; fresh snow fills them again. Kept on the CPU, uploaded to one buffer per frame in
// flight, and read by the G-buffer materials where they draw snow cover.
class SnowTrail final {
  public:
    static constexpr int   Size = 512;      // cells per side
    static constexpr float Cell = 12.5f;    // cm per cell: 64 m in all

    void init();   // a buffer for every frame in flight, so the materials always have one to read
    void tick(const Tempest::Vec3& hero, bool onGround, float cover, float snowfall, uint64_t tickCount, uint8_t fId);

    const Tempest::StorageBuffer& buffer(uint8_t fId) const { return ssbo[fId]; }
    // (min x, min z, 1/Cell, Size) in world cm; Size<=0 while there is nothing
    Tempest::Vec4 box() const;

  private:
    std::vector<uint8_t>   cells = std::vector<uint8_t>(size_t(Size*Size), 0);
    Tempest::Vec2          origin;          // world x, z of cell (0,0)
    bool                   placed   = false;
    bool                   empty    = true;
    Tempest::Vec3          lastStep;
    bool                   left     = false;
    uint64_t               lastFill = 0;
    float                  fillDebt = 0;
    uint8_t                dirty    = 0;    // one bit per frame in flight whose buffer is out of date
    Tempest::StorageBuffer ssbo[Resources::MaxFramesInFlight];

    void recentre(const Tempest::Vec3& hero);
    void stamp(float x, float z, Tempest::Vec2 dir);
    void fill(uint8_t amount);
  };
