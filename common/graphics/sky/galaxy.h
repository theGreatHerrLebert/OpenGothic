#pragma once

#include <Tempest/Texture2d>

#include <array>
#include <string_view>

// Images for a galaxy over the sky (see shader/sky/sky.frag): slot 0 is a 360-degree panorama, slots 1 and 2 are
// nebulae placed as patches on the sky. Loaded on demand from Python; how strongly they show is the world's
// GlobalEffects::Galaxy.
class Galaxy final {
  public:
    enum : size_t { Panorama = 0, Slots = 3 };

    static Galaxy& inst();

    bool                      load(size_t slot, std::string_view path);
    void                      clear(size_t slot);
    // Destroys every image at once; called at shutdown after the device is idle and before it is destroyed (the
    // store itself is a static, which would otherwise outlive the device).
    void                      releaseAll();
    const Tempest::Texture2d& texture(size_t slot) const;

  private:
    std::array<Tempest::Texture2d,Slots> tex;
  };
