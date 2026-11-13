#pragma once

#include <algorithm>

#include <Tempest/SoundEffect>

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
      float          aurora = 0;           // northern lights over it, 0..1
      float          time   = 0;           // seconds, for the aurora's drift
      float          moon   = 0;           // a blood-red moon rising, 0..1
      };
    void          setGalaxy(const Galaxy& g) { galaxy = g; }
    const Galaxy& galaxyState() const { return galaxy; }
    // Falling snow over the finished frame, 0 none .. 1 a blizzard; independent of a trip.
    void        setSnow(float density) { snow = density; }
    float       snowDensity() const { return snow; }

    // Weather in the world (docs/plan-weather.md), set from Python and eased towards its target in game time. A change
    // of kind first lets the old precipitation stop, then the new one begins.
    enum class Precipitation : uint8_t { None, Snow, Rain };
    struct Weather {
      Precipitation kind        = Precipitation::None;
      float         intensity   = 0;    // what falls now, 0..1
      float         target      = 0;
      float         fadeSeconds = 10;
      float         windX       = 0;    // metres per second the wind carries what falls
      float         windZ       = 0;
      float         cover       = 0;    // snow lying on the ground, 0..1
      float         coverTarget = 0;
      float         coverSeconds = 600;
      float         wet         = 0;    // how wet the ground is: rises while it rains, dries slowly after
      float         overcast    = 0;    // how closed the sky is: follows what falls, slower
      float         flash       = 0;    // a lightning flash, fading within a fraction of a second
      bool          openSky     = false; // falls from a clear sky (a trip's snow under the stars): no clouds
      float         fog         = 0;    // ground fog, 0..1, eased towards fogTarget
      float         fogTarget   = 0;
      float         fogSeconds  = 60;
      float         fogHeight   = 25;   // metres the fog reaches above its base (it thins exponentially)
      float         fogBase     = 0;    // world height of its base, in cm
      };
    // Ground fog (docs/plan-weather.md): density 0..1 over seconds, lying from base (world cm) and thinning upwards.
    void           setFog(float target, float heightMetres, float baseCm, float seconds);
    // Lightning: a flash now, its thunder after delay seconds (sound travels about 340 m a second).
    void           lightning(float delaySeconds);
    void           setWeather(Precipitation kind, float target, float fadeSeconds, float windX, float windZ,
                              bool openSky = false);
    void           setCover(float target, float seconds);
    const Weather& weatherState() const { return weather; }
    // What actually falls: nothing until the clouds have half covered the sky, all of it once they have closed.
    float          falling() const {
      if(weather.kind==Precipitation::None)
        return 0.f;
      if(weather.openSky)
        return weather.intensity;
      // how far the clouds have come towards the cover this weather brings: half way, it starts; nearly there, all
      const float t = std::clamp((weather.overcast/std::max(cloudsFor(), 0.01f)-0.55f)/0.4f, 0.f, 1.f);
      return weather.intensity*t*t*(3.f-2.f*t);
      }
    // The cover any weather brings: even light rain greys most of the sky; heavy weather closes it.
    float          cloudsFor() const {
      return (weather.kind==Precipitation::None || weather.openSky) ? 0.f : 0.7f + 0.3f*weather.intensity;
      }
    bool           isRaining() const { return weather.kind==Precipitation::Rain && falling()>0.1f; }

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
    Weather                                   weather;
    Precipitation                             pendingKind   = Precipitation::None;
    float                                     pendingTarget = -1;   // below zero: no change of kind waiting

    void tickWeather(uint64_t dt);
    void tickWeatherSound();
    Tempest::SoundEffect                      rainSound, windSound;
    float                                     thunderIn = -1;   // seconds until the thunder; below zero: none due
    Galaxy                                    galaxy;
    float                                     tripTimeRem = 0;
  friend class GlobalFx;
  };

