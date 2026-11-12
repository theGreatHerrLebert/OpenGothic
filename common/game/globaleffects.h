#pragma once

#include <Tempest/Matrix4x4>
#include <Tempest/Painter>
#include <Tempest/Texture2d>

#include <vector>
#include <memory>
#include <cstdint>

class World;
class VisualFx;
class GlobalFx;

class GlobalEffects {
  public:
    GlobalEffects(World& owner);

    void     tick(uint64_t dt);
    GlobalFx startEffect(std::string_view what, uint64_t len, const std::string* argv, size_t argc);
    void     stopEffect (const VisualFx& vfx);

    void     scaleTime(uint64_t& dt);
    void     morph(Tempest::Matrix4x4& proj);
    void     shake(Tempest::Vec3& origin);
    void     scrBlend(Tempest::Painter& p, const Tempest::Rect& rect);

    // A trip whose strength a story sets every tick, so nothing here has a duration. Zero everywhere is sober.
    struct Trip {
      float          fov   = 0;            // breathing of the view: 1 is as strong as the game's own fov morph
      float          speed = 1;            // how fast it breathes
      Tempest::Color tint  = {0,0,0,0};    // colour washed over the screen, alpha is its strength
      float          time  = 1;            // world speed: below 1 the world slows down
      float          shake = 0;            // camera shake, in centimetres
      float          zoom  = 0;            // the view drawn in by this fraction: a beat's contraction
      // The post-process over the finished frame (shader/trip/trip.frag): zero intensity skips it entirely.
      float          post    = 0;          // its intensity, 0 sober .. 1 peak
      float          edges   = 1;          // how strongly edges glow
      float          tracers = 1;          // how strongly the previous frame persists
      float          bass = 0, mid = 0, treble = 0;   // music bands, smoothed
      int            look = 0;             // 0 Mindcap (neon edges, tracers), 1 Emberheart (heat shimmer), 2 the Invocation
      float          eye   = 0;            // Solaris's DragonflyEye over it: compound eye and rose window, 0..1
      float          afterglow = 0;        // Solaris's Afterglow over it: long-exposure glow and light trails, 0..1
      };
    void        setTrip(const Trip& t) { trip = t; }
    const Trip& tripState() const { return trip; }
    // A galaxy in place of the sky (graphics/sky/galaxy.h holds its images), set every tick like the trip.
    struct Galaxy {
      float          amount = 0;           // 0 the game's own sky .. 1 the galaxy instead
      float          gain   = 1;           // its brightness
      Tempest::Vec3  tint   = {1,1,1};     // the colour it is graded towards
      float          grade  = 0;           // 0 its own colours .. 1 graded to the tint
      float          spin   = 0;           // radians around the pole: the sky turning
      float          glow   = 0;           // a swell, 0..1, from the music
      Tempest::Vec4  nebula[2] = {};       // per nebula slot: yaw, pitch, size across (radians), strength
      };
    void          setGalaxy(const Galaxy& g) { galaxy = g; }
    const Galaxy& galaxyState() const { return galaxy; }
    // Falling snow over the finished frame, 0 none .. 1 a blizzard; independent of a trip.
    void        setSnow(float density) { snow = density; }
    float       snowDensity() const { return snow; }

  private:
    struct Effect {
      virtual ~Effect(){}
      virtual void stop();
      uint64_t timeUntil = 0;
      uint64_t timeStart = 0;
      uint64_t timeLen   = 0;
      uint64_t timeLoop  = 0;
      };

    struct SlowTime:Effect {
      // world  time scaler
      uint64_t mul = 0;
      uint64_t div = 0;
      uint64_t timeWrldRem = 0;
      // TODO: player time scaler
      };

    struct ScreenBlend:Effect {
      float          loop  = 0;                      // screenblend loop duration
      Tempest::Color cl    = {1,1,1,1};              // screenblend color
      float          inout = 0;                      // screenblend in/out duration
      std::vector<const Tempest::Texture2d*> frames; // screenblend texture
      size_t         fps   = 1;                      // tex ani fps
      };

    struct Morph:Effect {
      float amplitude = 1; // fov morph amplitude scaler
      float speed     = 1; // fov morph speed scaler
      float baseX     = 0; // fov base x (leave empty for default)
      float baseY     = 0; // fov base y (leave empty for default)
      };

    struct Quake:Effect {
      float          arg0  = 0; // unknown
      float          loop  = 0; // earthquake loop duration
      Tempest::Vec3  off   = {};

      Tempest::Vec3  last  = {};
      uint64_t       tLast = 0;
      };

    template<class T>
    void    tick(uint64_t dt, std::vector<T>& eff);

    GlobalFx create        (std::string_view what, const std::string* argv, size_t argc);
    GlobalFx addSlowTime   (const std::string* argv, size_t argc);
    GlobalFx addScreenBlend(const std::string* argv, size_t argc);
    GlobalFx addMorphFov   (const std::string* argv, size_t argc);
    GlobalFx addEarthQuake (const std::string* argv, size_t argc);

    static Tempest::Color parseColor(std::string_view c);
    static Tempest::Vec3  parseVec3 (std::string_view c);

    World& owner;

    std::vector<std::shared_ptr<SlowTime>>    timeEff;
    std::vector<std::shared_ptr<ScreenBlend>> scrEff;
    std::vector<std::shared_ptr<Morph>>       morphEff;
    std::vector<std::shared_ptr<Quake>>       quakeEff;
    Trip                                      trip;
    float                                     snow = 0;
    Galaxy                                    galaxy;
    float                                     tripTimeRem = 0;
  friend class GlobalFx;
  };

