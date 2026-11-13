#include <cmath>
#include "gothic.h"
#include <algorithm>
#include "globaleffects.h"

#include <Tempest/Log>

#include "world/objects/globalfx.h"
#include "world/world.h"
#include "graphics/visualfx.h"

using namespace Tempest;

GlobalEffects::GlobalEffects(World& owner):owner(owner) {
  /*
  std::string argv[] = {"1000", "5", "5 5 5"};
  auto g = startEffect("earthquake.eqk", 0, argv, 3);
  auto h = g.h;
  g = GlobalFx();
  h->timeUntil = uint64_t(-1);
  */
  }

void GlobalEffects::tick(uint64_t dt) {
  tick(dt,timeEff);
  tick(dt,scrEff);
  tick(dt,morphEff);
  tick(dt,quakeEff);
  tickWeather(dt);
  }

void GlobalEffects::setWeather(Precipitation kind, float target, float fadeSeconds, float windX, float windZ,
                               bool openSky) {
  weather.openSky = openSky;
  target            = std::clamp(target, 0.f, 1.f);
  weather.fadeSeconds = std::max(fadeSeconds, 0.f);
  weather.windX     = windX;
  weather.windZ     = windZ;
  if(kind!=weather.kind && weather.intensity>0.01f && weather.fadeSeconds>0.f) {
    pendingKind    = kind;      // let what falls now stop first
    pendingTarget  = target;
    weather.target = 0;
    return;
    }
  pendingTarget  = -1;
  weather.kind   = kind;
  weather.target = kind==Precipitation::None ? 0.f : target;
  if(weather.fadeSeconds<=0.f)
    weather.intensity = weather.target;
  }

void GlobalEffects::setCover(float target, float seconds) {
  weather.coverTarget  = std::clamp(target, 0.f, 1.f);
  weather.coverSeconds = std::max(seconds, 0.f);
  if(weather.coverSeconds<=0.f)
    weather.cover = weather.coverTarget;
  }

void GlobalEffects::tickWeather(uint64_t dt) {
  const float sec  = float(dt)/1000.f;
  auto        ease = [sec](float& value, float target, float seconds) {
    if(seconds<=0.f) {
      value = target;
      return;
      }
    const float step = sec/seconds;
    value = value<target ? std::min(value+step, target) : std::max(value-step, target);
    };
  ease(weather.intensity, weather.target, weather.fadeSeconds);
  // Snow settles only while it falls, as fast as it falls: no white ground under a sky still closing.
  // Melting keeps its own pace; a cover set at once (seconds 0) is snow already lying.
  if(weather.cover<weather.coverTarget && weather.coverSeconds>0.f) {
    const float snowing = weather.kind==Precipitation::Snow ? falling() : 0.f;
    if(snowing>0.001f)
      ease(weather.cover, weather.coverTarget, weather.coverSeconds/snowing);
    } else {
    ease(weather.cover, weather.coverTarget, weather.coverSeconds);
    }
  ease(weather.fog, weather.fogTarget, weather.fogSeconds);
  ease(weather.heat, weather.heatTarget, weather.heatSeconds);
  for(auto& [name, l] : loops)
    ease(l.level, l.target, l.seconds);
  // The ground gets wet within a couple of minutes of rain and takes a quarter of an hour to dry, much less in heat.
  const float wetTarget = weather.kind==Precipitation::Rain ? falling() : 0.f;
  ease(weather.wet, wetTarget, wetTarget>weather.wet ? 120.f : 900.f/(1.f + 4.f*weather.heat));
  // The sky closes as the weather comes (a minute and a half) and opens again slower (three minutes).
  const float closed = cloudsFor();
  ease(weather.overcast, closed, closed>weather.overcast ? 90.f : 180.f);
  weather.flash = std::max(0.f, weather.flash - sec*5.f);
  if(thunderIn>=0.f) {
    thunderIn -= sec;
    if(thunderIn<0.f)
      Gothic::inst().emitGlobalSoundWav("NEARTHUNDER.WAV");
    }
  tickWeatherSound();
  if(pendingTarget>=0.f && weather.intensity<=0.01f) {
    weather.kind   = pendingKind;
    weather.target = pendingKind==Precipitation::None ? 0.f : pendingTarget;
    pendingTarget  = -1;
    }
  }

template<class T>
void GlobalEffects::tick(uint64_t /*dt*/, std::vector<T>& eff) {
  uint64_t time = owner.tickCount();
  for(size_t i=0; i<eff.size(); ) {
    if(eff[i]->timeUntil<time) {
      eff.erase(eff.begin()+int(i));
      } else {
      ++i;
      }
    }
  }

void GlobalEffects::scaleTime(uint64_t& dt) {
  for(auto& pi:timeEff) {
    auto& i = *pi;
    dt            = dt*i.mul + i.timeWrldRem;
    i.timeWrldRem = dt%i.div;
    dt /=i.div;
    }
  if(trip.time<1.f) {
    const float scaled = float(dt)*std::max(trip.time, 0.05f) + tripTimeRem;
    dt          = uint64_t(scaled);
    tripTimeRem = scaled-float(dt);
    }
  }

static float generator(uint64_t dt, uint64_t period) {
  if(period<=0)
    return 0;
  float a0 = float((dt+period/2)%period)/float(period); //[0..1]
  a0 = a0*2.f-1.f;
  return a0;
  }

void GlobalEffects::morph(Tempest::Matrix4x4& proj) {
  for(auto& pi:morphEff) {
    auto& i = *pi;
    float x = i.amplitude*0.075f;
    float y = i.amplitude*0.075f;

    uint64_t time = owner.tickCount()-i.timeStart;
    // a0 = std::sin(float(2*a0*M_PI));

    float a0 = generator(time,5000);
    float a1 = generator(time,9000);
    a0 = std::sin(a0*float(M_PI));
    a1 = std::sin(a1*float(M_PI));

    proj.scale(1.f+a0*x,1.f-a0*y,1.f);
    proj.scale(1.f+a1*x,1.f+a1*y,1.f);
    }
  if(trip.zoom>0.f)
    proj.scale(1.f+trip.zoom,1.f+trip.zoom,1.f);
  if(trip.fov>0.f) {
    const float    x     = trip.fov*0.075f;
    const float    speed = std::max(trip.speed, 0.05f);
    const uint64_t time  = owner.tickCount();
    const float    a0    = std::sin(generator(time, uint64_t(5000.f/speed))*float(M_PI));
    const float    a1    = std::sin(generator(time, uint64_t(9000.f/speed))*float(M_PI));
    proj.scale(1.f+a0*x,1.f-a0*x,1.f);
    proj.scale(1.f+a1*x,1.f+a1*x,1.f);
    }
  }

void GlobalEffects::shake(Vec3& origin) {
  for(auto& pi:quakeEff) {
    auto& i = *pi;

    uint64_t time = owner.tickCount()-i.timeStart;
    if(i.tLast+uint64_t(10) >= time)
      continue;
    i.tLast = time;

    Vec3 off;
    off.x = float(std::rand()%1000)/1000.f;
    off.y = float(std::rand()%1000)/1000.f;
    off.z = float(std::rand()%1000)/1000.f;

    // more interesting curve
    float a = generator(time, i.timeLoop);
    a = std::sin(a*float(M_PI))*0.5f + 0.5f;
    a = a*0.75f+0.25f;

    i.last = i.off*(off*2.f - 1.f)*a;
    origin = i.last;
    }
  if(trip.shake>0.f) {
    Vec3 off;
    off.x = float(std::rand()%1000)/1000.f*2.f-1.f;
    off.y = float(std::rand()%1000)/1000.f*2.f-1.f;
    off.z = float(std::rand()%1000)/1000.f*2.f-1.f;
    origin += off*trip.shake;
    }
  }

void GlobalEffects::scrBlend(Tempest::Painter& p, const Tempest::Rect& rect) {
  if(trip.tint.a()>0.f) {
    p.setBrush(Tempest::Brush(trip.tint,Tempest::Painter::Alpha));
    p.drawRect(rect.x,rect.y,rect.w,rect.h);
    }
  for(auto& pi:scrEff) {
    auto&    i  = *pi;
    auto     cl = i.cl;
    if(i.inout>0) {
      uint64_t now = owner.tickCount();
      float    a0  = std::min(1.f, (float(now-i.timeStart)/1000.f)/i.inout);
      float    a1  = std::min(1.f, (float(i.timeUntil-now)/1000.f)/i.inout);
      float    a   = std::min(a0,a1);
      cl.set(cl.r(),cl.g(),cl.b(),cl.a()*a);
      }
    if(i.frames.size()==0) {
      p.setBrush(Tempest::Brush(cl,Tempest::Painter::Alpha));
      } else {
      uint64_t dt = owner.tickCount()-i.timeStart;
      size_t   frame = size_t(i.fps*dt)/1000;
      if(i.fps>0)
        frame%=i.fps;
      p.setBrush(Tempest::Brush(*i.frames[frame],Tempest::Color(1,1,1,cl.a()),Tempest::Painter::Alpha));
      }
    p.drawRect(rect.x,rect.y,rect.w,rect.h,0,0,p.brush().w(),p.brush().h());
    }
  }

GlobalFx GlobalEffects::startEffect(std::string_view what, uint64_t len, const std::string* argv, size_t argc) {
  auto     ret = create(what,argv,argc);
  auto&    eff = *ret.h;
  if(len==0)
    eff.timeUntil = uint64_t(-1); else
    eff.timeUntil = owner.tickCount()+len;
  eff.timeStart = owner.tickCount();
  eff.timeLen   = len==0 ? uint64_t(-1) : len;
  return ret;
  }

void GlobalEffects::stopEffect(const VisualFx& vfx) {
  auto& what = vfx.visName_S;
  if(what=="time.slw")
    timeEff.clear();
  if(what=="screenblend.scx")
    scrEff.clear();
  if(what=="morph.fov")
    morphEff.clear();
  if(what=="earthquake.eqk")
    quakeEff.clear();
  }

GlobalFx GlobalEffects::create(std::string_view what, const std::string* argv, size_t argc) {
  if(what=="time.slw")
    return addSlowTime(argv,argc);
  if(what=="screenblend.scx")
    return addScreenBlend(argv,argc);
  if(what=="morph.fov")
    return addMorphFov(argv,argc);
  if(what=="earthquake.eqk")
    return addEarthQuake(argv,argc);
  return GlobalFx();
  }

GlobalFx GlobalEffects::addSlowTime(const std::string* argv, size_t argc) {
  double val[2] = {1,1};
  for(size_t i=0; i<argc && i<2; ++i) {
    try {
      val[i] = std::stof(argv[i]);
      }
    catch(...) {
      Log::e("invalid time.slw parameter [",i,"]: \"", argv[i], "\"");
      }
    }
  uint64_t v[2] = {};
  for(int i=0; i<2; ++i)
    v[i] = uint64_t(val[i]*1000);
  // todo: separated time-scale
  SlowTime s;
  s.mul = v[0];
  s.div = 1000;
  timeEff.emplace_back(std::make_shared<SlowTime>(s));
  return GlobalFx(timeEff.back());
  }

GlobalFx GlobalEffects::addScreenBlend(const std::string* argv, size_t argc) {
  ScreenBlend sc;

  if(0<argc) try {
    sc.loop   = float(std::stof(argv[0]));
    }
  catch(...) {
    Log::e("invalid screenblend.scx parameter [0]: \"", argv[0], "\"");
    }

  if(1<argc) {
    sc.cl     = parseColor(argv[1]);
    }

  if(2<argc) try {
    sc.inout  = float(std::stof(argv[2]));
    }
  catch(...){
    Log::e("invalid screenblend.scx parameter [2]: \"", argv[2], "\"");
    }

  if(3<argc) {
    sc.frames = Resources::loadTextureAnim(argv[3]);
    }

  if(4<argc) try {
    sc.fps    = size_t(std::stoi(argv[4]));
    }
  catch(...) {
    Log::e("invalid screen-blend parameter [4]: \"", argv[4], "\"");
    }

  sc.timeLoop = uint64_t(sc.loop*1000.f);

  scrEff.emplace_back(std::make_shared<ScreenBlend>(sc));
  return GlobalFx(scrEff.back());
  }

GlobalFx GlobalEffects::addMorphFov(const std::string* argv, size_t argc) {
  double val[4] = {0,0,0,0};
  for(size_t i=0; i<argc && i<4; ++i) {
    val[i] = std::stof(argv[i]);
    }
  Morph m;
  m.amplitude = float(val[0]);
  m.speed     = float(val[1]);
  m.baseX     = float(val[2]);
  m.baseY     = float(val[3]);

  morphEff.emplace_back(std::make_shared<Morph>(m));
  return GlobalFx(morphEff.back());
  }

GlobalFx GlobalEffects::addEarthQuake(const std::string* argv, size_t argc) {
  // https://worldofplayers.ru/threads/39160/
  if(argc<3)
    return GlobalFx();

  Quake q;
  q.arg0 = std::stof(argv[0]);
  q.loop = std::stof(argv[1]);
  q.off  = parseVec3(argv[2]);

  q.timeLoop = uint64_t(q.loop * 1000.f);

  quakeEff.emplace_back(std::make_shared<Quake>(q));
  return GlobalFx(quakeEff.back());
  }

Tempest::Color GlobalEffects::parseColor(std::string_view sv) {
  auto  s    = std::string(sv);
  auto  str  = s.data();

  float v[4] = {};
  for(int i=0;i<4;++i) {
    char* next=nullptr;
    v[i] = std::strtof(str,&next)/255.f;
    if(str==next)
      if(i==1) {
        return Tempest::Color(v[0],v[0],v[0],1.f);
      if(i==2)
        return Tempest::Color(v[0],v[1],0.f,1.f);
      if(i==3)
        return Tempest::Color(v[0],v[1],v[2],1.f);
      }
    str = next;
    }
  return Tempest::Color(v[0],v[1],v[2],v[3]);
  }

Vec3 GlobalEffects::parseVec3(std::string_view sv) {
  auto  s    = std::string(sv);
  auto  str  = s.data();

  float v[3] = {};
  for(int i=0;i<3;++i) {
    char* next = nullptr;
    v[i] = std::strtof(str,&next);
    if(str==next)
      if(i==1) {
        return Tempest::Vec3(v[0],v[0],v[0]);
      if(i==2)
        return Tempest::Vec3(v[0],v[1],0.f);
      if(i==3)
        return Tempest::Vec3(v[0],v[1],v[2]);
      }
    str = next;
    }
  return Tempest::Vec3(v[0],v[1],v[2]);
  }

void GlobalEffects::Effect::stop() {
  timeUntil = 0;
  }

void GlobalEffects::lightning(float delaySeconds) {
  weather.flash = 1.f;
  thunderIn     = std::max(delaySeconds, 0.f);
  }

void GlobalEffects::tickWeatherSound() {
  // The game's own rain and storm sounds, kept going while they are wanted, as loud as the weather is.
  const float rain = weather.kind==Precipitation::Rain ? falling() : 0.f;
  const float wind = std::min(std::sqrt(weather.windX*weather.windX + weather.windZ*weather.windZ)/8.f, 1.f) *
                     (weather.kind==Precipitation::None ? 0.3f : 1.f);
  auto keep = [](Tempest::SoundEffect& snd, const char* wav, float volume) {
    if(volume<0.02f) {
      if(!snd.isEmpty())
        snd = Tempest::SoundEffect();
      return;
      }
    if(snd.isEmpty() || snd.isFinished()) {
      snd = Gothic::inst().loadSoundEffect(wav);
      snd.play();
      }
    snd.setVolume(volume);
    };
  keep(rainSound, "RAIN_01.WAV",       rain*0.9f);
  keep(windSound, "WIND_HEAVY01.WAV",  wind*0.7f);
  for(auto& [name, l] : loops) {
    if(l.level<0.01f) {
      if(!l.snd.isEmpty())
        l.snd = Tempest::SoundEffect();
      continue;
      }
    if(l.broken)
      continue;
    if(l.snd.isEmpty() || l.snd.isFinished()) {
      // an optional sound of ours: a missing or broken file leaves it silent, it never stops the game
      try {
        l.snd = Gothic::inst().loadSoundFile(l.path);
        }
      catch(...) {
        Log::e("weather loop: cannot play \"", l.path, "\"");
        l.broken = true;
        l.snd    = Tempest::SoundEffect();
        continue;
        }
      l.snd.play();
      }
    l.snd.setVolume(l.level);
    }
  }

void GlobalEffects::setLoop(const std::string& name, const std::string& path, float volume, float seconds) {
  auto& l = loops[name];
  if(l.path!=path) {
    l.path   = path;
    l.broken = false;
    l.snd  = Tempest::SoundEffect();   // the next tick starts the new one
    }
  l.target  = std::clamp(volume, 0.f, 1.f);
  l.seconds = std::max(seconds, 0.f);
  if(l.seconds<=0.f)
    l.level = l.target;
  }

std::vector<std::pair<std::string, float>> GlobalEffects::loopLevels() const {
  std::vector<std::pair<std::string, float>> ret;
  for(auto& [name, l] : loops)
    ret.emplace_back(name, l.level);
  return ret;
  }

void GlobalEffects::setHeat(float target, float seconds) {
  weather.heatTarget  = std::clamp(target, 0.f, 1.f);
  weather.heatSeconds = std::max(seconds, 0.f);
  if(weather.heatSeconds<=0.f)
    weather.heat = weather.heatTarget;
  }

void GlobalEffects::setFog(float target, float heightMetres, float baseCm, float seconds) {
  weather.fogTarget  = std::clamp(target, 0.f, 1.f);
  weather.fogHeight  = std::clamp(heightMetres, 2.f, 300.f);
  weather.fogBase    = baseCm;
  weather.fogSeconds = std::max(seconds, 0.f);
  if(weather.fogSeconds<=0.f)
    weather.fog = weather.fogTarget;
  }
